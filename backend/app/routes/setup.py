import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from ..controllers.config_controller import ConfigManager
from ..controllers.warp_controller import WarpController

router = APIRouter()
logger = logging.getLogger(__name__)
config_mgr = ConfigManager.get_instance()


class SetupRequest(BaseModel):
    panel_password: str = Field(min_length=8, max_length=256)
    socks5_port: Optional[int] = Field(default=1080, ge=1, le=65535)
    panel_port: Optional[int] = Field(default=8000, ge=1, le=65535)


@router.get("/status")
async def setup_status():
    return {
        "initialized": config_mgr.initialized,
        "requires_auth": bool(config_mgr.panel_password),
    }


@router.post("/initialize")
async def initialize_panel(req: SetupRequest):
    if config_mgr.initialized:
        raise HTTPException(status_code=409, detail="Panel is already initialized")

    previous_socks5 = config_mgr.socks5_port
    previous_panel_port = config_mgr.panel_port
    config_mgr.set("panel_password", req.panel_password)
    config_mgr.set("socks5_port", int(req.socks5_port or 1080))
    config_mgr.set("panel_port", int(req.panel_port or 8000))
    config_mgr.set("initialized", True)

    if config_mgr.socks5_port != previous_socks5:
        try:
            WarpController.update_socks5_port(config_mgr.socks5_port)
        except Exception as e:
            logger.warning(f"Failed to apply SOCKS5 port during initialization: {e}")

    restart_required = config_mgr.panel_port != previous_panel_port
    return {
        "success": True,
        "restart_required": restart_required,
        "message": "Initialization completed",
    }
