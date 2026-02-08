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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class UsqueController:
    """Control usque MASQUE WARP client (proxy + TUN modes)"""

    # Class-level status cache
    _status_cache = None
    _status_cache_time = 0
    _STATUS_CACHE_TTL = 8  # seconds

    def __init__(self, config_path="/var/lib/warp/config.json", socks5_port=1080, http_port=8080):
        self.config_path = config_path
        self.socks5_port = socks5_port
        self.http_port = http_port
        self.process: Optional[subprocess.Popen] = None
        self._cached_ip_info: Optional[Dict] = None
        self._cache_time: float = 0
        self._cache_ttl: float = 120  # Cache IP info for 120 seconds
        self._mode = os.getenv("WARP_MODE", "proxy")  # 'proxy' or 'tun'

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
                process = subprocess.Popen(
                    ["usque", "register"],
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
        """Start usque TUN mode via supervisor"""
        try:
            logger.info("Starting usque service (TUN mode)...")
            subprocess.run(["supervisorctl", "start", "usque-tun"], check=True)

            logger.info("Waiting for usque TUN to become ready...")
            for _ in range(20):
                if self._is_tun_connected():
                    logger.info("usque TUN started successfully")
                    self._start_tun_proxy()
                    return True
                time.sleep(1)

            logger.error("usque TUN failed to start (timeout)")
            return False
        except Exception as e:
            logger.error(f"Failed to start usque TUN: {e}")
            return False

    def disconnect(self) -> bool:
        """Stop usque (both modes)"""
        try:
            logger.info(f"Stopping usque service ({self._mode} mode)...")

            if self._mode == "tun":
                subprocess.run(["supervisorctl", "stop", "tun-proxy"], check=False)
                subprocess.run(["supervisorctl", "stop", "usque-tun"], check=False)
            else:
                subprocess.run(["supervisorctl", "stop", "http-proxy"], check=False)
                subprocess.run(["supervisorctl", "stop", "usque"], check=False)

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

    def _start_tun_proxy(self):
        """Start SOCKS5 + HTTP proxy for TUN mode"""
        try:
            res = subprocess.run(
                ["supervisorctl", "status", "tun-proxy"],
                capture_output=True, text=True,
            )
            if "RUNNING" in res.stdout:
                return
            logger.info("Starting TUN proxy (SOCKS5 + HTTP)...")
            subprocess.run(["supervisorctl", "start", "tun-proxy"], check=False)
            for _ in range(10):
                if self._is_port_open(self.socks5_port):
                    break
                time.sleep(0.5)
        except Exception as e:
            logger.warning(f"Failed to start TUN proxy: {e}")

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
        """Check if usque TUN mode is running"""
        try:
            res = subprocess.run(
                ["supervisorctl", "status", "usque-tun"],
                capture_output=True, text=True,
            )
            if res.returncode != 0 or "RUNNING" not in res.stdout:
                return False
        except Exception:
            return False
        # Trust supervisor status; optionally verify TUN interface
        return True

    def is_connected(self) -> bool:
        """Check if usque is running in current mode"""
        if self._mode == "tun":
            return self._is_tun_connected()
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
        """Fetch IP info. Proxy mode: via SOCKS5. TUN mode: direct (all traffic tunnelled)."""
        try:
            if self._mode == "tun":
                cmd = [
                    "curl", "-s", "--max-time", "5",
                    "http://ip-api.com/json/?fields=status,message,query,country,city,isp",
                ]
            else:
                cmd = [
                    "curl",
                    "-x", f"socks5h://127.0.0.1:{self.socks5_port}",
                    "-s", "--max-time", "5",
                    "http://ip-api.com/json/?fields=status,message,query,country,city,isp",
                ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=8)

            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout)
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
        except subprocess.TimeoutExpired:
            logger.warning("Timeout getting IP info")
        except Exception as e:
            logger.error(f"Error getting IP info: {e}")

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
