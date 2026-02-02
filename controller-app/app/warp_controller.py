# controller-app/warp_controller.py
import subprocess
import logging
import shlex
import asyncio
from typing import Optional, Dict, List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WarpController:
    def __init__(self, instance_id: int = 1, name: str = "Primary", socks5_port: int = 1080):
        self.instance_id = instance_id
        self.name = name  
        self.socks5_port = socks5_port

    def execute_command(self, command: str):
        try:
            # shell=True allows using pipes if needed, but risky if untrusted input. 
            # Here input is static.
            result = subprocess.run(
                command, 
                shell=True, 
                capture_output=True, 
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                logger.error(f"Command '{command}' failed with code {result.returncode}: {result.stderr.strip()}")
                return None
            return result.stdout.strip()
        except Exception as e:
            logger.error(f"Error executing '{command}': {e}")
            return None

    def connect(self) -> bool:
        logger.info(f"Connecting WARP...")
        output = self.execute_command("warp-cli --accept-tos connect")
        if output and ("Success" in output or "connected" in output.lower()):
            # Wait for connection to be established
            if self.wait_for_status("connected", timeout=15):
                return True
            logger.warning("Connect command succeeded but status is not connected after timeout")
            return False
        return False

    def disconnect(self) -> bool:
        logger.info(f"Disconnecting WARP...")
        output = self.execute_command("warp-cli --accept-tos disconnect")
        if output and ("Success" in output or "disconnected" in output.lower()):
            # Wait for disconnection
            if self.wait_for_status("disconnected", timeout=5):
                return True
            logger.warning("Disconnect command succeeded but status is not disconnected after timeout")
            return False
        return False

    def get_status(self) -> dict:
        """
        Returns a dict with status info for the frontend.
        """
        base_status = {
            "status": "disconnected", # connected, disconnected, error
            "ip": "Unknown",
            "location": "Unknown",
            "city": "Unknown",
            "country": "Unknown",
            "isp": "Cloudflare WARP",
            "warp_protocol": "Unknown",
            "connection_time": "Unknown",
            "network_type": "Unknown",
            "proxy_address": f"socks5://127.0.0.1:{self.socks5_port}",
            "details": {}
        }

        # 1. Check WARP status
        warp_output = self.execute_command("warp-cli --accept-tos status")
        is_connected = False
        if warp_output:
            # Check for connection status - more flexible matching
            warp_lower = warp_output.lower()
            # Match various connected states: "Status: Connected", "Connected(NetworkHealthy)", etc.
            if "connected" in warp_lower and "disconnected" not in warp_lower:
                is_connected = True
                base_status["status"] = "connected"
            
            # Parse details from warp-cli status
            for line in warp_output.split('\n'):
                if ":" in line:
                    k, v = line.split(":", 1)
                    key = k.strip()
                    value = v.strip()
                    base_status["details"][key] = value
                    
            # Set protocol to WARP when connected
            if is_connected:
                base_status["warp_protocol"] = "WARP"

        # 2. Get IP and location info (if connected)
        if is_connected:
            try:
                # Use local proxy 40001 (set up in entrypoint)
                trace_output = self.execute_command("curl -x socks5h://127.0.0.1:40001 -s https://www.cloudflare.com/cdn-cgi/trace")
                if trace_output:
                    info = {}
                    for line in trace_output.split('\n'):
                        if "=" in line:
                            k, v = line.split("=", 1)
                            info[k] = v
                    
                    base_status["ip"] = info.get("ip", "Unknown")
                    loc_code = info.get("loc", "Unknown")
                    base_status["location"] = loc_code
                    
                    # Get country name from colo (which is airport code)
                    colo = info.get("colo", "")
                    
                    # Parse location code (format: US, CN, JP, etc.)
                    if loc_code and loc_code != "Unknown":
                        # Map common country codes to names
                        country_map = {
                            "US": "United States",
                            "CN": "China",
                            "JP": "Japan",
                            "GB": "United Kingdom",
                            "DE": "Germany",
                            "FR": "France",
                            "CA": "Canada",
                            "AU": "Australia",
                            "SG": "Singapore",
                            "IN": "India",
                            "BR": "Brazil",
                            "KR": "South Korea",
                            "NL": "Netherlands",
                            "SE": "Sweden",
                            "IT": "Italy",
                            "ES": "Spain",
                            "RU": "Russia",
                            "HK": "Hong Kong",
                            "TW": "Taiwan",
                        }
                        base_status["country"] = country_map.get(loc_code, loc_code)
                    
                    # Get city from colo (airport code can hint at city)
                    if colo:
                        city_map = {
                            "LAX": "Los Angeles",
                            "SJC": "San Jose",
                            "ORD": "Chicago",
                            "IAD": "Ashburn",
                            "EWR": "Newark",
                            "MIA": "Miami",
                            "DFW": "Dallas",
                            "SEA": "Seattle",
                            "ATL": "Atlanta",
                            "LHR": "London",
                            "CDG": "Paris",
                            "FRA": "Frankfurt",
                            "AMS": "Amsterdam",
                            "SIN": "Singapore",
                            "HKG": "Hong Kong",
                            "NRT": "Tokyo",
                            "SYD": "Sydney",
                            "ICN": "Seoul",
                            "BOM": "Mumbai",
                            "GRU": "São Paulo",
                        }
                        base_status["city"] = city_map.get(colo, colo)
                    
                    # ISP is Cloudflare WARP
                    base_status["isp"] = "Cloudflare WARP"
                    
                    # Store trace info in details
                    base_status["details"]["trace"] = info
            except Exception as e:
                logger.error(f"Error getting trace info: {e}")
                pass
        
        return base_status

    def wait_for_status(self, target_status: str, timeout: int = 15) -> bool:
        """
        Wait for WARP to reach a specific status
        target_status: "connected" or "disconnected"
        """
        import time
        start_time = time.time()
        while time.time() - start_time < timeout:
            status = self.get_status()
            current_status = status.get("status", "disconnected")
            
            if current_status == target_status:
                return True
            
            # If waiting for connected but we are connecting, just wait
            # If waiting for disconnected, and we are connected, wait
            
            time.sleep(1)
        return False

    def rotate_ip_simple(self) -> bool:
        """简单轮换：断开重连"""
        logger.info("Performing simple IP rotation (disconnect + connect)")
        # 1. Disconnect
        self.disconnect()
        self.wait_for_status("disconnected", timeout=5)
        
        # 2. Wait a bit
        import time
        time.sleep(1)
        
        # 3. Connect
        if self.connect():
            # 4. Wait for connection
            return self.wait_for_status("connected", timeout=15)
        return False

