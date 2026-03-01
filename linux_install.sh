#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}$*${NC}"; }
warn() { echo -e "${YELLOW}$*${NC}"; }
error() { echo -e "${RED}$*${NC}"; }

require_root() {
  if [ "${EUID:-$(id -u)}" -ne 0 ]; then
    error "Please run as root"
    exit 1
  fi
}

validate_port() {
  local name="$1"
  local value="$2"
  if ! [[ "${value}" =~ ^[0-9]+$ ]] || [ "${value}" -lt 1 ] || [ "${value}" -gt 65535 ]; then
    error "Invalid ${name}: ${value} (must be 1-65535)"
    exit 1
  fi
}

detect_arch() {
  case "$(uname -m)" in
    x86_64|amd64) echo "amd64" ;;
    aarch64|arm64) echo "arm64" ;;
    *)
      error "Unsupported architecture: $(uname -m) (supported: amd64, arm64)"
      exit 1
      ;;
  esac
}

install_system_deps() {
  log "[1/9] Installing system dependencies..."
  apt-get update -qq
  apt-get install -y -qq -o Dpkg::Options::="--force-confold" \
    curl gpg lsb-release ca-certificates dbus \
    python3 python3-pip python3-venv python3-full \
    socat iputils-ping iproute2 iptables procps unzip tar jq openssl
}

install_nodejs_if_needed() {
  log "[2/9] Ensuring Node.js is installed..."
  if command -v node >/dev/null 2>&1; then
    log "Node.js already installed ($(node -v))"
    return
  fi

  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y -qq nodejs
}

install_cloudflare_warp_if_needed() {
  log "[3/9] Ensuring Cloudflare WARP is installed..."
  if command -v warp-cli >/dev/null 2>&1 && command -v warp-svc >/dev/null 2>&1; then
    log "Cloudflare WARP already installed"
    return
  fi

  rm -f /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg
  curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg \
    | gpg --yes --dearmor --output /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg
  echo "deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ $(lsb_release -cs) main" \
    > /etc/apt/sources.list.d/cloudflare-client.list
  apt-get update -qq
  apt-get install -y -qq cloudflare-warp
}

install_usque_if_needed() {
  log "[4/9] Ensuring usque is installed..."
  if command -v usque >/dev/null 2>&1; then
    log "usque already installed ($(command -v usque))"
    return
  fi

  local arch
  arch="$(detect_arch)"
  local latest_tag
  local version
  local url

  latest_tag="$(curl -fsSL https://api.github.com/repos/Diniboy1123/usque/releases/latest | jq -r '.tag_name')"
  version="${latest_tag#v}"
  url="https://github.com/Diniboy1123/usque/releases/download/${latest_tag}/usque_${version}_linux_${arch}.zip"

  log "Downloading usque ${latest_tag} (${arch})..."
  curl -fL -o /tmp/usque.zip "${url}"
  unzip -o /tmp/usque.zip -d /tmp/usque-extract >/dev/null

  if [ -f /tmp/usque-extract/usque ]; then
    install -m 0755 /tmp/usque-extract/usque /usr/local/bin/usque
  else
    error "usque binary not found after extraction"
    exit 1
  fi

  rm -rf /tmp/usque.zip /tmp/usque-extract
}

setup_python_env() {
  log "[5/9] Setting up Python virtual environment..."
  if [ ! -d "${BACKEND_DIR}" ]; then
    error "Backend directory not found: ${BACKEND_DIR}"
    exit 1
  fi

  cd "${BACKEND_DIR}"
  if [ ! -d "venv" ]; then
    python3 -m venv venv
  fi
  . "${BACKEND_DIR}/venv/bin/activate"
  pip install -U pip -q
  pip install -q -r requirements.txt
}

build_frontend() {
  log "[6/9] Building frontend..."
  if [ ! -d "${FRONTEND_DIR}" ]; then
    error "Frontend directory not found: ${FRONTEND_DIR}"
    exit 1
  fi

  cd "${FRONTEND_DIR}"
  if [ -f package-lock.json ]; then
    npm ci --silent
  else
    npm install --silent
  fi
  npm run build

  mkdir -p "${STATIC_DIR}"
  rm -rf "${STATIC_DIR:?}"/*
  cp -r "${FRONTEND_DIR}/dist/"* "${STATIC_DIR}/"
}

prepare_directories() {
  log "[7/9] Preparing runtime directories..."
  mkdir -p "${LUMINA_ETC_DIR}" "${LUMINA_SSL_DIR}" "${LUMINA_LOG_DIR}" "${LUMINA_DATA_DIR}"
  mkdir -p /var/lib/warp /var/lib/cloudflare-warp
  touch "${LUMINA_LOG_DIR}/warp-svc.log" "${LUMINA_LOG_DIR}/usque.log" "${LUMINA_LOG_DIR}/socat.log"
}

configure_ssl() {
  if [ "${PANEL_SSL_ENABLED}" != "true" ]; then
    return
  fi

  log "SSL is enabled for panel"
  mkdir -p "$(dirname "${PANEL_SSL_CERT_FILE}")" "$(dirname "${PANEL_SSL_KEY_FILE}")"

  if [ -f "${PANEL_SSL_CERT_FILE}" ] && [ -f "${PANEL_SSL_KEY_FILE}" ]; then
    log "Using existing SSL certificate and key"
    return
  fi

  if [ "${PANEL_SSL_AUTO_SELF_SIGNED}" != "true" ]; then
    error "SSL enabled but certificate/key not found and PANEL_SSL_AUTO_SELF_SIGNED=false"
    exit 1
  fi

  warn "Generating self-signed SSL certificate for domain: ${PANEL_SSL_DOMAIN}"
  openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
    -keyout "${PANEL_SSL_KEY_FILE}" \
    -out "${PANEL_SSL_CERT_FILE}" \
    -subj "/CN=${PANEL_SSL_DOMAIN}" >/dev/null 2>&1

  chmod 600 "${PANEL_SSL_KEY_FILE}"
  chmod 644 "${PANEL_SSL_CERT_FILE}"
}

write_env_file() {
  log "Writing environment file: ${ENV_FILE}"
  cat > "${ENV_FILE}" <<EOF
PANEL_PORT=${PANEL_PORT}
SOCKS5_PORT=${SOCKS5_PORT}
WARP_BACKEND=${WARP_BACKEND}
WARP_DATA_DIR=${LUMINA_DATA_DIR}
USQUE_CONFIG_PATH=/var/lib/warp/config.json
STATIC_DIR=${STATIC_DIR}
PYTHONUNBUFFERED=1
LUMINA_SERVICE_MANAGER=systemd
LUMINA_ENV_FILE=${ENV_FILE}
LUMINA_BACKEND_DIR=${BACKEND_DIR}
LUMINA_UVICORN_BIN=${BACKEND_DIR}/venv/bin/uvicorn
PANEL_SSL_ENABLED=${PANEL_SSL_ENABLED}
PANEL_SSL_CERT_FILE=${PANEL_SSL_CERT_FILE}
PANEL_SSL_KEY_FILE=${PANEL_SSL_KEY_FILE}
PANEL_SSL_AUTO_SELF_SIGNED=${PANEL_SSL_AUTO_SELF_SIGNED}
PANEL_SSL_DOMAIN=${PANEL_SSL_DOMAIN}
PANEL_HTTP_REDIRECT_STATUS=${PANEL_HTTP_REDIRECT_STATUS}
PANEL_HTTP_REDIRECT_FORCE_DOMAIN=${PANEL_HTTP_REDIRECT_FORCE_DOMAIN}
PANEL_HTTP_HTTPS_MUX_ENABLED=${PANEL_HTTP_HTTPS_MUX_ENABLED}
PANEL_HTTPS_INTERNAL_PORT=${PANEL_HTTPS_INTERNAL_PORT}
WARP_SVC_RUST_LOG=${WARP_SVC_RUST_LOG}
EOF
  chmod 600 "${ENV_FILE}"
}

write_wrapper_scripts() {
  log "Writing runtime wrapper scripts..."

cat > /usr/local/bin/lumina-run-api.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
ENV_FILE="/etc/lumina/lumina.env"
[ -f "${ENV_FILE}" ] && set -a && . "${ENV_FILE}" && set +a
: "${WARP_DATA_DIR:=/var/lib/lumina}"
: "${PANEL_PORT:=8000}"
: "${PANEL_SSL_ENABLED:=true}"
: "${PANEL_SSL_CERT_FILE:=/etc/lumina/ssl/panel.crt}"
: "${PANEL_SSL_KEY_FILE:=/etc/lumina/ssl/panel.key}"
: "${PANEL_SSL_AUTO_SELF_SIGNED:=true}"
: "${PANEL_SSL_DOMAIN:=localhost}"
: "${PANEL_HTTP_REDIRECT_STATUS:=308}"
: "${PANEL_HTTP_HTTPS_MUX_ENABLED:=true}"
: "${PANEL_HTTPS_INTERNAL_PORT:=8443}"
: "${PANEL_HTTP_REDIRECT_FORCE_DOMAIN:=}"

CONFIG_DB="${WARP_DATA_DIR}/config.db"
if [ -f "${CONFIG_DB}" ]; then
  PYTHON_BIN="${LUMINA_BACKEND_DIR}/venv/bin/python"
  if [ ! -x "${PYTHON_BIN}" ]; then
    PYTHON_BIN="$(command -v python3)"
  fi
  DB_OVERRIDES="$("${PYTHON_BIN}" - "${CONFIG_DB}" <<'PY'
import json
import shlex
import sqlite3
import sys

db_path = sys.argv[1]
mapping = {
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

def to_text(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)

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
        text = to_text(parsed).strip()
        if env_key in {"PANEL_SSL_CERT_FILE", "PANEL_SSL_KEY_FILE", "PANEL_SSL_DOMAIN"} and not text:
            continue
        print(f"{env_key}={shlex.quote(text)}")
finally:
    conn.close()
PY
)"
  if [ -n "${DB_OVERRIDES}" ]; then
    eval "${DB_OVERRIDES}"
  fi
fi

MUX_PID=""

cleanup_redirect() {
  if [ -n "${MUX_PID}" ] && kill -0 "${MUX_PID}" 2>/dev/null; then
    kill "${MUX_PID}" 2>/dev/null || true
    wait "${MUX_PID}" 2>/dev/null || true
  fi
}

trap cleanup_redirect EXIT INT TERM

if [ "${PANEL_SSL_ENABLED:-true}" = "true" ] && [ "${PANEL_SSL_AUTO_SELF_SIGNED:-true}" = "true" ] && { [ ! -f "${PANEL_SSL_CERT_FILE:-}" ] || [ ! -f "${PANEL_SSL_KEY_FILE:-}" ]; }; then
  PYTHON_BIN="${LUMINA_BACKEND_DIR}/venv/bin/python"
  if [ ! -x "${PYTHON_BIN}" ]; then
    PYTHON_BIN="$(command -v python3)"
  fi

  PYTHONPATH="${LUMINA_BACKEND_DIR}" "${PYTHON_BIN}" - "${PANEL_SSL_CERT_FILE:-}" "${PANEL_SSL_KEY_FILE:-}" "${PANEL_SSL_DOMAIN:-localhost}" <<'PY'
import sys
from app.utils.tls import ensure_self_signed_certificate

cert_path, key_path, domain = sys.argv[1], sys.argv[2], sys.argv[3]
if cert_path and key_path:
    ensure_self_signed_certificate(cert_path=cert_path, key_path=key_path, common_name=domain)
PY
fi

if [ "${PANEL_SSL_ENABLED:-true}" = "true" ] && [ -f "${PANEL_SSL_CERT_FILE:-}" ] && [ -f "${PANEL_SSL_KEY_FILE:-}" ]; then
  APP_PORT="${PANEL_PORT:-8000}"

  if [ "${PANEL_HTTP_HTTPS_MUX_ENABLED:-true}" = "true" ]; then
    if [ "${PANEL_HTTPS_INTERNAL_PORT:-8443}" = "${PANEL_PORT:-8000}" ]; then
      echo "WARN: PANEL_HTTP_HTTPS_MUX_ENABLED=true but PANEL_HTTPS_INTERNAL_PORT equals PANEL_PORT (${PANEL_PORT:-8000}), skipping mux" >&2
    else
      PYTHON_BIN="${LUMINA_BACKEND_DIR}/venv/bin/python"
      if [ ! -x "${PYTHON_BIN}" ]; then
        PYTHON_BIN="$(command -v python3)"
      fi
      PYTHONPATH="${LUMINA_BACKEND_DIR}" "${PYTHON_BIN}" -m app.utils.http_tls_multiplexer &
      MUX_PID="$!"
      APP_PORT="${PANEL_HTTPS_INTERNAL_PORT:-8443}"
    fi
  fi

  exec "${LUMINA_UVICORN_BIN}" app.main:app --host 0.0.0.0 --port "${APP_PORT}" --app-dir "${LUMINA_BACKEND_DIR}" \
    --ssl-certfile "${PANEL_SSL_CERT_FILE}" --ssl-keyfile "${PANEL_SSL_KEY_FILE}"
fi

exec "${LUMINA_UVICORN_BIN}" app.main:app --host 0.0.0.0 --port "${PANEL_PORT:-8000}" --app-dir "${LUMINA_BACKEND_DIR}"
EOF
  chmod +x /usr/local/bin/lumina-run-api.sh

  cat > /usr/local/bin/lumina-run-warp-svc.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
ENV_FILE="/etc/lumina/lumina.env"
[ -f "${ENV_FILE}" ] && set -a && . "${ENV_FILE}" && set +a
export RUST_LOG="${WARP_SVC_RUST_LOG:-warn}"
exec /usr/bin/warp-svc
EOF
  chmod +x /usr/local/bin/lumina-run-warp-svc.sh

  cat > /usr/local/bin/lumina-run-usque.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
ENV_FILE="/etc/lumina/lumina.env"
[ -f "${ENV_FILE}" ] && set -a && . "${ENV_FILE}" && set +a
exec /usr/local/bin/usque -c "${USQUE_CONFIG_PATH:-/var/lib/warp/config.json}" socks -b 0.0.0.0 -p "${SOCKS5_PORT:-1080}"
EOF
  chmod +x /usr/local/bin/lumina-run-usque.sh

  cat > /usr/local/bin/lumina-run-socat.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
ENV_FILE="/etc/lumina/lumina.env"
[ -f "${ENV_FILE}" ] && set -a && . "${ENV_FILE}" && set +a
exec /usr/bin/socat "TCP-LISTEN:${SOCKS5_PORT:-1080},reuseaddr,bind=0.0.0.0,fork" "TCP:127.0.0.1:40001"
EOF
  chmod +x /usr/local/bin/lumina-run-socat.sh
}

write_systemd_units() {
  log "[8/9] Writing systemd service units..."

  cat > /etc/systemd/system/lumina-api.service <<EOF
[Unit]
Description=Lumina API and Web Panel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=${BACKEND_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=/usr/local/bin/lumina-run-api.sh
Restart=always
RestartSec=3
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

  cat > /etc/systemd/system/lumina-warp-svc.service <<EOF
[Unit]
Description=Lumina Cloudflare WARP daemon
After=network-online.target dbus.service
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
EnvironmentFile=${ENV_FILE}
ExecStart=/usr/local/bin/lumina-run-warp-svc.sh
Restart=always
RestartSec=2
StandardOutput=append:${LUMINA_LOG_DIR}/warp-svc.log
StandardError=append:${LUMINA_LOG_DIR}/warp-svc.log

[Install]
WantedBy=multi-user.target
EOF

  cat > /etc/systemd/system/lumina-usque.service <<EOF
[Unit]
Description=Lumina usque proxy daemon
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
EnvironmentFile=${ENV_FILE}
ExecStart=/usr/local/bin/lumina-run-usque.sh
Restart=always
RestartSec=2
StandardOutput=append:${LUMINA_LOG_DIR}/usque.log
StandardError=append:${LUMINA_LOG_DIR}/usque.log

[Install]
WantedBy=multi-user.target
EOF

  cat > /etc/systemd/system/lumina-socat.service <<EOF
[Unit]
Description=Lumina SOCKS5 bridge (socat)
After=network-online.target lumina-warp-svc.service
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
EnvironmentFile=${ENV_FILE}
ExecStart=/usr/local/bin/lumina-run-socat.sh
Restart=always
RestartSec=2
StandardOutput=append:${LUMINA_LOG_DIR}/socat.log
StandardError=append:${LUMINA_LOG_DIR}/socat.log

[Install]
WantedBy=multi-user.target
EOF
}

write_logrotate() {
  cat > /etc/logrotate.d/lumina <<EOF
${LUMINA_LOG_DIR}/*.log {
  rotate 7
  daily
  size 20M
  missingok
  notifempty
  compress
  delaycompress
  copytruncate
}
EOF
}

cleanup_legacy_supervisor() {
  log "Cleaning legacy supervisor config (if any)..."
  if command -v supervisorctl >/dev/null 2>&1; then
    supervisorctl stop warppool-api warp-svc usque usque-tun socat >/dev/null 2>&1 || true
    rm -f /etc/supervisor/conf.d/warppool.conf
    supervisorctl reread >/dev/null 2>&1 || true
    supervisorctl update >/dev/null 2>&1 || true
  fi
}

activate_services() {
  log "[9/9] Activating systemd services..."
  systemctl daemon-reload

  # Disable vendor-provided warp-svc unit to avoid conflicts with Lumina-managed unit.
  systemctl disable --now warp-svc.service >/dev/null 2>&1 || true

  # API auto-starts; other services are on-demand and controlled by Lumina backend.
  systemctl enable --now lumina-api.service
  systemctl disable --now lumina-warp-svc.service >/dev/null 2>&1 || true
  systemctl disable --now lumina-usque.service >/dev/null 2>&1 || true
  systemctl disable --now lumina-socat.service >/dev/null 2>&1 || true
}

show_summary() {
  local scheme="http"
  if [ "${PANEL_SSL_ENABLED}" = "true" ]; then
    scheme="https"
  fi

  echo
  log "=== Installation Complete ==="
  echo "Service status:"
  systemctl --no-pager --full status lumina-api.service | sed -n '1,8p' || true
  echo
  echo -e "Web UI: ${GREEN}${scheme}://localhost:${PANEL_PORT}${NC}"
  echo -e "SOCKS5: ${GREEN}socks5://127.0.0.1:${SOCKS5_PORT}${NC} (active only when connected)"
  echo -e "Env file: ${GREEN}${ENV_FILE}${NC}"
}

main() {
  require_root
  export DEBIAN_FRONTEND=noninteractive
  export NEEDRESTART_MODE=a
  export NEEDRESTART_SUSPEND=1

  PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  BACKEND_DIR="${PROJECT_ROOT}/backend"
  FRONTEND_DIR="${PROJECT_ROOT}/frontend"
  STATIC_DIR="${BACKEND_DIR}/static"

  LUMINA_ETC_DIR="/etc/lumina"
  LUMINA_SSL_DIR="/etc/lumina/ssl"
  LUMINA_LOG_DIR="/var/log/lumina"
  LUMINA_DATA_DIR="/var/lib/lumina"
  ENV_FILE="${LUMINA_ETC_DIR}/lumina.env"

  PANEL_PORT="${PANEL_PORT:-8000}"
  SOCKS5_PORT="${SOCKS5_PORT:-1080}"
  WARP_BACKEND="${WARP_BACKEND:-usque}"
  PANEL_SSL_ENABLED="${PANEL_SSL_ENABLED:-true}"
  PANEL_SSL_CERT_FILE="${PANEL_SSL_CERT_FILE:-${LUMINA_SSL_DIR}/panel.crt}"
  PANEL_SSL_KEY_FILE="${PANEL_SSL_KEY_FILE:-${LUMINA_SSL_DIR}/panel.key}"
  PANEL_SSL_AUTO_SELF_SIGNED="${PANEL_SSL_AUTO_SELF_SIGNED:-true}"
  PANEL_SSL_DOMAIN="${PANEL_SSL_DOMAIN:-localhost}"
  PANEL_HTTP_REDIRECT_STATUS="${PANEL_HTTP_REDIRECT_STATUS:-308}"
  PANEL_HTTP_REDIRECT_FORCE_DOMAIN="${PANEL_HTTP_REDIRECT_FORCE_DOMAIN:-}"
  PANEL_HTTP_HTTPS_MUX_ENABLED="${PANEL_HTTP_HTTPS_MUX_ENABLED:-true}"
  PANEL_HTTPS_INTERNAL_PORT="${PANEL_HTTPS_INTERNAL_PORT:-8443}"
  WARP_SVC_RUST_LOG="${WARP_SVC_RUST_LOG:-warn}"

  validate_port "PANEL_PORT" "${PANEL_PORT}"
  validate_port "SOCKS5_PORT" "${SOCKS5_PORT}"

  log "=== Lumina Linux Installer (systemd mode) ==="
  log "Project root: ${PROJECT_ROOT}"

  install_system_deps
  install_nodejs_if_needed
  install_cloudflare_warp_if_needed
  install_usque_if_needed
  setup_python_env
  build_frontend
  prepare_directories
  configure_ssl
  write_env_file
  write_wrapper_scripts
  write_systemd_units
  write_logrotate
  cleanup_legacy_supervisor
  activate_services
  show_summary
}

main "$@"
