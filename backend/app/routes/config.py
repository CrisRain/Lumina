from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Tuple
import os
import logging

from ..controllers.auth_controller import AuthHandler
from ..controllers.config_controller import ConfigManager
from ..controllers.warp_controller import WarpController
from ..utils.tls import ensure_self_signed_certificate

router = APIRouter()
logger = logging.getLogger(__name__)
auth_handler = AuthHandler.get_instance()
config_mgr = ConfigManager.get_instance()


def _upsert_env_setting(key: str, value: str):
    env_file = os.getenv("LUMINA_ENV_FILE", "/etc/lumina/lumina.env")
    if not env_file:
        return

    lines = []
    try:
        if os.path.exists(env_file):
            with open(env_file, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
    except OSError:
        return

    target = f"{key}={value}"
    replaced = False
    out = []
    for line in lines:
        if line.startswith(f"{key}="):
            out.append(target)
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(target)

    try:
        os.makedirs(os.path.dirname(env_file), exist_ok=True)
        with open(env_file, "w", encoding="utf-8") as f:
            f.write("\n".join(out).rstrip() + "\n")
    except OSError:
        pass


def _update_s6_runtime_env(key: str, value: str):
    env_dir = "/var/run/s6/container_environment"
    if not os.path.isdir(env_dir):
        return

    try:
        with open(os.path.join(env_dir, key), "w", encoding="utf-8") as f:
            f.write(value)
    except OSError:
        pass


def _update_runtime_env_setting(key: str, value: str):
    # Make it immediately visible in current process for subsequent reads.
    os.environ[key] = value
    _upsert_env_setting(key, value)
    _update_s6_runtime_env(key, value)


def _to_bool_env(value: Optional[str], default: bool) -> bool:
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _coerce_bool(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        return default
    return bool(value)


def _default_ssl_paths() -> Tuple[str, str]:
    data_dir = os.getenv("WARP_DATA_DIR", "/app/data")
    ssl_dir = os.path.join(data_dir, "ssl")
    return (
        os.getenv("PANEL_SSL_CERT_FILE", os.path.join(ssl_dir, "panel.crt")),
        os.getenv("PANEL_SSL_KEY_FILE", os.path.join(ssl_dir, "panel.key")),
    )


def _get_ssl_settings():
    default_cert, default_key = _default_ssl_paths()

    env_enabled = os.getenv("PANEL_SSL_ENABLED")
    if env_enabled is not None:
        enabled = _to_bool_env(env_enabled, True)
    else:
        enabled = _coerce_bool(config_mgr.get("panel_ssl_enabled", True), True)

    env_cert_file = os.getenv("PANEL_SSL_CERT_FILE")
    if env_cert_file is not None and env_cert_file.strip():
        cert_file = env_cert_file.strip()
    else:
        cert_file = str(config_mgr.get("panel_ssl_cert_file", default_cert) or default_cert).strip() or default_cert

    env_key_file = os.getenv("PANEL_SSL_KEY_FILE")
    if env_key_file is not None and env_key_file.strip():
        key_file = env_key_file.strip()
    else:
        key_file = str(config_mgr.get("panel_ssl_key_file", default_key) or default_key).strip() or default_key

    env_auto_self_signed = os.getenv("PANEL_SSL_AUTO_SELF_SIGNED")
    if env_auto_self_signed is not None:
        auto_self_signed = _to_bool_env(env_auto_self_signed, True)
    else:
        auto_self_signed = _coerce_bool(config_mgr.get("panel_ssl_auto_self_signed", True), True)

    env_domain = os.getenv("PANEL_SSL_DOMAIN")
    if env_domain is not None and env_domain.strip():
        domain = env_domain.strip()
    else:
        domain = str(config_mgr.get("panel_ssl_domain", "localhost") or "localhost").strip() or "localhost"

    return {
        "panel_ssl_enabled": enabled,
        "panel_ssl_cert_file": cert_file.strip(),
        "panel_ssl_key_file": key_file.strip(),
        "panel_ssl_auto_self_signed": auto_self_signed,
        "panel_ssl_domain": domain.strip() or "localhost",
    }

class PortsConfig(BaseModel):
    socks5_port: Optional[int] = None
    panel_port: Optional[int] = None


class SSLConfig(BaseModel):
    panel_ssl_enabled: Optional[bool] = None
    panel_ssl_cert_file: Optional[str] = None
    panel_ssl_key_file: Optional[str] = None
    panel_ssl_auto_self_signed: Optional[bool] = None
    panel_ssl_domain: Optional[str] = None


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
            _update_runtime_env_setting("SOCKS5_PORT", str(config.socks5_port))
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
            _update_runtime_env_setting("PANEL_PORT", str(config.panel_port))
            restart_required = True

    return {
        "success": True,
        "socks5_port": config_mgr.socks5_port,
        "panel_port": config_mgr.panel_port,
        "restart_required": restart_required
    }


@router.get("/ssl")
async def get_ssl_config(user: str = Depends(auth_handler.get_current_user)):
    ssl_settings = _get_ssl_settings()
    cert_file = ssl_settings["panel_ssl_cert_file"]
    key_file = ssl_settings["panel_ssl_key_file"]

    return {
        **ssl_settings,
        "cert_exists": os.path.isfile(cert_file),
        "key_exists": os.path.isfile(key_file),
    }


@router.post("/ssl")
async def update_ssl_config(config: SSLConfig, user: str = Depends(auth_handler.get_current_user)):
    current = _get_ssl_settings()

    enabled = current["panel_ssl_enabled"] if config.panel_ssl_enabled is None else _coerce_bool(config.panel_ssl_enabled, False)
    cert_file = current["panel_ssl_cert_file"] if config.panel_ssl_cert_file is None else str(config.panel_ssl_cert_file).strip()
    key_file = current["panel_ssl_key_file"] if config.panel_ssl_key_file is None else str(config.panel_ssl_key_file).strip()
    auto_self_signed = (
        current["panel_ssl_auto_self_signed"]
        if config.panel_ssl_auto_self_signed is None
        else _coerce_bool(config.panel_ssl_auto_self_signed, True)
    )
    domain = current["panel_ssl_domain"] if config.panel_ssl_domain is None else str(config.panel_ssl_domain).strip()

    default_cert, default_key = _default_ssl_paths()
    cert_file = cert_file or default_cert
    key_file = key_file or default_key
    domain = domain or "localhost"

    generated_self_signed = False
    if enabled and auto_self_signed and (not os.path.isfile(cert_file) or not os.path.isfile(key_file)):
        try:
            generated_self_signed = ensure_self_signed_certificate(
                cert_path=cert_file,
                key_path=key_file,
                common_name=domain,
            )
        except Exception as e:
            logger.error(f"Failed to generate self-signed certificate: {e}")
            raise HTTPException(status_code=500, detail="Failed to generate self-signed certificate") from e

    changed = (
        enabled != current["panel_ssl_enabled"]
        or cert_file != current["panel_ssl_cert_file"]
        or key_file != current["panel_ssl_key_file"]
        or auto_self_signed != current["panel_ssl_auto_self_signed"]
        or domain != current["panel_ssl_domain"]
    )

    config_mgr.set("panel_ssl_enabled", enabled)
    config_mgr.set("panel_ssl_cert_file", cert_file)
    config_mgr.set("panel_ssl_key_file", key_file)
    config_mgr.set("panel_ssl_auto_self_signed", auto_self_signed)
    config_mgr.set("panel_ssl_domain", domain)

    _update_runtime_env_setting("PANEL_SSL_ENABLED", "true" if enabled else "false")
    _update_runtime_env_setting("PANEL_SSL_CERT_FILE", cert_file)
    _update_runtime_env_setting("PANEL_SSL_KEY_FILE", key_file)
    _update_runtime_env_setting("PANEL_SSL_AUTO_SELF_SIGNED", "true" if auto_self_signed else "false")
    _update_runtime_env_setting("PANEL_SSL_DOMAIN", domain)

    return {
        "success": True,
        "panel_ssl_enabled": enabled,
        "panel_ssl_cert_file": cert_file,
        "panel_ssl_key_file": key_file,
        "panel_ssl_auto_self_signed": auto_self_signed,
        "panel_ssl_domain": domain,
        "cert_exists": os.path.isfile(cert_file),
        "key_exists": os.path.isfile(key_file),
        "generated_self_signed": generated_self_signed,
        "restart_required": bool(changed or generated_self_signed),
    }
