# controller-app/app/usque_controller.py
"""
UsqueController - WARP backend implementation using usque
Supports both proxy mode (SOCKS5) and TUN mode
"""
import asyncio
import logging
import json
import os
from typing import Optional, Dict
from .kernel_controller import KernelVersionManager
from .base_controller import WarpBackendController

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UsqueController(WarpBackendController):

    def __init__(self, config_path=None, socks5_port=1080):
        super().__init__(socks5_port=socks5_port)
        self.config_path = config_path or os.getenv("USQUE_CONFIG_PATH", "/var/lib/warp/config.json")
        self.process = None

    @property
    def mode(self) -> str:
        return "proxy"

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    async def initialize(self) -> bool:
        """Initialize usque backend (register if needed)"""
        try:
            config_dir = os.path.dirname(self.config_path)
            os.makedirs(config_dir, exist_ok=True)

            if not os.path.exists(self.config_path):
                logger.info("Config not found, registering new usque account...")
                
                binary_path = KernelVersionManager.get_instance().get_binary_path('usque')
                process = await asyncio.create_subprocess_exec(
                    binary_path, "register",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=config_dir,
                )
                stdout, stderr = await process.communicate(input=b"y\n")

                if process.returncode == 0:
                    logger.info("usque registration successful")
                    return True
                else:
                    logger.error(f"usque registration failed: {stderr.decode()}")
                    return False
            return True
        except Exception as e:
            logger.error(f"Error initializing usque: {e}")
            return False

    # ------------------------------------------------------------------
    # Connect / Disconnect
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        """Start usque in proxy mode"""
        if not await self.initialize():
            logger.error("Failed to initialize usque backend")
            return False

        if await self.is_connected():
            logger.info("usque already running")
            return True

        return await self._connect_proxy()

    async def _connect_proxy(self) -> bool:
        """Start usque SOCKS5 proxy via s6"""
        try:
            logger.info(f"Starting usque service (proxy mode, port {self.socks5_port})...")
            self._write_s6_env("SOCKS5_PORT", str(self.socks5_port))

            # Stop first (idempotent — ok if it wasn't running)
            await self._run_command("s6-rc -d change usque")
            await asyncio.sleep(0.5)
            rc, _, stderr = await self._run_command("s6-rc -u change usque")
            if rc != 0:
                logger.error(f"Failed to start usque via s6-rc: {stderr}")
                return False

            logger.info("Waiting for usque proxy to become ready...")
            for _ in range(15):
                if await self._is_proxy_connected():
                    logger.info("usque proxy started successfully")
                    return True
                await asyncio.sleep(1)

            logger.error("usque proxy failed to start (timeout)")
            return False
        except Exception as e:
            logger.error(f"Failed to start usque proxy: {e}")
            return False

            logger.info("Waiting for usque proxy to become ready...")
            for _ in range(15):
                if await self._is_proxy_connected():
                    logger.info("usque proxy started successfully")
                    return True
                await asyncio.sleep(1)

            logger.error("usque proxy failed to start (timeout)")
            return False
        except Exception as e:
            logger.error(f"Failed to start usque proxy: {e}")
            return False

    @staticmethod
    def _write_s6_env(key: str, value: str) -> None:
        """Persist an env var into the s6 container environment store."""
        env_dir = "/var/run/s6/container_environment"
        try:
            os.makedirs(env_dir, exist_ok=True)
            with open(os.path.join(env_dir, key), "w") as f:
                f.write(value)
        except OSError:
            pass

    async def disconnect(self) -> bool:
        """Stop usque service"""
        try:
            logger.info("Stopping usque services...")
            await self._run_command("s6-rc -d change usque")
            self.process = None
            self._invalidate_status_cache()
            return True
        except Exception as e:
            logger.error(f"Error stopping usque: {e}")
            return False

    # ------------------------------------------------------------------
    # Connectivity checks
    # ------------------------------------------------------------------

    async def _is_proxy_connected(self) -> bool:
        """Check if usque SOCKS5 proxy is running"""
        try:
            rc, stdout, _ = await self._run_command("s6-svstat -o up /run/service/usque")
            if rc != 0 or stdout.strip() != "true":
                return False
        except Exception:
            return False
        return await self._is_port_open(self.socks5_port)

    async def is_connected(self) -> bool:
        """Check if usque is running"""
        return await self._is_proxy_connected()

    # ------------------------------------------------------------------
    # Status (Override common method if needed, otherwise use Base)
    # ------------------------------------------------------------------
    
    async def _get_status_uncached(self) -> Dict:
        # Get base status
        base = await super()._get_status_uncached()
        base["backend"] = "usque" # Explicitly set backend name if needed
        return base

    # ------------------------------------------------------------------
    # Custom operations
    # ------------------------------------------------------------------


