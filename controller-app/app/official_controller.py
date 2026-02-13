# controller-app/app/official_controller.py
"""
OfficialController - WARP backend implementation using official Cloudflare client
Supports proxy mode and TUN mode with MASQUE / WireGuard protocols
"""
import asyncio
import logging
import os
import json
from typing import Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


from .linux_tun_manager import LinuxTunManager

class OfficialController:
    """Control official Cloudflare WARP client (proxy + TUN modes)"""

    # Class-level status cache
    _status_cache = None
    _status_cache_time = 0
    _STATUS_CACHE_TTL = 8  # seconds

    def __init__(self, socks5_port: int = 1080):
        self.socks5_port = socks5_port
        self.mute_backend_logs = False
        self.preferred_protocol = "masque"  # 'masque' or 'wireguard' (wireguard only in TUN)
        self._mode = os.getenv("WARP_MODE", "proxy")  # 'proxy' or 'tun'
        self._cached_ip_info = None
        self._cache_time: float = 0
        self._cache_ttl: float = 120
        
        # TUN routing state
        self._tun_manager = LinuxTunManager()
        self._split_tunnel_cidrs: list[str] = []

    async def _run_command(self, command: str, timeout=None):
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

    # ------------------------------------------------------------------
    # Mode management
    # ------------------------------------------------------------------

    @property
    def mode(self) -> str:
        return self._mode

    async def set_mode(self, mode: str) -> bool:
        """Switch between proxy and tun mode."""
        if mode not in ("proxy", "tun"):
            logger.error(f"Invalid mode: {mode}")
            return False
            
        # Docker restriction for TUN mode
        if mode == "tun" and self._tun_manager.is_docker():
            logger.error("TUN mode is not allowed inside Docker environment")
            return False

        if mode == self._mode:
            logger.info(f"Already in {mode} mode")
            return True

        previous_mode = self._mode
        logger.info(f"Switching official mode from {previous_mode} to {mode}")

        # WireGuard only valid in TUN mode
        if mode == "proxy" and self.preferred_protocol == "wireguard":
            logger.info("Resetting protocol to MASQUE (WireGuard only in TUN mode)")
            self.preferred_protocol = "masque"

        # Disconnect and clean up resources from previous mode
        await self.disconnect()
        
        # Extra cleanup when switching FROM TUN mode
        if previous_mode == "tun":
            logger.info("Cleaning up TUN mode resources...")
            await self._cleanup_tun_routing()
            await asyncio.sleep(1)
        
        await asyncio.sleep(2)
        self._mode = mode
        os.environ["WARP_MODE"] = mode
        self._invalidate_status_cache()
        logger.info(f"Mode switched to {mode}, ready to connect")
        return True

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    async def execute_command(self, command: str):
        """Execute warp-cli command"""
        try:
            rc, stdout, stderr = await self._run_command(command, timeout=10)
            if rc != 0:
                logger.error(f"Command '{command}' failed: {stderr.strip()}")
                return None
            return stdout.strip()
        except Exception as e:
            logger.error(f"Error executing '{command}': {e}")
            return None

    async def _is_port_open(self, port: int) -> bool:
        try:
            rc, stdout, _ = await self._run_command(f"ss -lnt sport = :{port}")
            return f":{port}" in stdout
        except Exception:
            return False

    async def _is_daemon_responsive(self) -> bool:
        """Check if warp-svc is running AND responsive"""
        try:
            rc, stdout, _ = await self._run_command("supervisorctl status warp-svc")
            if rc != 0 or "RUNNING" not in stdout:
                return False
            
            # Use a short timeout for responsiveness check
            rc, _, _ = await self._run_command("warp-cli --accept-tos status", timeout=2)
            return rc == 0
        except Exception:
            return False

    async def _check_daemon_running(self) -> bool:
        return await self._is_daemon_responsive()

    # ------------------------------------------------------------------
    # Connect / Disconnect
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        """Connect to WARP in current mode"""
        if self._mode == "tun":
            return await self._connect_tun()
        return await self._connect_proxy()

    async def _connect_proxy(self) -> bool:
        """Connect in proxy mode"""
        # Ensure registration exists first
        if not os.path.exists("/var/lib/cloudflare-warp/reg.json"):
            logger.info("No registration found, attempting to register...")
            await self.execute_command("warp-cli --accept-tos registration new")
            
        if not await self._is_daemon_responsive():
            logger.info("Daemon not ready, restarting services...")
            await self._stop_services()
            if not await self._start_services_proxy():
                logger.error("Failed to start official WARP services (proxy)")
                return False

        await self._ensure_socat()

        logger.info("Connecting WARP (official, proxy mode)...")
        
        # Reset mode first to ensure clean state
        await self.execute_command("warp-cli --accept-tos disconnect")
        
        # Configure
        await self.execute_command("warp-cli --accept-tos mode proxy")
        await self.execute_command("warp-cli --accept-tos proxy port 40001")
        await self.execute_command("warp-cli --accept-tos tunnel protocol set MASQUE")
        
        # Connect
        res = await self.execute_command("warp-cli --accept-tos connect")
        if res and "Error" in res:
             logger.error(f"Connect command returned error: {res}")

        await asyncio.sleep(2)

        if await self.wait_for_status("connected", timeout=30): # Reduced timeout for faster feedback
            self.mute_backend_logs = True
            self._invalidate_status_cache()
            logger.info("Official WARP proxy connection successful")
            return True

        # Diagnostic log
        status = await self.execute_command("warp-cli --accept-tos status")
        logger.error(f"Official WARP proxy connection failed. Status: {status}")
        return False

    async def _connect_tun(self) -> bool:
        """Connect in TUN mode (full tunnel via virtual interface)"""
        if os.name != 'posix':
             logger.error("TUN mode is only supported on Linux/Unix systems")
             return False

        if not await self._is_daemon_responsive():
            logger.info("Daemon not ready, restarting services...")
            await self._stop_services()
            if not await self._start_services_tun():
                logger.error("Failed to start official WARP services (TUN)")
                return False

        logger.info("Connecting WARP (official, TUN mode)...")
        await self.execute_command("warp-cli --accept-tos mode warp")

        # Set tunnel protocol (WireGuard or MASQUE)
        proto_name = "WireGuard" if self.preferred_protocol == "wireguard" else "MASQUE"
        await self.execute_command(f"warp-cli --accept-tos tunnel protocol set {proto_name}")

        await self.execute_command("warp-cli --accept-tos connect")

        await asyncio.sleep(2)

        if await self.wait_for_status("connected", timeout=600):
            self.mute_backend_logs = True
            self._invalidate_status_cache()
            logger.info("Official WARP TUN connection successful")
            
            # Apply Split Tunneling so panel/management traffic bypasses WARP TUN
            await self._apply_tun_routing()
            return True

        logger.error("Official WARP TUN connection failed")
        return False

    async def disconnect(self) -> bool:
        """Disconnect from WARP and stop services"""
        logger.info(f"Disconnecting WARP (official, {self._mode} mode)...")
        self._cached_ip_info = None
        self._invalidate_status_cache()

        # Clean up TUN routing before disconnecting
        if self._mode == "tun":
            logger.info("Cleaning up TUN routing and firewall rules...")
            await self._cleanup_tun_routing()

        try:
            await self.execute_command("warp-cli --accept-tos disconnect")
            await self.wait_for_status("disconnected", timeout=5)
        except Exception:
            pass

        await self._stop_services()
        logger.info("WARP disconnected successfully")
        return True

    # ------------------------------------------------------------------
    # Service management
    # ------------------------------------------------------------------

    async def _start_services_proxy(self) -> bool:
        """Start services for proxy mode"""
        try:
            logger.info("Starting background services (proxy mode)...")
            self.mute_backend_logs = False

            try:
                rc, _, _ = await self._run_command("supervisorctl start warp-svc")
                if rc != 0:
                     logger.error("Failed to start warp-svc")
                     return False
            except Exception:
                logger.error("Failed to start warp-svc")
                return False

            await asyncio.sleep(3)
            await self._ensure_socat()

            for _ in range(30):
                if await self._is_daemon_responsive():
                    logger.info("warp-svc is ready")
                    return await self._configure_warp_proxy()
                await asyncio.sleep(1)

            logger.error("Timed out waiting for warp-svc")
            return False
        except Exception as e:
            logger.error(f"Error starting proxy services: {e}")
            return False

    async def _start_services_tun(self) -> bool:
        """Start services for TUN mode"""
        try:
            logger.info("Starting background services (TUN mode)...")
            self.mute_backend_logs = False

            try:
                rc, _, _ = await self._run_command("supervisorctl start warp-svc")
                if rc != 0:
                     logger.error("Failed to start warp-svc")
                     return False
            except Exception:
                logger.error("Failed to start warp-svc")
                return False

            await asyncio.sleep(3)

            for _ in range(30):
                if await self._is_daemon_responsive():
                    logger.info("warp-svc is ready")
                    return await self._configure_warp_tun()
                await asyncio.sleep(1)

            logger.error("Timed out waiting for warp-svc")
            return False
        except Exception as e:
            logger.error(f"Error starting TUN services: {e}")
            return False

    async def _configure_warp_proxy(self) -> bool:
        """Apply WARP configuration for proxy mode"""
        try:
            if not os.path.exists("/var/lib/cloudflare-warp/reg.json"):
                logger.info("Registering new WARP account...")
                await self.execute_command("warp-cli --accept-tos registration delete")
                await self.execute_command("warp-cli --accept-tos registration new")

            await self.execute_command("warp-cli --accept-tos tunnel protocol set MASQUE")
            await self.execute_command("warp-cli --accept-tos mode proxy")
            await self.execute_command("warp-cli --accept-tos proxy port 40001")
            return True
        except Exception as e:
            logger.error(f"Error configuring WARP proxy: {e}")
            return False

    async def _configure_warp_tun(self) -> bool:
        """Apply WARP configuration for TUN mode"""
        try:
            if not os.path.exists("/var/lib/cloudflare-warp/reg.json"):
                logger.info("Registering new WARP account...")
                await self.execute_command("warp-cli --accept-tos registration delete")
                await self.execute_command("warp-cli --accept-tos registration new")

            proto_name = "WireGuard" if self.preferred_protocol == "wireguard" else "MASQUE"
            await self.execute_command(f"warp-cli --accept-tos tunnel protocol set {proto_name}")
            await self.execute_command("warp-cli --accept-tos mode warp")
            return True
        except Exception as e:
            logger.error(f"Error configuring WARP TUN: {e}")
            return False

    async def _stop_services(self):
        """Stop all possible services (safe for both modes)"""
        logger.info("Stopping official services...")
        try:
            await self._run_command("supervisorctl stop socat")
            await self._run_command("supervisorctl stop warp-svc")
        except Exception as e:
            logger.error(f"Error stopping services: {e}")

    # ------------------------------------------------------------------
    # Auxiliary proxy helpers
    # ------------------------------------------------------------------

    async def _ensure_socat(self):
        """Ensure socat service is running with the correct SOCKS5 port (proxy mode only)"""
        if self._mode != "proxy":
            return

        # Update supervisor config if port differs from default
        await self._update_supervisor_socat_port()

        sys_active = False
        try:
            rc, stdout, _ = await self._run_command("supervisorctl status socat")
            sys_active = rc == 0 and "RUNNING" in stdout
        except Exception:
            pass

        port_open = await self._is_port_open(self.socks5_port)

        if sys_active and port_open:
            return

        logger.info(f"Starting socat service (port {self.socks5_port})...")
        try:
            # Stop first to pick up config changes
            await self._run_command("supervisorctl stop socat")
            await asyncio.sleep(0.3)
            await self._run_command("supervisorctl start socat")
            await asyncio.sleep(1)
            if not await self._is_port_open(self.socks5_port):
                logger.warning(f"Socat started but port {self.socks5_port} not listening yet")
                await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Error starting socat: {e}")

    async def _update_supervisor_socat_port(self):
        """Update the socat supervisor config to use the current socks5_port."""
        import re as _re
        conf_paths = [
            "/etc/supervisor/conf.d/supervisord.conf",
            "/etc/supervisor/conf.d/warppool.conf",
        ]
        for conf_path in conf_paths:
            if not os.path.isfile(conf_path):
                continue
            try:
                with open(conf_path, "r") as f:
                    content = f.read()

                new_cmd = f"command=/usr/bin/socat TCP-LISTEN:{self.socks5_port},reuseaddr,bind=0.0.0.0,fork TCP:127.0.0.1:40001"
                updated = _re.sub(
                    r"command=/usr/bin/socat TCP-LISTEN:\d+,reuseaddr,bind=0\.0\.0\.0,fork TCP:127\.0\.0\.1:40001",
                    new_cmd,
                    content,
                )
                if updated != content:
                    with open(conf_path, "w") as f:
                        f.write(updated)
                    await self._run_command("supervisorctl reread")
                    await self._run_command("supervisorctl update")
                    logger.info(f"Updated socat supervisor config to port {self.socks5_port}")
            except Exception as e:
                logger.warning(f"Failed to update socat config in {conf_path}: {e}")

    # ------------------------------------------------------------------
    # TUN routing helpers (Delegated to LinuxTunManager)
    # ------------------------------------------------------------------

    async def _apply_tun_routing(self):
        """Use warp-cli Split Tunneling to exclude panel/management traffic from WARP tunnel."""
        try:
            cidrs_to_exclude = []

            # 1. 获取服务器自身 IP，排除出隧道（确保面板可访问）
            server_ip = await self._tun_manager.get_server_ip()
            if server_ip:
                cidrs_to_exclude.append(f"{server_ip}/32")

            # 2. 获取 SSH 客户端 IP，排除出隧道（防止 SSH 断连）
            ssh_ip = await self._tun_manager.get_ssh_client_ip()
            if ssh_ip:
                cidrs_to_exclude.append(f"{ssh_ip}/32")

            # 3. 排除常见局域网网段
            lan_cidrs = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
            for cidr in lan_cidrs:
                cidrs_to_exclude.append(cidr)

            # 4. 去重
            cidrs_to_exclude = list(dict.fromkeys(cidrs_to_exclude))

            # 5. 批量添加到 Split Tunneling
            await self._tun_manager.setup_split_tunnel_bypass(cidrs_to_exclude)
            self._split_tunnel_cidrs = cidrs_to_exclude

            logger.info(f"Split Tunneling configured: excluded {len(cidrs_to_exclude)} CIDRs")
        except Exception as e:
            logger.error(f"Failed to configure Split Tunneling: {e}")

    async def _cleanup_tun_routing(self):
        """Remove Split Tunneling exclusion rules added by _apply_tun_routing."""
        if self._split_tunnel_cidrs:
            await self._tun_manager.cleanup_split_tunnel_bypass(self._split_tunnel_cidrs)
            self._split_tunnel_cidrs = []
        logger.info("Split Tunneling cleanup complete")

    # ------------------------------------------------------------------
    # Connectivity checks
    # ------------------------------------------------------------------

    async def is_connected(self) -> bool:
        """Check if WARP is connected"""
        if not await self._check_daemon_running():
            return False
        try:
            rc, stdout, _ = await self._run_command("warp-cli --accept-tos status", timeout=3)
            if rc != 0:
                return False
            output = stdout.lower()
            return "connected" in output and "disconnected" not in output
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Status / IP Info
    # ------------------------------------------------------------------

    async def get_status(self) -> Dict:
        now = asyncio.get_running_loop().time()
        if (
            OfficialController._status_cache is not None
            and now - OfficialController._status_cache_time < OfficialController._STATUS_CACHE_TTL
        ):
            return OfficialController._status_cache

        status = await self._get_status_uncached()
        OfficialController._status_cache = status
        OfficialController._status_cache_time = now
        return status

    def _invalidate_status_cache(self):
        OfficialController._status_cache = None
        OfficialController._status_cache_time = 0

    async def _get_status_uncached(self) -> Dict:
        base_status = {
            "backend": "official",
            "status": "disconnected",
            "ip": "Unknown",
            "location": "Unknown",
            "city": "Unknown",
            "country": "Unknown",
            "isp": "Cloudflare WARP",
            "warp_protocol": self.preferred_protocol.upper(),
            "warp_mode": self._mode,
            "connection_time": "Unknown",
            "network_type": "Unknown",
            "proxy_address": f"socks5://127.0.0.1:{self.socks5_port}",

            "details": {},
        }

        if not await self.is_connected():
            self._cached_ip_info = None
            return base_status

        base_status["status"] = "connected"

        now = asyncio.get_running_loop().time()
        if self._cached_ip_info and (now - self._cache_time) < self._cache_ttl:
            base_status.update(self._cached_ip_info)
            return base_status

        ip_info = await self._fetch_ip_info()
        if ip_info:
            self._cached_ip_info = ip_info
            self._cache_time = now
            base_status.update(ip_info)
        elif self._cached_ip_info:
            base_status.update(self._cached_ip_info)

        return base_status

    async def _fetch_ip_info(self) -> dict:
        """Fetch IP info. Proxy mode: via SOCKS5. TUN mode: direct."""
        try:
            if self._mode == "tun":
                cmd = "curl -s --max-time 5 \"http://ip-api.com/json/?fields=status,message,query,country,city,isp\""
            else:
                cmd = f"curl -x socks5h://127.0.0.1:{self.socks5_port} -s --max-time 5 \"http://ip-api.com/json/?fields=status,message,query,country,city,isp\""

            rc, stdout, _ = await self._run_command(cmd, timeout=8)

            if rc == 0 and stdout:
                data = json.loads(stdout)
                if data.get("status") == "success":
                    isp_value = data.get("isp") or "Cloudflare WARP"
                    return {
                        "ip": data.get("query") or "Unknown",
                        "country": data.get("country") or "Unknown",
                        "city": data.get("city") or "Unknown",
                        "location": data.get("country") or "Unknown",
                        "isp": isp_value,
                        "details": {"isp": isp_value},
                    }
                else:
                    logger.warning("IP API returned failure: %s", data.get("message"))
        except Exception as e:
            logger.error(f"Error getting IP info: {e}")

        return None

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    async def wait_for_status(self, target_status: str, timeout: int = 15) -> bool:
        start_time = asyncio.get_running_loop().time()
        while asyncio.get_running_loop().time() - start_time < timeout:
            connected = await self.is_connected()
            if target_status == "connected" and connected:
                self._invalidate_status_cache()
                return True
            elif target_status == "disconnected" and not connected:
                self._invalidate_status_cache()
                return True
            await asyncio.sleep(2)
        return False

    async def rotate_ip_simple(self) -> bool:
        logger.info("Rotating IP (official: disconnect + reconnect)...")
        await self.disconnect()
        await asyncio.sleep(2)
        if await self.connect():
            return await self.wait_for_status("connected", timeout=15)
        return False

    async def set_custom_endpoint(self, endpoint: str) -> bool:
        try:
            if not endpoint:
                logger.info("Resetting custom endpoint (official)...")
                cmd = "warp-cli --accept-tos tunnel endpoint reset"
            else:
                logger.info(f"Setting custom endpoint to {endpoint} (official)...")
                cmd = f"warp-cli --accept-tos tunnel endpoint set {endpoint}"

            await self.execute_command(cmd)

            try:
                await self.execute_command("warp-cli --accept-tos disconnect")
                await self.wait_for_status("disconnected", timeout=5)
            except Exception:
                pass
            await asyncio.sleep(10)
            return await self.connect()
        except Exception as e:
            logger.error(f"Failed to set custom endpoint: {e}")
            return False

    async def set_protocol(self, protocol: str) -> bool:
        """Set WARP tunnel protocol. WireGuard only available in TUN mode."""
        protocol = (protocol or "masque").lower()

        if protocol not in ("masque", "wireguard"):
            logger.error(f"Invalid protocol: {protocol}. Use 'masque' or 'wireguard'")
            return False

        if protocol == "wireguard" and self._mode != "tun":
            logger.error("WireGuard is only available in TUN mode")
            return False

        if self.preferred_protocol == protocol:
            logger.info(f"Protocol already set to {protocol}")
            return True

        self.preferred_protocol = protocol
        self._invalidate_status_cache()
        self.mute_backend_logs = False

        try:
            logger.info(f"Switching protocol to {protocol.upper()}...")

            try:
                await self.execute_command("warp-cli --accept-tos disconnect")
                await self.wait_for_status("disconnected", timeout=5)
            except Exception:
                pass

            proto_name = "WireGuard" if protocol == "wireguard" else "MASQUE"
            cmd = f"warp-cli --accept-tos tunnel protocol set {proto_name}"
            res = await self.execute_command(cmd)
            if res is None:
                logger.error("Failed to update tunnel protocol")
                return False

            await self._stop_services()
            await asyncio.sleep(2)

            return await self.connect()
        except Exception as e:
            logger.error(f"Failed to set protocol: {e}")
            return False

    # ------------------------------------------------------------------
    # Geo helpers
    # ------------------------------------------------------------------
    # ... (Geo helpers are purely functional, no async needed, but usually not called directly async)
    # They are just string lookups. I will leave them as sync methods.
    
    def _get_city_from_colo(self, colo: str) -> str:
        city_map = {
            "LAX": "Los Angeles", "SJC": "San Jose", "ORD": "Chicago",
            "IAD": "Ashburn", "EWR": "Newark", "MIA": "Miami",
            "DFW": "Dallas", "SEA": "Seattle", "ATL": "Atlanta",
            "LHR": "London", "CDG": "Paris", "FRA": "Frankfurt",
            "AMS": "Amsterdam", "SIN": "Singapore", "HKG": "Hong Kong",
            "NRT": "Tokyo", "SYD": "Sydney", "ICN": "Seoul",
            "BOM": "Mumbai", "GRU": "São Paulo",
        }
        return city_map.get(colo.upper(), colo)

    def _get_country_name(self, loc_code: str) -> str:
        country_map = {
            "US": "United States", "CN": "China", "JP": "Japan",
            "GB": "United Kingdom", "DE": "Germany", "FR": "France",
            "CA": "Canada", "AU": "Australia", "SG": "Singapore",
            "IN": "India", "BR": "Brazil", "KR": "South Korea",
            "NL": "Netherlands", "SE": "Sweden", "IT": "Italy",
            "ES": "Spain", "RU": "Russia", "HK": "Hong Kong",
            "TW": "Taiwan",
        }
        return country_map.get(loc_code.upper(), loc_code)

