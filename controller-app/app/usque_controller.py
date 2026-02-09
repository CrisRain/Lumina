# controller-app/app/usque_controller.py
"""
UsqueController - WARP backend implementation using usque
Supports both proxy mode (SOCKS5) and TUN mode
"""
import subprocess
import logging
import psutil
import time
import json
import os
from typing import Optional, Dict
from .kernel_version_manager import KernelVersionManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


from .linux_tun_manager import LinuxTunManager

class UsqueController:
    """Control usque MASQUE WARP client (proxy + TUN modes)"""

    # Class-level status cache
    _status_cache = None
    _status_cache_time = 0
    _STATUS_CACHE_TTL = 8  # seconds

    def __init__(self, config_path=None, socks5_port=1080, http_port=8080):
        self.config_path = config_path or os.getenv("USQUE_CONFIG_PATH", "/var/lib/warp/config.json")
        self.socks5_port = socks5_port
        self.http_port = http_port
        self.process: Optional[subprocess.Popen] = None
        self._cached_ip_info: Optional[Dict] = None
        self._cache_time: float = 0
        self._cache_ttl: float = 120  # Cache IP info for 120 seconds
        self._mode = os.getenv("WARP_MODE", "proxy")  # 'proxy' or 'tun'
        
        # TUN State
        self._tun_manager = LinuxTunManager()
        self._saved_gw = None
        self._saved_iface = None
        self._saved_ip = None

    # ------------------------------------------------------------------
    # Mode management
    # ------------------------------------------------------------------

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> bool:
        """Switch between proxy and tun mode. Disconnects first."""
        if mode not in ("proxy", "tun"):
            logger.error(f"Invalid mode: {mode}. Use 'proxy' or 'tun'")
            return False
        
        # Docker restriction for TUN mode
        if mode == "tun" and self._tun_manager.is_docker():
            logger.error("TUN mode is not allowed inside Docker environment")
            return False

        if mode == self._mode:
            logger.info(f"Already in {mode} mode")
            return True

        logger.info(f"Switching usque mode from {self._mode} to {mode}")
        self.disconnect()
        time.sleep(2)
        self._mode = mode
        os.environ["WARP_MODE"] = mode
        self._invalidate_status_cache()
        return True

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def initialize(self) -> bool:
        """Initialize usque backend (register if needed)"""
        try:
            config_dir = os.path.dirname(self.config_path)
            os.makedirs(config_dir, exist_ok=True)

            if not os.path.exists(self.config_path):
                logger.info("Config not found, registering new usque account...")
                
                binary_path = KernelVersionManager.get_instance().get_binary_path('usque')
                process = subprocess.Popen(
                    [binary_path, "register"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=config_dir,
                )
                stdout, stderr = process.communicate(input="y\n")

                if process.returncode == 0:
                    logger.info("usque registration successful")
                    return True
                else:
                    logger.error(f"usque registration failed: {stderr}")
                    return False
            return True
        except Exception as e:
            logger.error(f"Error initializing usque: {e}")
            return False

    # ------------------------------------------------------------------
    # Connect / Disconnect
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Start usque in the current mode"""
        if not self.initialize():
            logger.error("Failed to initialize usque backend")
            return False

        if self.is_connected():
            logger.info(f"usque already running in {self._mode} mode")
            return True

        if self._mode == "tun":
            return self._connect_tun()
        else:
            return self._connect_proxy()

    def _connect_proxy(self) -> bool:
        """Start usque SOCKS5 proxy via supervisor"""
        try:
            logger.info("Starting usque service (proxy mode)...")
            # Ensure clean state (clear FATAL/BACKOFF from previous runs)
            subprocess.run(["supervisorctl", "stop", "usque"], check=False)
            time.sleep(0.5)
            subprocess.run(["supervisorctl", "start", "usque"], check=True)

            logger.info("Waiting for usque proxy to become ready...")
            for _ in range(15):
                if self._is_proxy_connected():
                    logger.info("usque proxy started successfully")
                    self._start_http_proxy()
                    return True
                time.sleep(1)

            logger.error("usque proxy failed to start (timeout)")
            return False
        except Exception as e:
            logger.error(f"Failed to start usque proxy: {e}")
            return False

    def _connect_tun(self) -> bool:
        """Start usque nativetun + set up routing + start gost proxy listeners."""
        # Linux only check
        if os.name != 'posix':
             logger.error("TUN mode is only supported on Linux/Unix systems")
             return False

        try:
            logger.info("Starting usque service (TUN mode: nativetun)...")
            # Ensure clean state
            subprocess.run(["supervisorctl", "stop", "usque"], check=False)
            subprocess.run(["supervisorctl", "stop", "usque-tun"], check=False)
            subprocess.run(["supervisorctl", "stop", "tun-proxy"], check=False)
            time.sleep(0.5)

            # Save original default route before TUN modifies anything
            self._saved_gw, self._saved_iface, self._saved_ip = self._tun_manager.get_default_route()

            # Start usque nativetun (creates tun0 interface)
            subprocess.run(["supervisorctl", "start", "usque-tun"], check=True)

            logger.info("Waiting for TUN interface to come up...")
            for _ in range(20):
                if self._tun_manager.tun_interface_exists():
                    break
                time.sleep(1)
            else:
                logger.error("TUN interface failed to appear (timeout)")
                return False

            # Set up routing with policy-based split
            self._setup_tun_routing()

            # Start gost as plain SOCKS5 + HTTP listener;
            # since default route is now through tun0, traffic goes through WARP
            # logger.info("Starting tun-proxy (gost SOCKS5 + HTTP)...")
            # subprocess.run(["supervisorctl", "start", "tun-proxy"], check=True)

            logger.info("usque TUN mode started successfully (Proxy listeners disabled)")
            return True

            # for _ in range(10):
            #     if self._is_port_open(self.socks5_port):
            #         logger.info("usque TUN mode started successfully")
            #         return True
            #     time.sleep(1)

            # logger.error("tun-proxy failed to start (timeout)")
            # return False
        except Exception as e:
            logger.error(f"Failed to start usque TUN: {e}")
            return False

    def disconnect(self) -> bool:
        """Stop all usque services (both modes, prevents stale FATAL states)"""
        try:
            logger.info("Stopping usque services...")
            # Always stop ALL services to avoid leftover FATAL/BACKOFF states
            subprocess.run(["supervisorctl", "stop", "tun-proxy"], check=False)
            subprocess.run(["supervisorctl", "stop", "http-proxy"], check=False)
            subprocess.run(["supervisorctl", "stop", "usque-tun"], check=False)
            subprocess.run(["supervisorctl", "stop", "usque"], check=False)

            # Clean up TUN routing if tun0 was active
            self._cleanup_tun_routing()

            self.process = None
            self._invalidate_status_cache()
            return True
        except Exception as e:
            logger.error(f"Error stopping usque: {e}")
            return False

    # ------------------------------------------------------------------
    # Auxiliary proxy helpers
    # ------------------------------------------------------------------

    def _start_http_proxy(self):
        """Start HTTP proxy that chains through SOCKS5 (proxy mode)"""
        try:
            res = subprocess.run(
                ["supervisorctl", "status", "http-proxy"],
                capture_output=True, text=True,
            )
            if "RUNNING" in res.stdout:
                return
            logger.info("Starting HTTP proxy (proxy mode)...")
            subprocess.run(["supervisorctl", "start", "http-proxy"], check=False)
        except Exception as e:
            logger.warning(f"Failed to start HTTP proxy: {e}")

    # ------------------------------------------------------------------
    # TUN routing helpers (Delegated to LinuxTunManager)
    # ------------------------------------------------------------------

    def _get_warp_endpoint(self) -> Optional[str]:
        """Read endpoint_v4 from usque config.json."""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r") as f:
                    config = json.load(f)
                return config.get("endpoint_v4")
        except Exception as e:
            logger.warning(f"Could not read endpoint from config: {e}")
        return None

    def _setup_tun_routing(self):
        """Set up policy-based routing for usque nativetun."""
        tun_name = self._tun_manager.get_tun_interface_name() or "tun0"
        endpoint = self._get_warp_endpoint()

        # 1. Policy routing: response traffic from our IP uses original gateway
        if self._saved_gw and self._saved_iface and self._saved_ip:
            self._tun_manager.setup_bypass_routing(self._saved_gw, self._saved_iface, self._saved_ip)
        else:
            logger.warning("Missing orig_gw/iface/ip, skipping policy route (panel may be inaccessible in TUN mode)")

        # 2. Route WARP endpoint through original gateway (prevent routing loop)
        if self._saved_gw and self._saved_iface and endpoint:
            self._tun_manager.add_static_route(f"{endpoint}/32", self._saved_gw, self._saved_iface)

        # 3. Set default route through TUN
        self._tun_manager.set_default_interface(tun_name)
        logger.info(f"TUN routing configured: default via {tun_name}")

    def _cleanup_tun_routing(self):
        """Remove TUN routing: policy rule, table 100, endpoint route."""
        # Cleanup bypass routing
        self._tun_manager.cleanup_bypass_routing(self._saved_ip)

        # Remove endpoint route
        endpoint = self._get_warp_endpoint()
        if endpoint:
            self._tun_manager.delete_static_route(f"{endpoint}/32")
        
        # Reset saved state
        self._saved_gw = None
        self._saved_iface = None
        self._saved_ip = None

    # ------------------------------------------------------------------
    # Connectivity checks
    # ------------------------------------------------------------------

    def _is_port_open(self, port: int) -> bool:
        """Check if port is listening using ss"""
        try:
            result = subprocess.run(
                ["ss", "-lnt", f"sport = :{port}"],
                capture_output=True, text=True,
            )
            return f":{port}" in result.stdout
        except Exception:
            return False

    def _is_proxy_connected(self) -> bool:
        """Check if usque SOCKS5 proxy is running"""
        try:
            res = subprocess.run(
                ["supervisorctl", "status", "usque"],
                capture_output=True, text=True,
            )
            if res.returncode != 0 or "RUNNING" not in res.stdout:
                return False
        except Exception:
            return False
        return self._is_port_open(self.socks5_port)

    def _is_tun_connected(self) -> bool:
        """Check if usque nativetun is running and tun interface exists."""
        try:
            res = subprocess.run(
                ["supervisorctl", "status", "usque-tun"],
                capture_output=True, text=True,
            )
            if res.returncode != 0 or "RUNNING" not in res.stdout:
                return False
        except Exception:
            return False
        return self._tun_manager.tun_interface_exists()

    def is_connected(self) -> bool:
        """Check if usque is running in current mode"""
        if self._mode == "tun":
            # Just check tun interface exists, no proxy port check
            return self._tun_manager.tun_interface_exists()
        return self._is_proxy_connected()

    # ------------------------------------------------------------------
    # Status / IP Info
    # ------------------------------------------------------------------

    def get_status(self) -> Dict:
        """Get connection status and IP information (cached)"""
        now = time.time()
        if (
            UsqueController._status_cache is not None
            and now - UsqueController._status_cache_time < UsqueController._STATUS_CACHE_TTL
        ):
            return UsqueController._status_cache

        status = self._get_status_uncached()
        UsqueController._status_cache = status
        UsqueController._status_cache_time = now
        return status

    def _invalidate_status_cache(self):
        UsqueController._status_cache = None
        UsqueController._status_cache_time = 0

    def _get_status_uncached(self) -> Dict:
        base_status = {
            "backend": "usque",
            "status": "disconnected",
            "ip": "Unknown",
            "location": "Unknown",
            "city": "Unknown",
            "country": "Unknown",
            "isp": "Cloudflare WARP",
            "warp_protocol": "MASQUE",
            "warp_mode": self._mode,
            "connection_time": "Unknown",
            "network_type": "Unknown",
            "proxy_address": f"socks5://127.0.0.1:{self.socks5_port}",
            "http_proxy_address": f"http://127.0.0.1:{self.http_port}",
            "details": {},
        }

        if not self.is_connected():
            self._cached_ip_info = None
            return base_status

        base_status["status"] = "connected"

        now = time.time()
        if self._cached_ip_info and (now - self._cache_time) < self._cache_ttl:
            base_status.update(self._cached_ip_info)
            return base_status

        ip_info = self._fetch_ip_info()
        if ip_info:
            self._cached_ip_info = ip_info
            self._cache_time = now
            base_status.update(ip_info)
        elif self._cached_ip_info:
            base_status.update(self._cached_ip_info)

        return base_status

    def _fetch_ip_info(self) -> Optional[Dict]:
        """Fetch IP info. Proxy mode: via SOCKS5. TUN mode: direct (traffic goes through tun)."""
        
        # Try primary API first (ip-api.com)
        apis = [
            "http://ip-api.com/json/?fields=status,message,query,country,city,isp",
            "https://ipinfo.io/json",
            "https://ifconfig.me/all.json"
        ]
        
        for api_url in apis:
            try:
                cmd = ["curl", "-s", "--max-time", "5"]
                
                # Proxy configuration
                if self._mode == "proxy":
                     cmd.extend(["-x", f"socks5h://127.0.0.1:{self.socks5_port}"])
                
                cmd.append(api_url)
                
                logger.info(f"Fetching IP info from {api_url}...")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=8)

                if result.returncode == 0 and result.stdout:
                    # Try to parse as JSON
                    try:
                        data = json.loads(result.stdout)
                        
                        # Normalize data structure based on API
                        if "ip-api.com" in api_url:
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
                        elif "ipinfo.io" in api_url:
                            return {
                                "ip": data.get("ip") or "Unknown",
                                "country": data.get("country") or "Unknown",
                                "city": data.get("city") or "Unknown",
                                "location": data.get("country") or "Unknown",
                                "isp": data.get("org") or "Cloudflare WARP",
                                "details": {"isp": data.get("org")},
                            }
                        elif "ifconfig.me" in api_url:
                             return {
                                "ip": data.get("ip_addr") or "Unknown",
                                "country": "Unknown", # ifconfig.me doesn't give country in json easily?
                                "city": "Unknown",
                                "location": "Unknown",
                                "isp": "Cloudflare WARP",
                                "details": {},
                            }
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse JSON from {api_url}: {result.stdout[:100]}")
                        
            except Exception as e:
                logger.warning(f"Error fetching IP from {api_url}: {e}")
                
        logger.error("All IP fetch attempts failed")
        return None

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def wait_for_status(self, target_status: str, timeout: int = 15) -> bool:
        start_time = time.time()
        while time.time() - start_time < timeout:
            if target_status == "connected" and self.is_connected():
                self._invalidate_status_cache()
                return True
            elif target_status == "disconnected" and not self.is_connected():
                self._invalidate_status_cache()
                return True
            time.sleep(2)
        return False

    def rotate_ip_simple(self) -> bool:
        """Rotate IP by reconnecting"""
        logger.info("Rotating IP (disconnect + reconnect)...")
        self.disconnect()
        self.wait_for_status("disconnected", timeout=5)
        time.sleep(2)
        if self.connect():
            return self.wait_for_status("connected", timeout=15)
        return False

    def set_custom_endpoint(self, endpoint: str) -> bool:
        """Set custom endpoint in config.json and restart"""
        try:
            if not os.path.exists(self.config_path):
                logger.error("Config file not found")
                return False

            with open(self.config_path, "r") as f:
                config = json.load(f)

            if not endpoint:
                logger.info("Resetting custom endpoint (usque)...")
                config.pop("endpoint_v4", None)
            else:
                logger.info(f"Setting custom endpoint to {endpoint} (usque)...")
                config["endpoint_v4"] = endpoint

            with open(self.config_path, "w") as f:
                json.dump(config, f, indent=2)

            logger.info(f"Updated usque endpoint to: {endpoint}")
            self.disconnect()
            time.sleep(5)
            return self.connect()
        except Exception as e:
            logger.error(f"Failed to set custom endpoint: {e}")
            return False

    # ------------------------------------------------------------------
    # Geo helpers
    # ------------------------------------------------------------------

    def _get_city_from_colo(self, colo: str) -> str:
        city_map = {
            "LAX": "Los Angeles", "SJC": "San Jose", "ORD": "Chicago",
            "IAD": "Ashburn", "EWR": "Newark", "MIA": "Miami",
            "DFW": "Dallas", "SEA": "Seattle", "ATL": "Atlanta",
            "LHR": "London", "CDG": "Paris", "FRA": "Frankfurt",
            "AMS": "Amsterdam", "SIN": "Singapore", "HKG": "Hong Kong",
            "NRT": "Tokyo", "SYD": "Sydney", "ICN": "Seoul",
            "BOM": "Mumbai", "GRU": "São Paulo", "YVR": "Vancouver",
            "YYZ": "Toronto", "MEL": "Melbourne", "DXB": "Dubai",
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
            "TW": "Taiwan", "MX": "Mexico", "AR": "Argentina",
        }
        return country_map.get(loc_code.upper(), loc_code)
