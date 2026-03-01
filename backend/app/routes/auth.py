from fastapi import APIRouter, Depends, Request, Security, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from ..controllers.auth_controller import AuthHandler, security
from ..controllers.config_controller import ConfigManager

router = APIRouter()
auth_handler = AuthHandler.get_instance()
config_mgr = ConfigManager.get_instance()

class LoginRequest(BaseModel):
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class LogoutAllRequest(BaseModel):
    keep_current: bool = True

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

@router.get("/sessions")
async def get_sessions(user: str = Depends(auth_handler.get_current_user)):
    return {
        "active_sessions": auth_handler.active_session_count()
    }

@router.post("/password")
async def change_password(
    req: ChangePasswordRequest,
    user: str = Depends(auth_handler.get_current_user),
    creds: HTTPAuthorizationCredentials = Security(security)
):
    if not config_mgr.panel_password:
        raise HTTPException(status_code=400, detail="Authentication is disabled")

    if not auth_handler.verify_password(req.current_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    if req.current_password == req.new_password:
        raise HTTPException(status_code=400, detail="New password must be different from current password")

    config_mgr.set("panel_password", auth_handler.hash_password(req.new_password))

    current_token = creds.credentials if creds else None
    logged_out_others = auth_handler.revoke_all_tokens(keep_token=current_token)

    return {
        "success": True,
        "message": "Password updated",
        "logged_out_others": logged_out_others,
        "active_sessions": auth_handler.active_session_count(),
    }

@router.post("/logout")
async def logout(
    user: str = Depends(auth_handler.get_current_user),
    creds: HTTPAuthorizationCredentials = Security(security)
):
    if creds and creds.credentials:
        auth_handler.revoke_token(creds.credentials)
    return {"success": True}

@router.post("/logout-all")
async def logout_all(
    req: LogoutAllRequest,
    user: str = Depends(auth_handler.get_current_user),
    creds: HTTPAuthorizationCredentials = Security(security)
):
    current_token = creds.credentials if (req.keep_current and creds) else None
    removed = auth_handler.revoke_all_tokens(keep_token=current_token)
    return {
        "success": True,
        "removed_sessions": removed,
        "active_sessions": auth_handler.active_session_count()
    }

@router.get("/check")
async def check_auth(user: str = Depends(auth_handler.get_current_user)):
    return {"authenticated": True, "user": user}
