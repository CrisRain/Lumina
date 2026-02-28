# controller-app/app/official_controller.py
"""
OfficialController - WARP backend implementation using official Cloudflare client
Supports proxy mode with MASQUE / WireGuard protocols
"""
import asyncio
import logging
import os
from typing import Dict
from .base_controller import WarpBackendController

logger = logging.getLogger(__name__)

class OfficialController(WarpBackendController):

    def __init__(self, socks5_port: int = 1080):
        super().__init__(socks5_port=socks5_port)
        self.mute_backend_logs = False
        self.preferred_protocol = "masque" 

    @property
    def mode(self) -> str:
        return "proxy"

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    async def execute_command(self, command: str):
        """Execute warp-cli command"""
        rc, stdout, stderr = await self._run_command(command, timeout=10)
        if rc != 0:
            logger.error(f"Command '{command}' failed: {stderr.strip()}")
            return None
        return stdout.strip()

    async def _is_daemon_responsive(self) -> bool:
        """Check if warp-svc is running AND responsive"""
        rc, stdout, _ = await self._run_command("s6-svstat -o up /run/service/warp-svc")
        if rc != 0 or stdout.strip() != "true":
            return False
        rc, _, _ = await self._run_command("warp-cli --accept-tos status", timeout=2)
        return rc == 0

    async def _check_daemon_running(self) -> bool:
        return await self._is_daemon_responsive()

    # ------------------------------------------------------------------
    # Connect / Disconnect
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        """Connect to WARP in proxy mode"""
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

        if await self.wait_for_status("connected", timeout=30): 
            self.mute_backend_logs = True
            self._invalidate_status_cache()
            logger.info("Official WARP proxy connection successful")
            return True

        # Diagnostic log
        status = await self.execute_command("warp-cli --accept-tos status")
        logger.error(f"Official WARP proxy connection failed. Status: {status}")
        return False


    async def disconnect(self) -> bool:
        """Disconnect from WARP and stop services"""
        logger.info(f"Disconnecting WARP (official, proxy mode)...")
        self._invalidate_status_cache()

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

            rc, _, stderr = await self._run_command("s6-rc -u change warp-svc")
            if rc != 0:
                logger.error(f"Failed to start warp-svc: {stderr}")
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


    async def _stop_services(self):
        """Stop all possible services (safe for both modes)"""
        logger.info("Stopping official services...")
        try:
            await self._run_command("s6-rc -d change socat")
            await self._run_command("s6-rc -d change warp-svc")
        except Exception as e:
            logger.error(f"Error stopping services: {e}")

    # ------------------------------------------------------------------
    # Auxiliary proxy helpers
    # ------------------------------------------------------------------

    async def _ensure_socat(self):
        """Ensure socat is running on the correct port; restart if port changed."""
        if self.mode != "proxy":
            return

        s6_active = False
        try:
            rc, stdout, _ = await self._run_command("s6-svstat -o up /run/service/socat")
            s6_active = rc == 0 and stdout.strip() == "true"
        except Exception:
            pass

        port_open = await self._is_port_open(self.socks5_port)

        if s6_active and port_open:
            return

        # Write updated port into the s6 container environment so the
        # run script picks it up on next start.
        self._write_s6_env("SOCKS5_PORT", str(self.socks5_port))

        logger.info(f"Starting socat service (port {self.socks5_port})...")
        try:
            await self._run_command("s6-rc -d change socat")
            await asyncio.sleep(0.3)
            await self._run_command("s6-rc -u change socat")
            await asyncio.sleep(1)
            if not await self._is_port_open(self.socks5_port):
                logger.warning(f"Socat started but port {self.socks5_port} not listening yet")
                await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Error starting socat: {e}")

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


    # ------------------------------------------------------------------
    # Connectivity checks
    # ------------------------------------------------------------------

    async def is_connected(self) -> bool:
        """Check if WARP is connected"""
        if not await self._check_daemon_running():
            return False
        rc, stdout, _ = await self._run_command("warp-cli --accept-tos status", timeout=3)
        if rc != 0:
            return False
        output = stdout.lower()
        return "connected" in output and "disconnected" not in output

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    
    async def _get_status_uncached(self) -> Dict:
        base = await super()._get_status_uncached()
        base["backend"] = "official"
        return base
        


