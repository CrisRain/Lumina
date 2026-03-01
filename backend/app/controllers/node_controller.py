import logging
import os
import time
import uuid
from typing import Dict, List, Optional
from urllib.parse import urlparse, urlunparse

import httpx

from .config_controller import ConfigManager

logger = logging.getLogger(__name__)


class NodeManager:
    _instance = None
    _config_key = "remote_nodes"

    def __init__(self):
        self.config_mgr = ConfigManager.get_instance()
        self.request_timeout = float(os.getenv("NODE_REQUEST_TIMEOUT", "8"))

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = NodeManager()
        return cls._instance

    def _normalize_url(self, base_url: str) -> str:
        value = (base_url or "").strip()
        if not value:
            raise ValueError("Base URL is required")

        if not value.startswith(("http://", "https://")):
            value = f"http://{value}"

        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Invalid base URL")

        # Keep only scheme + host[:port]
        normalized = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
        return normalized.rstrip("/")

    def _load_nodes(self) -> List[Dict]:
        raw = self.config_mgr.get(self._config_key, [])
        if not isinstance(raw, list):
            return []

        nodes: List[Dict] = []
        changed = False
        for item in raw:
            if not isinstance(item, dict):
                changed = True
                continue

            node_id = str(item.get("id") or "").strip() or uuid.uuid4().hex[:12]
            name = str(item.get("name") or "").strip()
            base_url = str(item.get("base_url") or "").strip()
            token = str(item.get("token") or "")
            enabled = bool(item.get("enabled", True))
            created_at = int(item.get("created_at") or time.time())

            if not name or not base_url:
                changed = True
                continue

            try:
                normalized_url = self._normalize_url(base_url)
            except ValueError:
                changed = True
                continue

            nodes.append(
                {
                    "id": node_id,
                    "name": name,
                    "base_url": normalized_url,
                    "token": token,
                    "enabled": enabled,
                    "created_at": created_at,
                }
            )

            if node_id != item.get("id") or normalized_url != base_url:
                changed = True

        if changed:
            self._save_nodes(nodes)
        return nodes

    def _save_nodes(self, nodes: List[Dict]):
        self.config_mgr.set(self._config_key, nodes)

    @staticmethod
    def _public_node(node: Dict) -> Dict:
        return {
            "id": node["id"],
            "name": node["name"],
            "base_url": node["base_url"],
            "enabled": bool(node.get("enabled", True)),
            "created_at": int(node.get("created_at") or 0),
            "token_configured": bool(node.get("token")),
        }

    def public_node(self, node: Dict) -> Dict:
        return self._public_node(node)

    def list_nodes(self) -> List[Dict]:
        return [self._public_node(node) for node in self._load_nodes()]

    def get_node(self, node_id: str) -> Optional[Dict]:
        for node in self._load_nodes():
            if node["id"] == node_id:
                return node
        return None

    def add_node(self, name: str, base_url: str, token: str = "", enabled: bool = True) -> Dict:
        clean_name = (name or "").strip()
        if not clean_name:
            raise ValueError("Node name is required")

        normalized_url = self._normalize_url(base_url)
        nodes = self._load_nodes()

        for node in nodes:
            if node["base_url"] == normalized_url:
                raise ValueError("A node with the same base URL already exists")

        new_node = {
            "id": uuid.uuid4().hex[:12],
            "name": clean_name,
            "base_url": normalized_url,
            "token": (token or "").strip(),
            "enabled": bool(enabled),
            "created_at": int(time.time()),
        }
        nodes.append(new_node)
        self._save_nodes(nodes)
        return self._public_node(new_node)

    def update_node(
        self,
        node_id: str,
        name: Optional[str] = None,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> Dict:
        nodes = self._load_nodes()
        target = None
        for node in nodes:
            if node["id"] == node_id:
                target = node
                break

        if not target:
            raise KeyError("Node not found")

        if name is not None:
            clean_name = name.strip()
            if not clean_name:
                raise ValueError("Node name cannot be empty")
            target["name"] = clean_name

        if base_url is not None:
            normalized_url = self._normalize_url(base_url)
            for node in nodes:
                if node["id"] != node_id and node["base_url"] == normalized_url:
                    raise ValueError("A node with the same base URL already exists")
            target["base_url"] = normalized_url

        if token is not None:
            target["token"] = token.strip()

        if enabled is not None:
            target["enabled"] = bool(enabled)

        self._save_nodes(nodes)
        return self._public_node(target)

    def delete_node(self, node_id: str) -> bool:
        nodes = self._load_nodes()
        remaining = [node for node in nodes if node["id"] != node_id]
        if len(remaining) == len(nodes):
            return False
        self._save_nodes(remaining)
        return True

    @staticmethod
    def _build_auth_headers(token: str) -> Dict[str, str]:
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}

    async def request_remote(self, node: Dict, method: str, path: str, payload: Dict = None) -> Dict:
        node_path = path if path.startswith("/") else f"/{path}"
        url = f"{node['base_url']}{node_path}"
        headers = self._build_auth_headers(str(node.get("token") or ""))

        try:
            async with httpx.AsyncClient(timeout=self.request_timeout) as client:
                response = await client.request(method.upper(), url, headers=headers, json=payload)
        except httpx.RequestError as exc:
            return {
                "ok": False,
                "status_code": None,
                "data": None,
                "error": f"Request failed: {exc}",
            }

        content_type = response.headers.get("content-type", "").lower()
        if "application/json" in content_type:
            try:
                data = response.json()
            except ValueError:
                data = {"detail": response.text}
        else:
            data = {"detail": response.text}

        if response.status_code >= 400:
            detail = data.get("detail") if isinstance(data, dict) else None
            return {
                "ok": False,
                "status_code": response.status_code,
                "data": data,
                "error": str(detail or f"HTTP {response.status_code}"),
            }

        return {
            "ok": True,
            "status_code": response.status_code,
            "data": data,
            "error": None,
        }
