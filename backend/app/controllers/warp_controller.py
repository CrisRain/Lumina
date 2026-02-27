# controller-app/app/warp_controller.py
"""
WarpController - Factory for WARP backend controllers
Automatically selects between usque and official backends based on environment
"""
import os
import logging
import asyncio
import shutil
from typing import Union
from .usque_controller import UsqueController
from .official_controller import OfficialController

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WarpController:
    """Factory class for WARP backend controllers"""
    
    _instance: Union[UsqueController, OfficialController, None] = None
    _current_backend: str = None
    _socks5_port: int = 1080

    @classmethod
    def _check_official_available(cls) -> Union[None, str]:
        missing = [b for b in ("warp-cli", "warp-svc") if shutil.which(b) is None]
        return f"Official backend unavailable: missing {', '.join(missing)}" if missing else None
    
    @classmethod
    def get_instance(cls, socks5_port: int = None) -> Union[UsqueController, OfficialController]:
        """
        Get the current WARP controller instance.
        Creates new instance if backend changed or doesn't exist.
        """
        if socks5_port is not None:
            cls._socks5_port = socks5_port

        backend = os.getenv("WARP_BACKEND", "usque").lower()
        if backend == "official":
            err = cls._check_official_available()
            if err:
                logger.warning(f"{err}; falling back to usque")
                backend = "usque"
                os.environ["WARP_BACKEND"] = "usque"
        
        # Create new instance if needed
        if cls._instance is None or cls._current_backend != backend:
            logger.info(f"Initializing WARP controller with backend: {backend} (SOCKS5 port: {cls._socks5_port})")
            cls._current_backend = backend
            
            if backend == "usque":
                cls._instance = UsqueController(socks5_port=cls._socks5_port)
            elif backend == "official":
                cls._instance = OfficialController(socks5_port=cls._socks5_port)
            else:
                raise ValueError(f"Unknown WARP_BACKEND: {backend}. Use 'usque' or 'official'")
        
        return cls._instance
    
    @classmethod
    async def switch_backend(cls, new_backend: str) -> Union[UsqueController, OfficialController]:
        """
        Switch to a different backend.
        Properly disconnects and cleans up the old backend before switching.
        """
        if new_backend not in ["usque", "official"]:
            raise ValueError(f"Invalid backend: {new_backend}. Use 'usque' or 'official'")

        if new_backend == "official":
            err = cls._check_official_available()
            if err:
                raise ValueError(err)
        
        current_backend = cls._current_backend or os.getenv("WARP_BACKEND", "usque")
        if current_backend == new_backend and cls._instance:
            logger.info(f"Already using {new_backend} backend")
            return cls._instance
        
        logger.info(f"Switching backend from {current_backend} to {new_backend}")
        
        # Disconnect and cleanup current backend
        if cls._instance:
            try:
                # Get current mode before disconnecting
                current_mode = "proxy"
                logger.info(f"Disconnecting current backend ({current_backend})...")
                
                await cls._instance.disconnect()
                    
            except Exception as e:
                logger.warning(f"Error disconnecting current backend: {e}")
        
        # Ensure SOCKS5 port is released before switching
        port = cls._socks5_port
        logger.info(f"Waiting for port {port} to be released...")
        port_free = False
        for _ in range(30): # Wait up to 15 seconds
            try:
                # Use asyncio to check port
                reader, writer = await asyncio.open_connection('127.0.0.1', port)
                writer.close()
                await writer.wait_closed()
                # Connected means port is busy
                await asyncio.sleep(0.5)
            except (ConnectionRefusedError, OSError):
                # Connection refused means port is free
                port_free = True
                break
        
        if not port_free:
            logger.error(f"Port {port} remains occupied after disconnect limit. Switch aborted.")
            raise RuntimeError(f"Address already in use: Port {port} is still occupied. Please check running processes.")
        
        # Update environment and reset instance
        os.environ["WARP_BACKEND"] = new_backend
        cls._instance = None
        cls._current_backend = None
        
        logger.info(f"Backend switched to {new_backend}, creating new controller...")
        
        # Return new instance
        return cls.get_instance()
    
    @classmethod
    def get_current_backend(cls) -> str:
        """Get the name of the current backend"""
        return cls._current_backend or os.getenv("WARP_BACKEND", "usque")

    @classmethod
    def get_current_mode(cls) -> str:
        """Get the current operating mode (always proxy)"""
        return "proxy"

    @classmethod
    async def reset(cls):
        """Reset the controller instance"""
        if cls._instance:
            try:
                await cls._instance.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting during reset: {e}")
        cls._instance = None
        cls._current_backend = None

    @classmethod
    def update_socks5_port(cls, port: int):
        """Update the SOCKS5 port on the current controller instance."""
        cls._socks5_port = port
        if cls._instance and hasattr(cls._instance, 'socks5_port'):
            cls._instance.socks5_port = port
            logger.info(f"Updated controller SOCKS5 port to {port}")
