from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from ..controllers.auth_controller import AuthHandler
from ..controllers.config_controller import ConfigManager

router = APIRouter()
auth_handler = AuthHandler.get_instance()
config_mgr = ConfigManager.get_instance()

class LoginRequest(BaseModel):
    password: str

@router.get("/status")
async def auth_status():
    """Public endpoint: tells the client whether authentication is enabled."""
    return {
        "initialized": config_mgr.initialized,
        "requires_auth": auth_handler.is_auth_enabled()
    }

@router.post("/login")
async def login(req: LoginRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    token = auth_handler.authenticate(req.password, client_ip=client_ip)
    return {"success": True, "token": token}

@router.get("/check")
async def check_auth(user: str = Depends(auth_handler.get_current_user)):
    return {"authenticated": True, "user": user}
