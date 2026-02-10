import asyncio
import logging
import shutil
import os
import platform
from typing import Optional, Tuple, Union, List

logger = logging.getLogger(__name__)

class LinuxTunManager:
    """
    Helper class for managing Linux TUN/TAP routing and firewall rules.
    Designed for platform-exclusive operations on Linux.
    """

    # 定义私有网段，用于防止 Docker/局域网流量被错误路由
    PRIVATE_SUBNETS = [
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16"
    ]

    def __init__(self):
        self.check_platform()

    def check_platform(self):
        if platform.system() != "Linux":
            # 这是一个严重错误，非 Linux 环境下直接阻断，防止后续命令报错
            msg = "LinuxTunManager instantiated on non-Linux platform."
            logger.critical(msg)
            raise RuntimeError(msg)

    @staticmethod
    async def _run_command(command: Union[str, List[str]]) -> Tuple[int, str, str]:
        """
        Helper to run async shell commands.
        Supports both string (shell=True, unsafe) and list (exec, safe).
        """
        try:
            if isinstance(command, list):
                # 安全模式：使用 exec，避免 shell 注入
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
            else:
                # 兼容模式：使用 shell，但在处理由外部输入的变量时应避免使用
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
            
            stdout, stderr = await process.communicate()
            return process.returncode, stdout.decode().strip(), stderr.decode().strip()
        except Exception as e:
            cmd_str = command if isinstance(command, str) else " ".join(command)
            logger.error(f"Error running command '{cmd_str}': {e}")
            return -1, "", str(e)

    @staticmethod
    def is_docker() -> bool:
        """Check if running inside a Docker container."""
        if os.path.exists('/.dockerenv'):
            return True
        path = '/proc/self/cgroup'
        try:
            if os.path.isfile(path):
                with open(path, 'r') as f:
                    content = f.read()
                    return 'docker' in content or 'kubepods' in content
        except Exception:
            pass
        return False

    @classmethod
    async def get_default_route(cls) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Get original default gateway, interface, and primary IP.
        Returns: (gateway, interface, ip_address)
        """
        gw, iface, ip = None, None, None
        try:
            # Get default route
            # 使用 split 方式虽然简单，但在复杂网络环境下可能需要更健壮的解析库(如 pyroute2)
            rc, stdout, _ = await cls._run_command(["ip", "route", "show", "default"])
            # Example output: "default via 172.18.0.1 dev eth0"
            lines = stdout.split('\n')
            if lines:
                parts = lines[0].split()
                if 'via' in parts:
                    gw = parts[parts.index('via') + 1]
                if 'dev' in parts:
                    iface = parts[parts.index('dev') + 1]
        except Exception as e:
            logger.warning(f"Could not get default route: {e}")
            return None, None, None

        # Get IP address for the interface
        if iface:
            try:
                rc, stdout, _ = await cls._run_command(["ip", "-4", "-o", "addr", "show", "dev", iface])
                for line in stdout.split('\n'):
                    if 'inet ' in line:
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

    @classmethod
    async def setup_bypass_routing(cls, gw: str, iface: str, ip: str, table_id: int = 100):
        """
        Set up policy routing to ensure traffic from specific IP and Local subnets
        uses the original gateway (bypassing the VPN/TUN).
        """
        if not gw or not iface or not ip:
            logger.warning("Missing routing info, skipping bypass routing setup.")
            return

        try:
            logger.info(f"Setting up bypass routing: from {ip} -> table {table_id} via {gw} dev {iface}")
            
            # 1. Add default route to custom table
            # 所有的路由命令改用 list 格式，防止注入
            await cls._run_command(["ip", "route", "add", "default", "via", gw, "dev", iface, "table", str(table_id)])
            
            # 2. Copy link-scope routes to custom table (for ARP/local reachability)
            rc, stdout, _ = await cls._run_command(["ip", "route", "show", "dev", iface, "scope", "link"])
            for line in stdout.split('\n'):
                subnet = line.split()[0] if line.strip() else None
                if subnet:
                    await cls._run_command(["ip", "route", "add", subnet, "dev", iface, "table", str(table_id)])

            # 3. [关键修改] 优先处理私有网段/Docker 网段
            # 确保 10.x, 172.x, 192.x 的流量直接查 main 表，不进入 TUN
            # Priority 4900 (高于下面的源 IP 规则)
            for subnet in cls.PRIVATE_SUBNETS:
                # 先尝试删除旧规则以防重复
                await cls._run_command(["ip", "rule", "del", "to", subnet, "lookup", "main"])
                await cls._run_command(["ip", "rule", "add", "to", subnet, "lookup", "main", "priority", "4900"])

            # 4. [关键修改] 源 IP 策略路由
            # 凡是源 IP 为本机物理 IP 的流量，强制查 custom table (走物理网关)
            # 这解决了 SSH/Web 服务回包被 TUN 劫持的问题
            # Priority 5000 (需要比 TUN 的默认规则优先级高，通常 TUN 是 0 或默认)
            await cls._run_command(["ip", "rule", "del", "from", ip, "lookup", str(table_id)])
            await cls._run_command(["ip", "rule", "add", "from", ip, "lookup", str(table_id), "priority", "5000"])
            
        except Exception as e:
            logger.error(f"Failed to setup bypass routing: {e}")

    @classmethod
    async def cleanup_bypass_routing(cls, ip: Optional[str], table_id: int = 100):
        """
        Remove the bypass routing rules and flush the custom table.
        """
        try:
            # Remove Local/Docker subnet rules
            for subnet in cls.PRIVATE_SUBNETS:
                await cls._run_command(["ip", "rule", "del", "to", subnet, "lookup", "main", "priority", "4900"])

            # Remove host IP rule
            if ip:
                await cls._run_command(["ip", "rule", "del", "from", ip, "lookup", str(table_id)])

            # Flush table
            await cls._run_command(["ip", "route", "flush", "table", str(table_id)])
            logger.info(f"Bypass routing (table {table_id}) cleaned up.")
        except Exception as e:
            logger.error(f"Error cleaning up bypass routing: {e}")

    @classmethod
    async def add_static_route(cls, target: str, gateway: str, interface: str):
        """Add a specific static route via a gateway."""
        try:
            logger.info(f"Adding static route: {target} via {gateway}")
            await cls._run_command(["ip", "route", "add", target, "via", gateway, "dev", interface])
        except Exception as e:
            logger.error(f"Failed to add static route: {e}")

    @classmethod
    async def delete_static_route(cls, target: str):
        """Delete a specific static route."""
        try:
            await cls._run_command(["ip", "route", "del", target])
        except Exception as e:
            logger.error(f"Failed to delete static route: {e}")

    @classmethod
    async def set_default_interface(cls, interface: str):
        """Replace the default system route to go through a specific interface."""
        try:
            logger.info(f"Replacing default route with dev {interface}")
            await cls._run_command(["ip", "route", "replace", "default", "dev", interface])
        except Exception as e:
            logger.error(f"Failed to set default interface: {e}")

    @classmethod
    async def tun_interface_exists(cls, pattern: str = "tun") -> bool:
        """Check if any interface matching the pattern exists."""
        try:
            rc, stdout, _ = await cls._run_command(["ip", "link", "show"])
            return any(pattern in line for line in stdout.split('\n'))
        except Exception:
            return False

    @classmethod
    async def get_tun_interface_name(cls, prefix: str = "tun") -> Optional[str]:
        """Get the name of the first interface starting with prefix."""
        try:
            rc, stdout, _ = await cls._run_command(["ip", "-o", "link", "show"])
            for line in stdout.split('\n'):
                parts = line.split(':')
                if len(parts) >= 2:
                    name = parts[1].strip()
                    if name.startswith(prefix):
                        return name
        except Exception:
            pass
        return None

    @classmethod
    async def apply_nftables_allow_rules(cls, interface: str, ports: list[int]):
        """
        Add nftables rules to allow traffic on specific ports for the given interface.
        Handles Cloudflare WARP firewall table.
        """
        if not shutil.which("nft"):
            logger.warning("nft command not found, skipping nftables configuration")
            return

        logger.info(f"Waiting for WARP nftables table...")
        table_ready = False
        # 等待表出现的逻辑
        for _ in range(10):
            rc, _, _ = await cls._run_command(["nft", "list", "table", "inet", "cloudflare-warp"])
            if rc == 0:
                table_ready = True
                break
            await asyncio.sleep(0.5)
        
        if not table_ready:
            logger.warning("WARP nftables table not found.")
            return

        logger.info(f"Adding allow rules for {interface} on ports {ports}")
        try:
            # Clean up first (idempotency)
            await cls.cleanup_nftables_rules(interface, ports)
            
            # [关键修改] 允许已建立连接 (Established/Related)
            # 这允许 SSH/Web 等服务的“回包”通过防火墙，防止外部连接中断
            await cls._run_command([
                "nft", "add", "rule", "inet", "cloudflare-warp", "input", 
                "ct", "state", "established,related", "accept", 
                "comment", "warppool-allow-established"
            ])

             # [关键修改] 允许 Docker 流量
             # 假设 docker0 是网桥名，或者允许所有 docker 相关接口
            await cls._run_command([
                "nft", "add", "rule", "inet", "cloudflare-warp", "input",
                "iifname", "docker*", "accept", 
                "comment", "warppool-allow-docker"
            ])

            # Allow Output (add to end of chain with comment)
            await cls._run_command([
                "nft", "add", "rule", "inet", "cloudflare-warp", "output", 
                "oif", interface, "accept", 
                "comment", "warppool-controller-output"
            ])
            
            # Allow Input on specific ports
            for port in ports:
                # TCP rule
                await cls._run_command([
                    "nft", "add", "rule", "inet", "cloudflare-warp", "input", 
                    "iif", interface, "tcp", "dport", str(port), "accept", 
                    "comment", f"warppool-controller-tcp-{port}"
                ])
                
                # UDP rule
                await cls._run_command([
                    "nft", "add", "rule", "inet", "cloudflare-warp", "input", 
                    "iif", interface, "udp", "dport", str(port), "accept", 
                    "comment", f"warppool-controller-udp-{port}"
                ])
                
        except Exception as e:
            logger.error(f"Failed to apply nftables rules: {e}")
            raise

    @classmethod
    async def cleanup_nftables_rules(cls, interface: str, ports: list[int]):
        """
        Remove nftables rules using handle ID for precision.
        """
        import re
        
        if not shutil.which("nft"):
            return

        logger.info(f"Cleaning up nftables rules for {interface}")
        
        # Check if table exists
        rc, _, _ = await cls._run_command(["nft", "list", "table", "inet", "cloudflare-warp"])
        if rc != 0:
            return
        
        try:
            # Helper to delete rules by comment pattern
            async def delete_by_comment(chain: str, comment_regex: str):
                rc, stdout, _ = await cls._run_command(["nft", "-a", "list", "chain", "inet", "cloudflare-warp", chain])
                if rc == 0:
                    handles = re.findall(rf'comment "{comment_regex}".*?# handle (\d+)', stdout)
                    for handle in handles:
                        await cls._run_command(["nft", "delete", "rule", "inet", "cloudflare-warp", chain, "handle", handle])
                        logger.debug(f"Removed rule handle {handle} matching {comment_regex}")

            # 1. Clean up controller outputs
            await delete_by_comment("output", "warppool-controller-output")

            # 2. Clean up specific port rules
            for port in ports:
                await delete_by_comment("input", f"warppool-controller-tcp-{port}")
                await delete_by_comment("input", f"warppool-controller-udp-{port}")

            # 3. Clean up generic allowed rules (established/docker)
            await delete_by_comment("input", "warppool-allow-established")
            await delete_by_comment("input", "warppool-allow-docker")
            
            logger.info("nftables rules cleanup complete")
        except Exception as e:
            logger.error(f"Error during nftables cleanup: {e}")