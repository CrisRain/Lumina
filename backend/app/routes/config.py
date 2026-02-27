from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from ..controllers.auth_controller import AuthHandler
from ..controllers.config_controller import ConfigManager
from ..controllers.warp_controller import WarpController
import logging

router = APIRouter()
logger = logging.getLogger(__name__)
auth_handler = AuthHandler.get_instance()
config_mgr = ConfigManager.get_instance()

class PortsConfig(BaseModel):
    socks5_port: Optional[int] = None
    panel_port: Optional[int] = None

@router.get("/ports")
async def get_ports(user: str = Depends(auth_handler.get_current_user)):
    """Get current port configuration"""
    return {
        "socks5_port": config_mgr.socks5_port,
        "panel_port": config_mgr.panel_port
    }

@router.post("/ports")
async def update_ports(config: PortsConfig, user: str = Depends(auth_handler.get_current_user)):
    """Update port configuration"""
    restart_required = False
    
    if config.socks5_port is not None:
        if not (1 <= config.socks5_port <= 65535):
            raise HTTPException(status_code=400, detail="Invalid SOCKS5 port")
        
        if config.socks5_port != config_mgr.socks5_port:
            logger.info(f"Updating SOCKS5 port to {config.socks5_port}")
            config_mgr.set("socks5_port", config.socks5_port)
            # Update runtime if possible
            WarpController.update_socks5_port(config.socks5_port)
            # Trigger restart of backend connection to apply new port
            try:
                controller = WarpController.get_instance()
                if await controller.is_connected():
                    await controller.disconnect()
                    await controller.connect()
            except Exception as e:
                logger.warning(f"Failed to restart WARP after port change: {e}")

    if config.panel_port is not None:
        if not (1 <= config.panel_port <= 65535):
            raise HTTPException(status_code=400, detail="Invalid Panel port")
            
        if config.panel_port != config_mgr.panel_port:
            logger.info(f"Updating Panel port to {config.panel_port}")
            config_mgr.set("panel_port", config.panel_port)
            restart_required = True

    return {
        "success": True,
        "socks5_port": config_mgr.socks5_port,
        "panel_port": config_mgr.panel_port,
        "restart_required": restart_required
    }
