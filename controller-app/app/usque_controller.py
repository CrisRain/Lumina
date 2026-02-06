# controller-app/app/usque_controller.py
"""
UsqueController - WARP backend implementation using usque
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
    """Control usque MASQUE WARP client"""
    
    # Class-level status cache
    _status_cache = None
    _status_cache_time = 0
    _STATUS_CACHE_TTL = 8  # seconds
    
    def __init__(self, config_path="/var/lib/warp/config.json", socks5_port=1080):
        self.config_path = config_path
        self.socks5_port = socks5_port
        self.process: Optional[subprocess.Popen] = None
        self._cached_ip_info: Optional[Dict] = None
        self._cache_time: float = 0
        self._cache_ttl: float = 120  # Cache IP info for 120 seconds (reduce proxy traffic)
    
    def initialize(self) -> bool:
        """Initialize usque backend (register if needed)"""
        import os
        try:
            # Create config dir
            config_dir = os.path.dirname(self.config_path)
            os.makedirs(config_dir, exist_ok=True)
            
            # Register if config doesn't exist
            if not os.path.exists(self.config_path):
                logger.info("Config not found, registering new usque account...")
                # Run usque register
                # input "y" to confirm license if needed, though 'usque register' usually just works or needs interactive.
                # entrypoint used: echo "y" | usque register
                process = subprocess.Popen(
                    ["usque", "register"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=config_dir # Run in dir so it might save there? entrypoint cd-ed there
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

    def connect(self) -> bool:
        """Start usque SOCKS5 proxy via systemd"""
        # Ensure initialized (registered)
        if not self.initialize():
            logger.error("Failed to initialize usque backend")
            return False

        if self.is_connected():
            logger.info("usque already running")
            return True
            
        try:
            logger.info("Starting usque service...")
            # Use systemctl to start service
            subprocess.run(["systemctl", "start", "usque"], check=True)
            
            # Wait for startup and readiness
            logger.info("Waiting for usque to become ready...")
            for i in range(15): # Wait up to 15 seconds
                if self.is_connected():
                    logger.info("usque started successfully")
                    return True
                time.sleep(1)
            
            logger.error("usque service failed to start or is inactive (timeout)")
            return False
        
        except Exception as e:
            logger.error(f"Failed to start usque: {e}")
            return False
    
    def disconnect(self) -> bool:
        """Stop usque via systemd"""
        try:
            logger.info("Stopping usque service...")
            subprocess.run(["systemctl", "stop", "usque"], check=False)
            self.process = None  # Clear legacy process handle if any
            self._invalidate_status_cache()
            return True
        except Exception as e:
            logger.error(f"Error stopping usque: {e}")
            return False
    
    def _is_port_open(self, port: int) -> bool:
        """Check if port is listening using ss"""
        try:
            # ss -lnt sport = :<port>
            # Use basic string matching for robustness
            result = subprocess.run(
                ["ss", "-lnt", f"sport = :{port}"],
                capture_output=True,
                text=True
            )
            return f":{port}" in result.stdout
        except Exception:
            return False

    def is_connected(self) -> bool:
        """Check if usque is running via systemd + port listening (lightweight)"""
        # 1. Check service status
        try:
            res = subprocess.run(
                ["systemctl", "is-active", "usque"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            if res.returncode != 0:
                return False
        except Exception:
            return False

        # 2. Check if port is listening
        return self._is_port_open(self.socks5_port)
    
    def get_status(self) -> Dict:
        """Get connection status and IP information (cached)"""
        now = time.time()
        if (UsqueController._status_cache is not None 
            and now - UsqueController._status_cache_time < UsqueController._STATUS_CACHE_TTL):
            return UsqueController._status_cache
        
        status = self._get_status_uncached()
        UsqueController._status_cache = status
        UsqueController._status_cache_time = now
        return status
    
    def _invalidate_status_cache(self):
        """Invalidate status cache after connect/disconnect"""
        UsqueController._status_cache = None
        UsqueController._status_cache_time = 0
    
    def _get_status_uncached(self) -> Dict:
        """Get connection status and IP information"""
        base_status = {
            "backend": "usque",
            "status": "disconnected",
            "ip": "Unknown",
            "location": "Unknown",
            "city": "Unknown",
            "country": "Unknown",
            "isp": "Cloudflare WARP",
            "warp_protocol": "MASQUE",
            "connection_time": "Unknown",
            "network_type": "Unknown",
            "proxy_address": f"socks5://127.0.0.1:{self.socks5_port}",
            "details": {}
        }
        
        if not self.is_connected():
            self._cached_ip_info = None
            return base_status
        
        base_status["status"] = "connected"
        
        # Use cached IP info if still fresh
        now = time.time()
        if self._cached_ip_info and (now - self._cache_time) < self._cache_ttl:
            base_status.update(self._cached_ip_info)
            return base_status
        
        # Fetch IP info through the proxy
        ip_info = self._fetch_ip_info()
        if ip_info:
            self._cached_ip_info = ip_info
            self._cache_time = now
            base_status.update(ip_info)
        elif self._cached_ip_info:
            # Use stale cache if fetch failed
            base_status.update(self._cached_ip_info)
        
        return base_status

    def _fetch_ip_info(self) -> Optional[Dict]:
        """Fetch IP information through the proxy.
        Uses the proxy to get the WARP exit IP (must go through tunnel).
        Cached for 120s to minimize traffic consumption.
        """
        try:
            result = subprocess.run(
                [
                    "curl",
                    "-x", f"socks5h://127.0.0.1:{self.socks5_port}",
                    "-s",
                    "--max-time", "5",
                    "http://ip-api.com/line/?fields=query,country,city,isp"
                ],
                capture_output=True,
                text=True,
                timeout=8
            )
            
            if result.returncode == 0 and result.stdout:
                # ip-api.com/line/ returns: query\ncountry\ncity\nisp
                lines = [l.strip() for l in result.stdout.strip().split('\n')]
                if len(lines) >= 4:
                    ip_data = {
                        "ip": lines[0] or "Unknown",
                        "country": lines[1] or "Unknown",
                        "city": lines[2] or "Unknown",
                        "location": lines[1] or "Unknown",
                        "details": {"isp": lines[3]}
                    }
                    return ip_data
                
        except subprocess.TimeoutExpired:
            logger.warning("Timeout getting IP info through proxy")
        except Exception as e:
            logger.error(f"Error getting IP info: {e}")
        
        return None
    
    def wait_for_status(self, target_status: str, timeout: int = 15) -> bool:
        """Wait for specific status using lightweight checks"""
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
        
        # Disconnect
        self.disconnect()
        self.wait_for_status("disconnected", timeout=5)
        
        # Wait a bit
        time.sleep(2)
        
        # Reconnect
        if self.connect():
            return self.wait_for_status("connected", timeout=15)
        
        return False
    
    def set_custom_endpoint(self, endpoint: str) -> bool:
        """Set custom endpoint in config.json and restart"""
        try:

            if not endpoint:
                # Reset
                logger.info("Resetting custom endpoint (official)...")
                cmd = "warp-cli --accept-tos tunnel endpoint reset"
            else:
                # Set
                logger.info(f"Setting custom endpoint to {endpoint} (official)...")
                cmd = f"warp-cli --accept-tos tunnel endpoint set {endpoint}"
            
            if not os.path.exists(self.config_path):
                logger.error("Config file not found")
                return False
            
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            
            if not endpoint:
                # Reset/Clear
                if "endpoint_v4" in config:
                    del config["endpoint_v4"]
            else:
                config["endpoint_v4"] = endpoint
            
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            logger.info(f"Updated usque endpoint to: {endpoint}")

            self.disconnect()
            time.sleep(5)
            return self.connect()
            
        except Exception as e:
            logger.error(f"Failed to set custom endpoint: {e}")
            return False


    def _get_city_from_colo(self, colo: str) -> str:
        """Map Cloudflare colo code to city name"""
        city_map = {
            "LAX": "Los Angeles", "SJC": "San Jose", "ORD": "Chicago",
            "IAD": "Ashburn", "EWR": "Newark", "MIA": "Miami",
            "DFW": "Dallas", "SEA": "Seattle", "ATL": "Atlanta",
            "LHR": "London", "CDG": "Paris", "FRA": "Frankfurt",
            "AMS": "Amsterdam", "SIN": "Singapore", "HKG": "Hong Kong",
            "NRT": "Tokyo", "SYD": "Sydney", "ICN": "Seoul",
            "BOM": "Mumbai", "GRU": "São Paulo", "YVR": "Vancouver",
            "YYZ": "Toronto", "MEL": "Melbourne", "DXB": "Dubai"
        }
        return city_map.get(colo.upper(), colo)
    
    def _get_country_name(self, loc_code: str) -> str:
        """Map country code to full name"""
        country_map = {
            "US": "United States", "CN": "China", "JP": "Japan",
            "GB": "United Kingdom", "DE": "Germany", "FR": "France",
            "CA": "Canada", "AU": "Australia", "SG": "Singapore",
            "IN": "India", "BR": "Brazil", "KR": "South Korea",
            "NL": "Netherlands", "SE": "Sweden", "IT": "Italy",
            "ES": "Spain", "RU": "Russia", "HK": "Hong Kong",
            "TW": "Taiwan", "MX": "Mexico", "AR": "Argentina"
        }
        return country_map.get(loc_code.upper(), loc_code)
