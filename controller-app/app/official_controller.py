# controller-app/app/official_controller.py
"""
OfficialController - WARP backend implementation using official Cloudflare client
"""
import subprocess
import logging
import os
import time
import threading
import json
from typing import Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OfficialController:
    """Control official Cloudflare WARP client"""
    
    # Class-level status cache
    _status_cache = None
    _status_cache_time = 0
    _STATUS_CACHE_TTL = 8  # seconds
    
    def __init__(self, socks5_port: int = 1080):
        self.socks5_port = socks5_port
        self.mute_backend_logs = False
        self.preferred_protocol = "masque"
        self._cached_ip_info = None
        self._cache_time: float = 0
        self._cache_ttl: float = 120  # Cache IP info for 120 seconds (reduce proxy traffic)

    def _stream_logs(self, process, name):
        """Read logs from process and log them until muted"""
        try:
            for line in iter(process.stdout.readline, ''):
                if not line:
                    break
                # Only log if not muted
                if not self.mute_backend_logs:
                    logger.debug(f"[{name}] {line.strip()}")
        except Exception:
            pass

    def execute_command(self, command: str):
        """Execute warp-cli command"""
        try:
            result = subprocess.run(
                command, 
                shell=True, 
                capture_output=True, 
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                logger.error(f"Command '{command}' failed: {result.stderr.strip()}")
                return None
            return result.stdout.strip()
        except Exception as e:
            logger.error(f"Error executing '{command}': {e}")
            return None

    def connect(self) -> bool:
        """Connect to WARP"""
        # Ensure daemon and proxy are running and responsive
        if not self._is_daemon_responsive():
            logger.info("Daemon not ready, restarting services...")
            # If process exists but not responsive, kill it first
            self._stop_services()
            if not self._start_services():
                logger.error("Failed to start official WARP services")
                return False
        
        # Ensure socat is running (in case daemon was running but proxy died)
        self._ensure_socat()

        logger.info("Connecting WARP (official)...")
        # Explicitly set mode and port again just in case, similar to entrypoint.sh acting every time
        self.execute_command("warp-cli --accept-tos mode proxy")
        self.execute_command("warp-cli --accept-tos proxy port 40001")
        
        self.execute_command("warp-cli --accept-tos connect")
        # Output logging removed as per user request
        
        # Wait a moment for state change
        time.sleep(2)
        
        if self.wait_for_status("connected", timeout=600):
            # Mute backend logs after successful connection
            self.mute_backend_logs = True
            self._invalidate_status_cache()
            logger.info("Official WARP connection successful")
            return True
        
        # Debug why it failed
        # status_output = self.execute_command("warp-cli --accept-tos status")
        logger.error("Official WARP connection failed")
        return False

    def disconnect(self) -> bool:
        """Disconnect from WARP and stop services"""
        logger.info("Disconnecting WARP (official)...")
        self._cached_ip_info = None
        
        # Try graceful disconnect first
        try:
            self.execute_command("warp-cli --accept-tos disconnect")
            self.wait_for_status("disconnected", timeout=5)
        except:
            pass
            
        # Stop background services
        self._stop_services()
        return True

    def _is_daemon_responsive(self) -> bool:
        """Check if warp-svc is running AND responsive"""
        try:
            # 1. Check warp-svc status via supervisor
            res = subprocess.run(
                ["supervisorctl", "status", "warp-svc"],
                capture_output=True,
                text=True
            )
            if res.returncode != 0 or "RUNNING" not in res.stdout:
                return False

            # 2. Check responsiveness
            # warp-cli status returns error code if daemon unreachable
            result = subprocess.run(
                "warp-cli --accept-tos status", 
                shell=True, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL,
                timeout=2
            )
            return result.returncode == 0
            
        except Exception:
            return False

    def _check_daemon_running(self) -> bool:
        """Deprecated: Use _is_daemon_responsive"""
        return self._is_daemon_responsive()

    def _start_services(self) -> bool:
        """Start warp-svc (systemctl) and socat (supervisor)"""
        try:
            logger.info("Starting background services (supervisor)...")
            
            # Reset mute flag on start
            self.mute_backend_logs = False
            
            # 1. Start warp-svc via supervisor
            try:
                subprocess.run(["supervisorctl", "start", "warp-svc"], check=True)
            except subprocess.CalledProcessError:
                logger.error("Failed to start warp-svc via supervisorctl")
                return False
            
            # logging removed as per user request
            time.sleep(3)
            
            # Start socat early as requested
            self._ensure_socat()
            
            # 3. Wait for readiness and configure
            for i in range(30):
                if self._is_daemon_responsive():
                    logger.info("warp-svc is ready")
                    
                    if self._configure_warp():
                        return True
                    else:
                        return False
                time.sleep(1)
                
            logger.error("Timed out waiting for warp-svc to become responsive")
            return False
        except Exception as e:
            logger.error(f"Error starting services: {e}")
            return False

    def _configure_warp(self) -> bool:
        """Apply WARP configuration (Register, MASQUE, Proxy Mode)"""
        try:
            # Register if needed
            if not os.path.exists("/var/lib/cloudflare-warp/reg.json"):
                logger.info("Registering new WARP account...")
                self.execute_command("warp-cli --accept-tos registration delete")
                self.execute_command("warp-cli --accept-tos registration new")
            
            # Always enforce MASQUE protocol
            self.execute_command("warp-cli --accept-tos tunnel protocol set MASQUE")
            
            # Configure Proxy Mode
            self.execute_command("warp-cli --accept-tos mode proxy")
            self.execute_command("warp-cli --accept-tos proxy port 40001")
            
            return True
        except Exception as e:
            logger.error(f"Error configuring WARP: {e}")
            return False

    def _stop_services(self):
        """Stop warp-svc and socat"""
        logger.info("Stopping official services (supervisor)...")
        try:
            # Stop socat via supervisor
            subprocess.run(["supervisorctl", "stop", "socat"], check=False)
            
            # Stop warp-svc via supervisor
            subprocess.run(["supervisorctl", "stop", "warp-svc"], check=False)
            
        except Exception as e:
            logger.error(f"Error stopping services: {e}")

    def _is_port_open(self, port: int) -> bool:
        """Check if port is listening using ss"""
        try:
            result = subprocess.run(
                ["ss", "-lnt", f"sport = :{port}"],
                capture_output=True,
                text=True
            )
            return f":{port}" in result.stdout
        except Exception:
            return False

    def _ensure_socat(self):
        """Ensure socat service is running and listening"""
        sys_active = False
        try:
            # Check if socat service is active via supervisor
            res = subprocess.run(
                ["supervisorctl", "status", "socat"],
                capture_output=True,
                text=True
            )
            sys_active = res.returncode == 0 and "RUNNING" in res.stdout
        except Exception:
            pass
            
        # Also check if it's actually listening
        port_open = self._is_port_open(self.socks5_port)
            
        if sys_active and port_open:
            return

        logger.info("Starting socat service...")
        try:
            subprocess.run(["supervisorctl", "start", "socat"], check=True)
            
            # Wait a moment for port to open
            time.sleep(1)
            
            # Verify port
            if not self._is_port_open(self.socks5_port):
                logger.warning(f"Socat started but port {self.socks5_port} is not listening yet")
                # Maybe wait a bit longer?
                time.sleep(2)
                
        except Exception as e:
            logger.error(f"Error starting socat: {e}")

    def is_connected(self) -> bool:
        """Check if WARP is connected and daemon is running (lightweight)"""
        if not self._check_daemon_running():
            return False
            
        try:
            result = subprocess.run(
                "warp-cli --accept-tos status", 
                shell=True, 
                capture_output=True, 
                text=True,
                timeout=3
            )
            
            if result.returncode != 0:
                return False
                
            output = result.stdout.lower()
            return "connected" in output and "disconnected" not in output
        except Exception:
            return False

    def get_status(self) -> Dict:
        """Get connection status and IP information (cached)"""
        now = time.time()
        if (OfficialController._status_cache is not None
            and now - OfficialController._status_cache_time < OfficialController._STATUS_CACHE_TTL):
            return OfficialController._status_cache
        
        status = self._get_status_uncached()
        OfficialController._status_cache = status
        OfficialController._status_cache_time = now
        return status
    
    def _invalidate_status_cache(self):
        """Invalidate status cache after connect/disconnect"""
        OfficialController._status_cache = None
        OfficialController._status_cache_time = 0
    
    def _get_status_uncached(self) -> Dict:
        """Get connection status and IP information"""
        base_status = {
            "backend": "official",
            "status": "disconnected",
            "ip": "Unknown",
            "location": "Unknown",
            "city": "Unknown",
            "country": "Unknown",
            "isp": "Cloudflare WARP",
            "warp_protocol": self.preferred_protocol.upper(),
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

    def _fetch_ip_info(self) -> dict:
        """Fetch IP information through the proxy.
        Uses the proxy to get the WARP exit IP.
        Cached for 120s to minimize traffic consumption.
        """
        try:
            result = subprocess.run(
                [
                    "curl",
                    "-x", f"socks5h://127.0.0.1:{self.socks5_port}",
                    "-s",
                    "--max-time", "5",
                    "http://ip-api.com/json/?fields=status,message,query,country,city,isp"
                ],
                capture_output=True,
                text=True,
                timeout=8
            )
            
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout)
                if data.get("status") == "success":
                    isp_value = data.get("isp") or "Cloudflare WARP"
                    ip_data = {
                        "ip": data.get("query") or "Unknown",
                        "country": data.get("country") or "Unknown",
                        "city": data.get("city") or "Unknown",
                        "location": data.get("country") or "Unknown",
                        "isp": isp_value,
                        "details": {"isp": isp_value}
                    }
                    return ip_data
                else:
                    logger.warning("IP API returned failure: %s", data.get("message"))
        except subprocess.TimeoutExpired:
            logger.warning("Timeout getting IP info through proxy")
        except Exception as e:
            logger.error(f"Error getting IP info: {e}")
        
        return None

    def wait_for_status(self, target_status: str, timeout: int = 15) -> bool:
        """Wait for specific connection status using lightweight checks"""
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
        """Rotate IP by disconnecting and reconnecting"""
        logger.info("Rotating IP (official: disconnect + reconnect)...")
        
        self.disconnect()
        # After disconnect, services are stopped. 
        # But connect() restarts them.
        
        # We need to wait a bit
        time.sleep(2)
        
        if self.connect():
            return self.wait_for_status("connected", timeout=15)
        
        return False

    def set_custom_endpoint(self, endpoint: str) -> bool:
        """Set custom endpoint using warp-cli"""
        try:
            if not endpoint:
                # Reset
                logger.info("Resetting custom endpoint (official)...")
                cmd = "warp-cli --accept-tos tunnel endpoint reset"
            else:
                # Set
                logger.info(f"Setting custom endpoint to {endpoint} (official)...")
                cmd = f"warp-cli --accept-tos tunnel endpoint set {endpoint}"

            self.execute_command(cmd)

            try:
                self.execute_command("warp-cli --accept-tos disconnect")
                self.wait_for_status("disconnected", timeout=5)
            except:
                pass
            time.sleep(10)
            return self.connect()

        except Exception as e:
            logger.error(f"Failed to set custom endpoint: {e}")
            return False

    def set_protocol(self, protocol: str) -> bool:
        """Set WARP protocol (MASQUE only, WireGuard removed)"""
        protocol = (protocol or "masque").lower()
        if protocol != "masque":
            logger.error("WireGuard mode has been removed; only MASQUE is supported")
            return False
        
        if self.preferred_protocol == "masque":
            logger.info("Protocol already locked to MASQUE")
            return True

        self.preferred_protocol = "masque"
        self._invalidate_status_cache()
        self.mute_backend_logs = False
        
        try:
            logger.info("Re-applying MASQUE protocol settings...")
            
            try:
                self.execute_command("warp-cli --accept-tos disconnect")
                self.wait_for_status("disconnected", timeout=5)
            except:
                pass
                
            cmd = "warp-cli --accept-tos tunnel protocol set MASQUE"
            res = self.execute_command(cmd)
            if res is None:
                logger.error("Failed to update tunnel protocol via warp-cli")
                return False

            self._stop_services()
            time.sleep(2)
            
            return self.connect()
            
        except Exception as e:
            logger.error(f"Failed to set protocol: {e}")
            return False

    def _get_city_from_colo(self, colo: str) -> str:
        """Map Cloudflare colo code to city"""
        city_map = {
            "LAX": "Los Angeles", "SJC": "San Jose", "ORD": "Chicago",
            "IAD": "Ashburn", "EWR": "Newark", "MIA": "Miami",
            "DFW": "Dallas", "SEA": "Seattle", "ATL": "Atlanta",
            "LHR": "London", "CDG": "Paris", "FRA": "Frankfurt",
            "AMS": "Amsterdam", "SIN": "Singapore", "HKG": "Hong Kong",
            "NRT": "Tokyo", "SYD": "Sydney", "ICN": "Seoul",
            "BOM": "Mumbai", "GRU": "São Paulo"
        }
        return city_map.get(colo.upper(), colo)

    def _get_country_name(self, loc_code: str) -> str:
        """Map country code to name"""
        country_map = {
            "US": "United States", "CN": "China", "JP": "Japan",
            "GB": "United Kingdom", "DE": "Germany", "FR": "France",
            "CA": "Canada", "AU": "Australia", "SG": "Singapore",
            "IN": "India", "BR": "Brazil", "KR": "South Korea",
            "NL": "Netherlands", "SE": "Sweden", "IT": "Italy",
            "ES": "Spain", "RU": "Russia", "HK": "Hong Kong",
            "TW": "Taiwan"
        }
        return country_map.get(loc_code.upper(), loc_code)
