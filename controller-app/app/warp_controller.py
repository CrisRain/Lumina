# controller-app/warp_controller.py
import subprocess
import logging
import shlex

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
            return True
        return False

    def disconnect(self) -> bool:
        logger.info(f"Disconnecting WARP...")
        output = self.execute_command("warp-cli --accept-tos disconnect")
        if output and ("Success" in output or "disconnected" in output.lower()):
            return True
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
            # Check for various success messages
            if "Status: Connected" in warp_output or "Status update: Connected" in warp_output:
                is_connected = True
                base_status["status"] = "connected"
            
            # Parse details from warp-cli status
            for line in warp_output.split('\n'):
                if ":" in line:
                    k, v = line.split(":", 1)
                    key = k.strip()
                    value = v.strip()
                    base_status["details"][key] = value
                    
                    # Extract specific fields
                    if "Protocol" in key or "Mode" in key:
                        base_status["warp_protocol"] = value
                    elif "Network" in key:
                        base_status["network_type"] = value

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

