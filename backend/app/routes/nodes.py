import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..controllers.auth_controller import AuthHandler
from ..controllers.node_controller import NodeManager
from ..controllers.warp_controller import WarpController
from ..utils.version import get_app_version

router = APIRouter()
logger = logging.getLogger(__name__)
auth_handler = AuthHandler.get_instance()
node_mgr = NodeManager.get_instance()


class NodeCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    base_url: str = Field(min_length=1, max_length=512)
    token: Optional[str] = Field(default="", max_length=512)
    enabled: bool = True


class NodeUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    base_url: Optional[str] = Field(default=None, min_length=1, max_length=512)
    token: Optional[str] = Field(default=None, max_length=512)
    enabled: Optional[bool] = None


class BackendSwitchRequest(BaseModel):
    backend: str = Field(pattern="^(usque|official)$")


def _proxy_error_to_http(result: dict) -> HTTPException:
    status_code = int(result.get("status_code") or 502)
    # Preserve explicit auth failures from target node.
    if status_code in (401, 403, 404, 409, 429):
        code = status_code
    else:
        code = 502
    return HTTPException(status_code=code, detail=result.get("error") or "Remote request failed")


async def _local_connect():
    controller = WarpController.get_instance()
    success = await controller.connect()
    if not success:
        raise HTTPException(status_code=500, detail="Failed to connect local WARP")
    return await controller.get_status()


async def _local_disconnect():
    controller = WarpController.get_instance()
    success = await controller.disconnect()
    if not success:
        raise HTTPException(status_code=500, detail="Failed to disconnect local WARP")
    return await controller.get_status()


@router.get("")
async def list_nodes(user: str = Depends(auth_handler.get_current_user)):
    return {"nodes": node_mgr.list_nodes()}


@router.post("")
async def create_node(request: NodeCreateRequest, user: str = Depends(auth_handler.get_current_user)):
    try:
        node = node_mgr.add_node(
            name=request.name,
            base_url=request.base_url,
            token=request.token or "",
            enabled=request.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "node": node}


@router.put("/{node_id}")
async def update_node(node_id: str, request: NodeUpdateRequest, user: str = Depends(auth_handler.get_current_user)):
    try:
        node = node_mgr.update_node(
            node_id=node_id,
            name=request.name,
            base_url=request.base_url,
            token=request.token,
            enabled=request.enabled,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Node not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "node": node}


@router.delete("/{node_id}")
async def delete_node(node_id: str, user: str = Depends(auth_handler.get_current_user)):
    deleted = node_mgr.delete_node(node_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Node not found")
    return {"success": True}


@router.get("/overview")
async def overview(user: str = Depends(auth_handler.get_current_user)):
    local_status = await WarpController.get_instance().get_status()
    rows = [
        {
            "id": "local",
            "name": "Local Node",
            "base_url": "local://self",
            "enabled": True,
            "token_configured": False,
            "is_local": True,
            "reachable": True,
            "version": get_app_version(),
            "status": local_status,
            "error": None,
        }
    ]

    remote_nodes = node_mgr.list_nodes()
    raw_nodes = [node_mgr.get_node(node["id"]) for node in remote_nodes]
    raw_nodes = [node for node in raw_nodes if node]

    async def fetch_node_status(node: dict):
        if not node.get("enabled", True):
            return {
                **node_mgr.public_node(node),
                "is_local": False,
                "reachable": False,
                "version": None,
                "status": None,
                "error": "Node is disabled",
            }

        status_result, version_result = await asyncio.gather(
            node_mgr.request_remote(node, "GET", "/api/status"),
            node_mgr.request_remote(node, "GET", "/api/version"),
        )
        reachable = bool(status_result.get("ok"))
        version = None
        if version_result.get("ok") and isinstance(version_result.get("data"), dict):
            version = version_result["data"].get("version")

        return {
            **node_mgr.public_node(node),
            "is_local": False,
            "reachable": reachable,
            "version": version,
            "status": status_result.get("data") if reachable else None,
            "error": None if reachable else status_result.get("error"),
        }

    if raw_nodes:
        remote_rows = await asyncio.gather(*[fetch_node_status(node) for node in raw_nodes])
        rows.extend(remote_rows)

    return {"nodes": rows}


@router.post("/{node_id}/connect")
async def connect_node(node_id: str, user: str = Depends(auth_handler.get_current_user)):
    if node_id == "local":
        status = await _local_connect()
        return {"success": True, "status": status}

    node = node_mgr.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    if not node.get("enabled", True):
        raise HTTPException(status_code=400, detail="Node is disabled")

    result = await node_mgr.request_remote(node, "POST", "/api/connect")
    if not result.get("ok"):
        raise _proxy_error_to_http(result)
    return {"success": True, "status": result.get("data")}


@router.post("/{node_id}/disconnect")
async def disconnect_node(node_id: str, user: str = Depends(auth_handler.get_current_user)):
    if node_id == "local":
        status = await _local_disconnect()
        return {"success": True, "status": status}

    node = node_mgr.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    if not node.get("enabled", True):
        raise HTTPException(status_code=400, detail="Node is disabled")

    result = await node_mgr.request_remote(node, "POST", "/api/disconnect")
    if not result.get("ok"):
        raise _proxy_error_to_http(result)
    return {"success": True, "status": result.get("data")}


@router.post("/{node_id}/backend")
async def switch_backend(node_id: str, request: BackendSwitchRequest, user: str = Depends(auth_handler.get_current_user)):
    backend = request.backend

    if node_id == "local":
        try:
            controller = await WarpController.switch_backend(backend)
            connected = await controller.connect()
            status = await controller.get_status()
            return {"success": True, "connected": connected, "status": status}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            logger.error(f"Failed to switch local backend: {exc}")
            raise HTTPException(status_code=500, detail="Failed to switch backend") from exc

    node = node_mgr.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    if not node.get("enabled", True):
        raise HTTPException(status_code=400, detail="Node is disabled")

    result = await node_mgr.request_remote(node, "POST", "/api/backend/switch", {"backend": backend})
    if not result.get("ok"):
        raise _proxy_error_to_http(result)
    return {"success": True, "data": result.get("data")}
