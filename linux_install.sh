#!/bin/bash
set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}=== Lumina Linux Installer ===${NC}"

# Check for root
if [ "$EUID" -ne 0 ]; then 
  echo -e "${RED}Please run as root${NC}"
  exit 1
fi

# Suppress all interactive prompts (needrestart, dpkg, etc.)
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a
export NEEDRESTART_SUSPEND=1

PROJECT_ROOT=$(pwd)
echo -e "Installing from: ${PROJECT_ROOT}"

# Configurable port defaults
PANEL_PORT=${PANEL_PORT:-8000}
SOCKS5_PORT=${SOCKS5_PORT:-1080}

# 1. Install System Dependencies
echo -e "${GREEN}[1/8] Installing system dependencies...${NC}"
apt-get update -qq
apt-get install -y -qq -o Dpkg::Options::="--force-confold" \
    curl gpg lsb-release ca-certificates dbus \
    python3 python3-pip python3-venv python3-full socat \
    iputils-ping iproute2 iptables procps supervisor unzip tar jq

# 2. Install Node.js (if not present)
if ! command -v node &> /dev/null; then
    echo -e "${GREEN}[2/8] Installing Node.js...${NC}"
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y -qq nodejs
else
    echo -e "${GREEN}[2/8] Node.js already installed ($(node -v))${NC}"
fi

# 3. Install Cloudflare WARP
echo -e "${GREEN}[3/8] Installing Cloudflare WARP...${NC}"
if ! command -v warp-cli &> /dev/null; then
    rm -f /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg
    curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | gpg --yes --dearmor --output /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg
    echo "deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ $(lsb_release -cs) main" | tee /etc/apt/sources.list.d/cloudflare-client.list
    apt-get update -qq
    apt-get install -y -qq cloudflare-warp
else
    echo "WARP already installed"
fi

# 4. Install Helper Binaries (usque)
echo -e "${GREEN}[4/8] Installing usque...${NC}"

# usque — auto-detect latest version
if [ ! -f /usr/local/bin/usque ]; then
    echo "Downloading usque (latest)..."
    LATEST_TAG=$(curl -fsSL https://api.github.com/repos/Diniboy1123/usque/releases/latest | jq -r '.tag_name')
    USQUE_VERSION=$(echo "$LATEST_TAG" | sed 's/^v//')
    
    echo "Detected usque version: ${USQUE_VERSION}"
    
    # Construct URL for linux amd64
    DOWNLOAD_URL="https://github.com/Diniboy1123/usque/releases/download/${LATEST_TAG}/usque_${USQUE_VERSION}_linux_amd64.zip"
    
    curl -L -o /tmp/usque.zip "$DOWNLOAD_URL"
    
    if [ ! -s /tmp/usque.zip ]; then
        echo -e "${RED}Failed to download usque. Check network or version.${NC}"
        exit 1
    fi
    
    unzip -o /tmp/usque.zip -d /tmp/
    if [ -f "/tmp/usque" ]; then
        mv /tmp/usque /usr/local/bin/usque
        chmod +x /usr/local/bin/usque
        echo "Usque installed to /usr/local/bin/usque"
    else
        echo -e "${RED}Usque binary not found in zip.${NC}"
        # Try finding it in subfolder if structure changed, or fail
    fi
    rm -f /tmp/usque.zip
else
    echo "usque already installed"
fi

# 5. Setup Python Environment
echo -e "${GREEN}[5/8] Setting up Python environment...${NC}"
if [ ! -d "${PROJECT_ROOT}/backend" ]; then
    echo -e "${RED}Error: 'backend' directory not found in ${PROJECT_ROOT}${NC}"
    exit 1
fi

cd "${PROJECT_ROOT}/backend"
# Create venv if not exists
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -U pip -q
pip install -q -r requirements.txt

# 6. Build Frontend
echo -e "${GREEN}[6/8] Building Frontend...${NC}"
cd "${PROJECT_ROOT}/frontend"
npm install --silent
npm run build

# Link frontend dist to backend static
echo "Deploying frontend build..."
STATIC_TARGET="${PROJECT_ROOT}/backend/static"
rm -rf "${STATIC_TARGET}"
mkdir -p "${STATIC_TARGET}"
cp -r dist/* "${STATIC_TARGET}/"

# 7. Setup Directories
echo -e "${GREEN}[7/8] Setting up directories...${NC}"
mkdir -p /var/lib/warp
mkdir -p /var/log/warppool

# 8. Configure Supervisor
echo -e "${GREEN}[8/8] Configuring Supervisor...${NC}"

# Stop systemd warp-svc to let supervisor manage it
systemctl disable --now warp-svc 2>/dev/null || true

# Write supervisor config
VENV_UVICORN="${PROJECT_ROOT}/backend/venv/bin/uvicorn"
BACKEND_DIR="${PROJECT_ROOT}/backend"
# Ensure we point to the static dir we just populated
STATIC_DIR="${PROJECT_ROOT}/backend/static"

cat > /etc/supervisor/conf.d/warppool.conf <<SUPERVISOREOF
[program:warppool-api]
command=${VENV_UVICORN} app.main:app --host 0.0.0.0 --port ${PANEL_PORT}
directory=${BACKEND_DIR}
user=root
autostart=true
autorestart=true
startsecs=5
redirect_stderr=true
stdout_logfile=/var/log/warppool/api.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=3
environment=STATIC_DIR="${STATIC_DIR}",PYTHONUNBUFFERED="1",PANEL_PORT="${PANEL_PORT}",SOCKS5_PORT="${SOCKS5_PORT}"

[program:warp-svc]
command=/usr/bin/warp-svc
user=root
autostart=false
autorestart=true
redirect_stderr=true
stdout_logfile=/dev/null
priority=5

[program:usque]
command=/usr/local/bin/usque -c /var/lib/warp/config.json socks -b 0.0.0.0 -p ${SOCKS5_PORT}
user=root
autostart=false
autorestart=true
redirect_stderr=true
stdout_logfile=/dev/null
priority=10

[program:usque-tun]
command=/usr/local/bin/usque -c /var/lib/warp/config.json nativetun
user=root
autostart=false
autorestart=true
redirect_stderr=true
stdout_logfile=/dev/null
priority=10

[program:socat]
command=/usr/bin/socat TCP-LISTEN:${SOCKS5_PORT},reuseaddr,bind=0.0.0.0,fork TCP:127.0.0.1:40001
user=root
autostart=false
autorestart=true
redirect_stderr=true
stdout_logfile=/dev/null
priority=20
SUPERVISOREOF

# Verify config was written correctly
echo "Supervisor config written to /etc/supervisor/conf.d/warppool.conf"

# Reload supervisor
supervisorctl reread
supervisorctl update

# Wait a moment for services to start
sleep 3

# Show status
echo ""
echo -e "${GREEN}=== Installation Complete ===${NC}"
supervisorctl status
echo ""
echo -e "Web UI: ${GREEN}http://localhost:${PANEL_PORT}${NC}"
echo -e "SOCKS5: ${GREEN}socks5://127.0.0.1:${SOCKS5_PORT}${NC} (only active if connected)"
