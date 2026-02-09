import subprocess
import logging
import time
import shutil
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

import os

class LinuxTunManager:
    """
    Helper class for managing Linux TUN/TAP routing and firewall rules.
    Designed for platform-exclusive operations on Linux.
    """

    def __init__(self):
        self.check_platform()

    def check_platform(self):
        import platform
        if platform.system() != "Linux":
            logger.warning("LinuxTunManager instantiated on non-Linux platform. Operations will fail or be ignored.")

    @staticmethod
    def is_docker() -> bool:
        """Check if running inside a Docker container."""
        # Check .dockerenv file
        if os.path.exists('/.dockerenv'):
            return True
        
        # Check cgroup
        path = '/proc/self/cgroup'
        try:
            if os.path.isfile(path):
                with open(path, 'r') as f:
                    for line in f:
                        if 'docker' in line:
                            return True
        except Exception:
            pass
            
        return False

    @staticmethod
    def get_default_route() -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Get original default gateway, interface, and primary IP.
        Returns: (gateway, interface, ip_address)
        """
        gw, iface, ip = None, None, None
        try:
            # Get default route
            result = subprocess.run(
                ["ip", "route", "show", "default"],
                capture_output=True, text=True, timeout=5,
            )
            # Example output: "default via 172.18.0.1 dev eth0"
            lines = result.stdout.strip().split('\n')
            if lines:
                parts = lines[0].split()
                if 'via' in parts and 'dev' in parts:
                    gw = parts[parts.index('via') + 1]
                    iface = parts[parts.index('dev') + 1]
        except Exception as e:
            logger.warning(f"Could not get default route: {e}")
            return None, None, None

        # Get IP address for the interface
        if iface:
            try:
                result = subprocess.run(
                    ["ip", "-4", "-o", "addr", "show", "dev", iface],
                    capture_output=True, text=True, timeout=5,
                )
                for line in result.stdout.strip().split('\n'):
                    if 'inet ' in line:
                        # Format: "N: eth0  inet 172.18.0.2/16 ..."
                        # Split by whitespace, find 'inet', next is IP/CIDR
                        parts = line.split()
                        if 'inet' in parts:
                            ip_cidr = parts[parts.index('inet') + 1]
                            ip = ip_cidr.split('/')[0]
                            break
            except Exception:
                pass

        if gw and iface:
            logger.info(f"Detected default route: via {gw} dev {iface}, IP {ip}")
        return gw, iface, ip

    @staticmethod
    def setup_bypass_routing(gw: str, iface: str, ip: str, table_id: int = 100):
        """
        Set up policy routing to ensure traffic from the specific IP 
        uses the original gateway (bypassing the VPN/TUN).
        """
        if not gw or not iface or not ip:
            logger.warning("Missing routing info, skipping bypass routing setup.")
            return

        try:
            logger.info(f"Setting up bypass routing: from {ip} -> table {table_id} via {gw} dev {iface}")
            
            # 1. Add default route to custom table
            subprocess.run(
                f"ip route add default via {gw} dev {iface} table {table_id}",
                shell=True, check=False, stderr=subprocess.DEVNULL
            )
            
            # 2. Copy link-scope routes to custom table (for ARP/local reachability)
            res = subprocess.run(
                f"ip route show dev {iface} scope link",
                capture_output=True, text=True, shell=True,
            )
            for line in res.stdout.strip().split('\n'):
                subnet = line.split()[0] if line.strip() else None
                if subnet:
                    subprocess.run(
                        f"ip route add {subnet} dev {iface} table {table_id}",
                        shell=True, check=False, stderr=subprocess.DEVNULL
                    )

            # 3. Add IP rule to use custom table
            # Clean up old rule first just in case
            subprocess.run(f"ip rule del from {ip} lookup {table_id} 2>/dev/null", shell=True, check=False)
            subprocess.run(f"ip rule add from {ip} lookup {table_id}", shell=True, check=False)
            
        except Exception as e:
            logger.error(f"Failed to setup bypass routing: {e}")

    @staticmethod
    def cleanup_bypass_routing(ip: Optional[str], table_id: int = 100):
        """
        Remove the bypass routing rules and flush the custom table.
        """
        try:
            # Remove ip rule
            if ip:
                subprocess.run(f"ip rule del from {ip} lookup {table_id} 2>/dev/null", shell=True, check=False)
            else:
                # If IP unknown, try to clean based on table ID scan
                # (Less safe, so we prefer explicit IP, but we can try removing all rules for this table)
                # For now, rely on specific IP or just skip
                pass

            # Flush table
            subprocess.run(f"ip route flush table {table_id} 2>/dev/null", shell=True, check=False)
            logger.info(f"Bypass routing (table {table_id}) cleaned up.")
        except Exception as e:
            logger.error(f"Error cleaning up bypass routing: {e}")

    @staticmethod
    def add_static_route(target: str, gateway: str, interface: str):
        """Add a specific static route via a gateway."""
        try:
            # target can be IP or CIDR. 
            # If target is IP, append /32 if not present? ip route add handles bare IPs as /32 usually.
            logger.info(f"Adding static route: {target} via {gateway}")
            subprocess.run(
                f"ip route add {target} via {gateway} dev {interface}",
                shell=True, check=False, stderr=subprocess.DEVNULL
            )
        except Exception as e:
            logger.error(f"Failed to add static route: {e}")

    @staticmethod
    def delete_static_route(target: str):
        """Delete a specific static route."""
        try:
            subprocess.run(
                f"ip route del {target} 2>/dev/null",
                shell=True, check=False
            )
        except Exception as e:
            logger.error(f"Failed to delete static route: {e}")

    @staticmethod
    def set_default_interface(interface: str):
        """Replace the default system route to go through a specific interface."""
        try:
            logger.info(f"Replacing default route with dev {interface}")
            subprocess.run(
                f"ip route replace default dev {interface}",
                shell=True, check=False
            )
        except Exception as e:
            logger.error(f"Failed to set default interface: {e}")

    @staticmethod
    def tun_interface_exists(pattern: str = "tun") -> bool:
        """Check if any interface matching the pattern exists."""
        try:
            result = subprocess.run(
                ["ip", "link", "show"],
                capture_output=True, text=True, timeout=5
            )
            # Simplified check
            return any(pattern in line for line in result.stdout.split('\n'))
        except Exception:
            return False

    @staticmethod
    def get_tun_interface_name(prefix: str = "tun") -> Optional[str]:
        """Get the name of the first interface starting with prefix."""
        try:
            result = subprocess.run(
                ["ip", "-o", "link", "show"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.strip().split('\n'):
                # Format: "N: name: ..."
                parts = line.split(':')
                if len(parts) >= 2:
                    name = parts[1].strip()
                    if name.startswith(prefix):
                        return name
        except Exception:
            pass
        return None

    @staticmethod
    def apply_nftables_allow_rules(interface: str, ports: list[int]):
        """
        Add nftables rules to allow traffic on specific ports for the given interface.
        Used when Cloudflare WARP enables its firewall (cloudflare-warp table).
        """
        if not shutil.which("nft"):
            logger.warning("nft command not found, skipping nftables configuration")
            return

        logger.info(f"Waiting for WARP nftables table...")
        # Wait for table
        table_ready = False
        for _ in range(10):
            res = subprocess.run(
                "nft list table inet cloudflare-warp 2>/dev/null",
                shell=True, capture_output=True
            )
            if res.returncode == 0:
                table_ready = True
                break
            time.sleep(0.5)
        
        if not table_ready:
            logger.warning("WARP nftables table not found.")
            return

        logger.info(f"Adding allow rules for {interface} on ports {ports}")
        try:
            # Allow Output
            subprocess.run(
                f"nft insert rule inet cloudflare-warp output oif \"{interface}\" accept 2>/dev/null",
                shell=True, check=False
            )
            
            # Allow Input on specific ports
            for port in ports:
                subprocess.run(
                    f"nft insert rule inet cloudflare-warp input iif \"{interface}\" tcp dport {port} accept 2>/dev/null",
                    shell=True, check=False
                )
        except Exception as e:
            logger.error(f"Failed to apply nftables rules: {e}")

