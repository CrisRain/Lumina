#!/bin/sh
# Container initialization - runs once at startup before services start
set -e

# Runtime directories
mkdir -p /var/lib/warp /var/lib/cloudflare-warp /app/data/kernels /var/log

# Persist dynamic env vars into the s6 container environment store
# so all services launched via with-contenv pick them up correctly
S6_ENV=/var/run/s6/container_environment
mkdir -p "${S6_ENV}"

DATA_DIR="${WARP_DATA_DIR:-/app/data}"
CONFIG_DB="${DATA_DIR}/config.db"
DEFAULT_SSL_DIR="${DATA_DIR}/ssl"

python3 - "${CONFIG_DB}" "${S6_ENV}" "${DEFAULT_SSL_DIR}" <<'PY'
import json
import os
import sqlite3
import sys

db_path, env_dir, ssl_dir = sys.argv[1], sys.argv[2], sys.argv[3]

def to_str(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)

defaults = {
    "SOCKS5_PORT": os.getenv("SOCKS5_PORT", "1080"),
    "PANEL_PORT": os.getenv("PANEL_PORT", "8000"),
    "WARP_BACKEND": os.getenv("WARP_BACKEND", "usque"),
    "WARP_DATA_DIR": os.getenv("WARP_DATA_DIR", "/app/data"),
    "PANEL_SSL_ENABLED": os.getenv("PANEL_SSL_ENABLED", "true"),
    "PANEL_SSL_CERT_FILE": os.getenv("PANEL_SSL_CERT_FILE", os.path.join(ssl_dir, "panel.crt")),
    "PANEL_SSL_KEY_FILE": os.getenv("PANEL_SSL_KEY_FILE", os.path.join(ssl_dir, "panel.key")),
    "PANEL_SSL_AUTO_SELF_SIGNED": os.getenv("PANEL_SSL_AUTO_SELF_SIGNED", "true"),
    "PANEL_SSL_DOMAIN": os.getenv("PANEL_SSL_DOMAIN", "localhost"),
    "PANEL_HTTP_REDIRECT_STATUS": os.getenv("PANEL_HTTP_REDIRECT_STATUS", "308"),
    "PANEL_HTTP_HTTPS_MUX_ENABLED": os.getenv("PANEL_HTTP_HTTPS_MUX_ENABLED", "true"),
    "PANEL_HTTPS_INTERNAL_PORT": os.getenv("PANEL_HTTPS_INTERNAL_PORT", "8443"),
    "PANEL_HTTP_REDIRECT_FORCE_DOMAIN": os.getenv("PANEL_HTTP_REDIRECT_FORCE_DOMAIN", ""),
}

mapping = {
    "SOCKS5_PORT": "socks5_port",
    "PANEL_PORT": "panel_port",
    "PANEL_SSL_ENABLED": "panel_ssl_enabled",
    "PANEL_SSL_CERT_FILE": "panel_ssl_cert_file",
    "PANEL_SSL_KEY_FILE": "panel_ssl_key_file",
    "PANEL_SSL_AUTO_SELF_SIGNED": "panel_ssl_auto_self_signed",
    "PANEL_SSL_DOMAIN": "panel_ssl_domain",
    "PANEL_HTTP_REDIRECT_STATUS": "panel_http_redirect_status",
    "PANEL_HTTP_HTTPS_MUX_ENABLED": "panel_http_https_mux_enabled",
    "PANEL_HTTPS_INTERNAL_PORT": "panel_https_internal_port",
    "PANEL_HTTP_REDIRECT_FORCE_DOMAIN": "panel_http_redirect_force_domain",
}

values = dict(defaults)

if os.path.exists(db_path):
    try:
        conn = sqlite3.connect(db_path)
        try:
            for env_key, db_key in mapping.items():
                row = conn.execute("SELECT value FROM settings WHERE key = ?", (db_key,)).fetchone()
                if not row:
                    continue
                raw = row[0]
                try:
                    parsed = json.loads(raw)
                except Exception:
                    parsed = raw
                text = to_str(parsed).strip()
                if env_key in {"PANEL_SSL_CERT_FILE", "PANEL_SSL_KEY_FILE", "PANEL_SSL_DOMAIN"} and not text:
                    continue
                values[env_key] = text
        finally:
            conn.close()
    except Exception:
        pass

os.makedirs(env_dir, exist_ok=True)
for key, value in values.items():
    with open(os.path.join(env_dir, key), "w", encoding="utf-8") as f:
        f.write(value)
PY
