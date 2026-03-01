import asyncio
import logging
import httpx
from abc import ABC, abstractmethod
from typing import Dict, Optional, Union, List
import os
import shutil

logger = logging.getLogger(__name__)

class WarpBackendController(ABC):
    """
    Abstract base class for WARP backend controllers.
    Implements common functionality for process management, network checks, and status retrieval.
    """
    
    _status_cache: Optional[Dict] = None
    _status_cache_time: float = 0
    _STATUS_CACHE_TTL: float = 2.0
    _service_manager_cache: Optional[str] = None

    def __init__(self, socks5_port: int = 1080):
        self.socks5_port = socks5_port
        self._cached_ip_info: Optional[Dict] = None
        self._cache_time: float = 0
        self._cache_ttl: float = 120  # Cache IP info for 120 seconds

    @property
    @abstractmethod
    def mode(self) -> str:
        """Return current operation mode (e.g. 'proxy', 'tun')"""
        pass

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection"""
        pass

    @abstractmethod
    async def disconnect(self) -> bool:
        """Terminate connection"""
        pass
    
    @abstractmethod
    async def is_connected(self) -> bool:
        """Check if backend is connected"""
        pass

    @staticmethod
    async def _run_command(command: Union[str, List[str]], timeout=None):
        """Run a shell command or executable"""
        try:
            if isinstance(command, list):
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
            else:
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

    @classmethod
    def _detect_service_manager(cls) -> str:
        forced = (os.getenv("LUMINA_SERVICE_MANAGER", "") or "").strip().lower()
        if forced in {"s6", "systemd"}:
            return forced

        if shutil.which("s6-rc") and os.path.exists("/run/service"):
            return "s6"
        if shutil.which("systemctl"):
            return "systemd"
        return "unknown"

    @classmethod
    def _service_manager(cls) -> str:
        if cls._service_manager_cache is None:
            cls._service_manager_cache = cls._detect_service_manager()
            logger.info(f"Detected service manager: {cls._service_manager_cache}")
        return cls._service_manager_cache

    @staticmethod
    def _systemd_unit(service: str) -> str:
        mapping = {
            "warp-svc": "lumina-warp-svc.service",
            "usque": "lumina-usque.service",
            "socat": "lumina-socat.service",
        }
        return mapping.get(service, service)

    async def _service_start(self, service: str) -> bool:
        manager = self._service_manager()
        if manager == "s6":
            rc, _, stderr = await self._run_command(f"s6-rc -u change {service}")
            if rc != 0:
                logger.error(f"Failed to start {service} via s6: {stderr}")
                return False
            return True

        if manager == "systemd":
            unit = self._systemd_unit(service)
            rc, _, stderr = await self._run_command(["systemctl", "start", unit])
            if rc != 0:
                logger.error(f"Failed to start {unit} via systemd: {stderr}")
                return False
            return True

        logger.error(f"No supported service manager found to start '{service}'")
        return False

    async def _service_stop(self, service: str) -> bool:
        manager = self._service_manager()
        if manager == "s6":
            rc, _, stderr = await self._run_command(f"s6-rc -d change {service}")
            if rc != 0:
                logger.warning(f"Failed to stop {service} via s6: {stderr}")
                return False
            return True

        if manager == "systemd":
            unit = self._systemd_unit(service)
            rc, _, stderr = await self._run_command(["systemctl", "stop", unit])
            if rc != 0:
                logger.warning(f"Failed to stop {unit} via systemd: {stderr}")
                return False
            return True

        logger.error(f"No supported service manager found to stop '{service}'")
        return False

    async def _service_is_active(self, service: str) -> bool:
        manager = self._service_manager()
        if manager == "s6":
            rc, stdout, _ = await self._run_command(f"s6-svstat -o up /run/service/{service}")
            return rc == 0 and stdout.strip() == "true"

        if manager == "systemd":
            unit = self._systemd_unit(service)
            rc, _, _ = await self._run_command(["systemctl", "is-active", "--quiet", unit])
            return rc == 0

        return False

    @staticmethod
    def _upsert_env_file(path: str, key: str, value: str):
        existing: List[str] = []
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing = f.read().splitlines()
            except OSError:
                existing = []

        target = f"{key}={value}"
        updated: List[str] = []
        replaced = False
        for line in existing:
            if line.startswith(f"{key}="):
                updated.append(target)
                replaced = True
            else:
                updated.append(line)
        if not replaced:
            updated.append(target)

        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(updated).rstrip() + "\n")

    def _write_runtime_env(self, key: str, value: str) -> None:
        manager = self._service_manager()
        if manager == "s6":
            env_dir = "/var/run/s6/container_environment"
            try:
                os.makedirs(env_dir, exist_ok=True)
                with open(os.path.join(env_dir, key), "w", encoding="utf-8") as f:
                    f.write(value)
            except OSError:
                pass
            return

        if manager == "systemd":
            env_file = os.getenv("LUMINA_ENV_FILE", "/etc/lumina/lumina.env")
            try:
                self._upsert_env_file(env_file, key, value)
            except OSError as e:
                logger.warning(f"Failed to update systemd env file {env_file}: {e}")

    async def _is_port_open(self, port: int) -> bool:
        """Check if a local port is listening using 'ss'"""
        try:
            rc, stdout, _ = await self._run_command(f"ss -lnt sport = :{port}")
            return f":{port}" in stdout
        except (OSError, asyncio.SubprocessError):
            return False

    async def get_status(self) -> Dict:
        """Get connection status and IP information (with short-term caching)"""
        now = asyncio.get_running_loop().time()
        if (
            self._status_cache is not None
            and now - self._status_cache_time < self._STATUS_CACHE_TTL
        ):
            return self._status_cache

        status = await self._get_status_uncached()
        self._status_cache = status
        self._status_cache_time = now
        return status

    def _invalidate_status_cache(self):
        self._status_cache = None
        self._status_cache_time = 0

    async def _get_status_uncached(self) -> Dict:
        """
        Construct status dictionary. 
        Subclasses can override, but this provides a solid default structure.
        """
        connected = await self.is_connected()
        
        base_status = {
            "backend": self.__class__.__name__.replace("Controller", "").lower(), # efficient enough
            "status": "connected" if connected else "disconnected",
            "ip": "Unknown",
            "location": "Unknown",
            "city": "Unknown",
            "country": "Unknown",
            "isp": "Cloudflare WARP",
            "warp_protocol": "MASQUE", # Default, override in subclass if dynamic
            "warp_mode": self.mode,
            "connection_time": "Unknown",
            "network_type": "Unknown",
            "proxy_address": f"socks5://127.0.0.1:{self.socks5_port}",
            "details": {},
        }

        if not connected:
            self._cached_ip_info = None
            return base_status

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

    async def _fetch_from_apis(self, client: httpx.AsyncClient, apis: List[str]) -> Optional[Dict]:
        for api_url in apis:
            try:
                response = await client.get(api_url)
                response.raise_for_status()
                data = response.json()
                result = self._parse_ip_data(data, api_url)
                if result:
                    return result
            except httpx.RequestError as e:
                logger.warning(f"IP info fetch failed ({api_url}): {e}")
            except Exception as e:
                logger.warning(f"Error parsing IP info ({api_url}): {e}")
        return None

    async def _fetch_ip_info(self) -> Optional[Dict]:
        """Fetch IP info via SOCKS5 proxy using httpx, with direct fallback"""
        apis = [
            "http://ip-api.com/json/?fields=status,message,query,country,city,isp",
            "https://ipinfo.io/json",
            "https://ifconfig.me/all.json"
        ]
        
        proxy_url = f"socks5h://127.0.0.1:{self.socks5_port}"
        
        # Try via SOCKS5 proxy first
        try:
            async with httpx.AsyncClient(proxy=proxy_url, timeout=8.0) as client:
                result = await self._fetch_from_apis(client, apis)
                if result:
                    return result
        except Exception as e:
            logger.warning(f"Failed to create proxy client (socks5 port {self.socks5_port}): {e}")
        
        # Fallback: try direct connection (useful for TUN mode or when socat isn't ready)
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                result = await self._fetch_from_apis(client, apis)
                if result:
                    logger.info(f"IP info fetched via direct connection")
                    return result
        except Exception as e:
            logger.warning(f"Direct IP info fetch also failed: {e}")
                
        return None

    @staticmethod
    def _parse_ip_data(data: Dict, api_url: str) -> Dict:
        """Normalize IP data from different APIs"""
        if "ip-api.com" in api_url:
            if data.get("status") == "success":
                isp = data.get("isp") or "Cloudflare WARP"
                return {
                    "ip": data.get("query") or "Unknown",
                    "country": data.get("country") or "Unknown",
                    "city": data.get("city") or "Unknown",
                    "location": data.get("country") or "Unknown",
                    "isp": isp,
                    "details": {"isp": isp},
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
                "country": "Unknown",
                "city": "Unknown",
                "location": "Unknown",
                "isp": "Cloudflare WARP",
                "details": {},
            }
        return {}

    async def wait_for_status(self, target_status: str, timeout: int = 15) -> bool:
        """Poll for status change"""
        start_time = asyncio.get_running_loop().time()
        while asyncio.get_running_loop().time() - start_time < timeout:
            connected = await self.is_connected()
            if target_status == "connected" and connected:
                self._invalidate_status_cache()
                return True
            elif target_status == "disconnected" and not connected:
                self._invalidate_status_cache()
                return True
            await asyncio.sleep(1)
        return False

