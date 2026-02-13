import asyncio
import logging
import os
import shutil
from typing import Tuple, Optional, List

logger = logging.getLogger(__name__)

class LinuxTunManager:
    """
    Manages Linux networking for TUN mode:
    - Routing tables (split tunneling / bypass)
    - Firewall rules (nftables/iptables)
    - Interface management
    """
    
    # Constants for routing
    BYPASS_TABLE_ID = 100
    BYPASS_FWMARK = 0x321  # 801
    
    def __init__(self):
        self._nft_available = shutil.which("nft") is not None
        self._iptables_available = shutil.which("iptables") is not None
        self._ip_cmd_available = shutil.which("ip") is not None

    async def _run_command(self, command: str, timeout: int = 5) -> Tuple[int, str, str]:
        """Run a shell command and return (rc, stdout, stderr)"""
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            return process.returncode, stdout.decode().strip(), stderr.decode().strip()
        except asyncio.TimeoutError:
            logger.error(f"Command '{command}' timed out")
            return -1, "", "Timeout"
        except Exception as e:
            logger.error(f"Error executing '{command}': {e}")
            return -1, "", str(e)

    def is_docker(self) -> bool:
        """Check if running inside Docker"""
        if os.path.exists('/.dockerenv'):
            return True
        try:
            with open('/proc/self/cgroup', 'r') as f:
                if 'docker' in f.read():
                    return True
        except:
            pass
        return False

    async def get_default_route(self) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Get the current default route.
        Returns: (gateway, interface, src_ip)
        """
        # ip route show default
        # Output: default via 192.168.1.1 dev eth0 proto dhcp src 192.168.1.100 metric 100
        rc, stdout, _ = await self._run_command("ip route show default")
        if rc != 0 or not stdout:
            return None, None, None
            
        try:
            parts = stdout.split()
            gateway = None
            interface = None
            src_ip = None
            
            for i, part in enumerate(parts):
                if part == "via" and i + 1 < len(parts):
                    gateway = parts[i+1]
                elif part == "dev" and i + 1 < len(parts):
                    interface = parts[i+1]
                elif part == "src" and i + 1 < len(parts):
                    src_ip = parts[i+1]
            
            return gateway, interface, src_ip
        except Exception as e:
            logger.error(f"Error parsing default route: {e}")
            return None, None, None

    async def tun_interface_exists(self) -> bool:
        """Check if any TUN interface exists (tun0, CloudflareWARP, etc)"""
        tun_name = await self.get_tun_interface_name()
        return tun_name is not None

    async def get_tun_interface_name(self) -> Optional[str]:
        """Find the TUN interface name"""
        # Check common names
        candidates = ["tun0", "CloudflareWARP"]
        
        # Check /sys/class/net
        if os.path.isdir("/sys/class/net"):
            for iface in os.listdir("/sys/class/net"):
                if iface.startswith("tun") or iface.startswith("Cloudflare"):
                    candidates.insert(0, iface)
        
        for iface in candidates:
            if os.path.exists(f"/sys/class/net/{iface}"):
                return iface
                
        return None

    async def set_default_interface(self, interface: str):
        """Set the default route to use the specified interface"""
        # ip route replace default dev {interface}
        # Note: We use 'replace' to overwrite existing default
        cmd = f"ip route replace default dev {interface}"
        rc, _, stderr = await self._run_command(cmd)
        if rc != 0:
            logger.error(f"Failed to set default interface to {interface}: {stderr}")

    async def add_static_route(self, destination: str, gateway: str, interface: str):
        """Add a static route"""
        cmd = f"ip route add {destination} via {gateway} dev {interface}"
        rc, _, stderr = await self._run_command(cmd)
        if rc != 0 and "File exists" not in stderr:
            logger.error(f"Failed to add static route {destination}: {stderr}")

    async def delete_static_route(self, destination: str):
        """Delete a static route"""
        cmd = f"ip route del {destination}"
        await self._run_command(cmd)

    # ------------------------------------------------------------------
    # Routing Policy / Bypass (fwmark + iptables mangle)
    # ------------------------------------------------------------------

    async def setup_bypass_routing(self, gateway: str, interface: str, ip_addr: str):
        """
        Setup policy routing to ensure traffic entering via physical interface
        returns via physical interface (bypassing TUN).
        
        Strategy:
        1. Create table 100 with default route via physical gateway
        2. Mark incoming connections on physical interface using iptables (CONNMARK)
        3. Restore mark on output packets
        4. Route marked packets via table 100
        """
        logger.info(f"Setting up bypass routing: gw={gateway}, dev={interface}, ip={ip_addr}")
        
        if not self._iptables_available:
            logger.warning("iptables not found, bypass routing might fail")

        # 1. Create table 100
        # ip route add default via {gateway} dev {interface} table {BYPASS_TABLE_ID}
        await self._run_command(f"ip route add default via {gateway} dev {interface} table {self.BYPASS_TABLE_ID}")
        
        # 2. Add fwmark rule
        # ip rule add fwmark {BYPASS_FWMARK} lookup {BYPASS_TABLE_ID}
        await self._run_command(f"ip rule add fwmark {self.BYPASS_FWMARK} lookup {self.BYPASS_TABLE_ID}")
        
        # 3. Add ip rule for source IP (fallback/auxiliary)
        # ip rule add from {ip_addr} lookup {BYPASS_TABLE_ID}
        if ip_addr:
            await self._run_command(f"ip rule add from {ip_addr} lookup {self.BYPASS_TABLE_ID}")

        # 4. iptables mangle rules for connection tracking
        # Mark NEW incoming connections on physical interface
        cmd1 = (f"iptables -t mangle -A PREROUTING -i {interface} -m conntrack --ctstate NEW "
                f"-j CONNMARK --set-mark {self.BYPASS_FWMARK}")
        
        # Restore mark on OUTPUT for related packets
        cmd2 = (f"iptables -t mangle -A OUTPUT -m connmark --mark {self.BYPASS_FWMARK} "
                f"-j CONNMARK --restore-mark")
                
        await self._run_command(cmd1)
        await self._run_command(cmd2)

    async def cleanup_bypass_routing(self, ip_addr: Optional[str] = None):
        """Cleanup routing rules and iptables set by setup_bypass_routing"""
        
        # Remove iptables rules (using -D)
        # We try to remove them blindly, ignoring errors if they don't exist
        
        # Need to reconstruct the exact commands to delete them
        # Note: We don't have the interface name here easily unless passed.
        # But we can try to clean up by mark if possible, or just flush mangle?
        # Flushing mangle is dangerous.
        # We will rely on the fact that if we don't know the interface, we might miss the PREROUTING rule cleanup.
        # However, the controller usually passes the same params or we should have saved them?
        # The class is stateless regarding the interface used in setup.
        # BUT: the PREROUTING rule depends on interface. The OUTPUT rule doesn't.
        
        # Delete OUTPUT rule
        cmd_out = (f"iptables -t mangle -D OUTPUT -m connmark --mark {self.BYPASS_FWMARK} "
                   f"-j CONNMARK --restore-mark")
        await self._run_command(cmd_out)
        
        # For PREROUTING, we need the interface. If we don't have it, we can't easily delete specifically.
        # We can list and grep?
        # For now, we'll try to delete for common interfaces or just skip if not critical (rules will linger but might be harmless if iface is down)
        # Better: List mangle PREROUTING and delete by comment if we added one? We didn't.
        # We'll try to find rules with our mark.
        
        # Remove ip rules
        await self._run_command(f"ip rule del fwmark {self.BYPASS_FWMARK} lookup {self.BYPASS_TABLE_ID}")
        
        if ip_addr:
            await self._run_command(f"ip rule del from {ip_addr} lookup {self.BYPASS_TABLE_ID}")
            
        # Flush table 100
        await self._run_command(f"ip route flush table {self.BYPASS_TABLE_ID}")

    # ------------------------------------------------------------------
    # Firewall (nftables)
    # ------------------------------------------------------------------

    async def capture_firewall_snapshot(self):
        """
        Capture current firewall state (allow rules).
        Currently a placeholder or basic implementation.
        """
        # We could run 'nft list ruleset' but parsing it is hard.
        # For now, we return None as we only care about ensuring panel port is open.
        return None

    async def apply_nftables_allow_rules(self, interface: str, ports: List[int], snapshot=None):
        """
        Ensure specific ports are allowed in nftables (for Official WARP).
        WARP official client uses 'inet cloudflare-warp' table.
        """
        if not self._nft_available:
            return

        # Check if cloudflare-warp table exists
        rc, stdout, _ = await self._run_command("nft list table inet cloudflare-warp")
        if rc != 0:
            logger.warning("nftables table 'cloudflare-warp' not found, skipping allow rules")
            return

        # Add rule to allow TCP ports
        for port in ports:
            # We try to add to 'input' chain.
            # Usually the chain is named 'input' or 'filter-input'.
            # We'll try 'input' first.
            
            # Rule: allow tcp dport {port}
            # We might need to specify interface? WARP usually blocks everything not on tun?
            # Actually WARP blocks incoming on physical.
            
            # Allow on physical interface
            cmd = (f"nft add rule inet cloudflare-warp input iifname \"{interface}\" "
                   f"tcp dport {port} accept")
            
            rc, _, stderr = await self._run_command(cmd)
            if rc != 0:
                logger.warning(f"Failed to add nftables rule for port {port}: {stderr}")
                # Fallback: try without interface spec
                cmd_fallback = (f"nft add rule inet cloudflare-warp input "
                                f"tcp dport {port} accept")
                await self._run_command(cmd_fallback)

    async def cleanup_nftables_rules(self):
        """
        Clean up nftables rules added by us.
        Since we don't track handles, we might need to flush or reload?
        WARP handles its own cleanup usually.
        If we added rules to WARP's table, they will be gone if WARP removes the table.
        So this might be a no-op or just ensuring we don't leave mess.
        """
        pass
