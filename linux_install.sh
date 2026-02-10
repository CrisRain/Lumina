#!/bin/bash
set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}=== WarpPool Linux Installer ===${NC}"

# Check for root
if [ "$EUID" -ne 0 ]; then 
  echo -e "${RED}Please run as root${NC}"
  exit 1
fi

PROJECT_ROOT=$(pwd)
echo -e "Installing from: ${PROJECT_ROOT}"

# 1. Install System Dependencies
echo -e "${GREEN}[1/8] Installing system dependencies...${NC}"
apt-get update
apt-get install -y curl gpg lsb-release ca-certificates dbus \
    python3 python3-pip python3-venv socat \
    iputils-ping iproute2 iptables procps supervisor unzip tar

# 2. Install Node.js (if not present)
if ! command -v node &> /dev/null; then
    echo -e "${GREEN}[2/8] Installing Node.js...${NC}"
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
else
    echo -e "${GREEN}[2/8] Node.js already installed${NC}"
fi

# 3. Install Cloudflare WARP
echo -e "${GREEN}[3/8] Installing Cloudflare WARP...${NC}"
if ! command -v warp-cli &> /dev/null; then
    curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | gpg --yes --dearmor --output /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg
    echo "deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ $(lsb_release -cs) main" | tee /etc/apt/sources.list.d/cloudflare-client.list
    apt-get update
    apt-get install -y cloudflare-warp
else
    echo "WARP already installed"
fi

# 4. Install Helper Binaries (usque)
echo -e "${GREEN}[4/8] Installing usque...${NC}"

# usque — auto-detect latest version
if [ ! -f /usr/local/bin/usque ]; then
    echo "Downloading usque (latest)..."
    USQUE_VERSION=$(curl -fsSL https://api.github.com/repos/Diniboy1123/usque/releases/latest | grep '"tag_name"' | sed 's/.*"v\(.*\)".*/\1/')
    echo "Detected usque version: ${USQUE_VERSION}"
    curl -L -o /tmp/usque.zip "https://github.com/Diniboy1123/usque/releases/download/v${USQUE_VERSION}/usque_${USQUE_VERSION}_linux_amd64.zip"
    unzip -o /tmp/usque.zip -d /tmp/
    mv /tmp/usque /usr/local/bin/usque
    chmod +x /usr/local/bin/usque
    rm /tmp/usque.zip
fi

# 5. Setup Python Environment
echo -e "${GREEN}[5/8] Setting up Python environment...${NC}"
cd "${PROJECT_ROOT}/controller-app"
# Create venv if not exists
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt

# 6. Build Frontend
echo -e "${GREEN}[6/8] Building Frontend...${NC}"
cd "${PROJECT_ROOT}/frontend"
npm install
npm run build

# Link frontend dist to controller static
echo "Linking frontend build..."
mkdir -p "${PROJECT_ROOT}/controller-app/static"
rm -rf "${PROJECT_ROOT}/controller-app/static/*"
cp -r dist/* "${PROJECT_ROOT}/controller-app/static/"

# 7. Setup Directories
echo -e "${GREEN}[7/8] Setting up directories...${NC}"
mkdir -p /var/lib/warp
mkdir -p /var/log/warppool

# 8. Configure Supervisor
echo -e "${GREEN}[8/8] Configuring Supervisor...${NC}"

# Stop systemd warp-svc to let supervisor manage it (or keep it if you prefer)
# For this setup, we will let supervisor manage everything to match Docker behavior
systemctl disable --now warp-svc || true

cat > /etc/supervisor/conf.d/warppool.conf <<EOF
[program:warppool-api]
command=${PROJECT_ROOT}/controller-app/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
directory=${PROJECT_ROOT}/controller-app
user=root
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/warppool/api.log
environment=STATIC_DIR="${PROJECT_ROOT}/controller-app/static"

[program:warp-svc]
command=/usr/bin/warp-svc
user=root
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/dev/null
priority=5

[program:usque]
command=/usr/local/bin/usque -c /var/lib/warp/config.json socks -b 0.0.0.0 -p 1080
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
command=/usr/bin/socat TCP-LISTEN:1080,reuseaddr,bind=0.0.0.0,fork TCP:127.0.0.1:40001
user=root
autostart=false
autorestart=true
redirect_stderr=true
stdout_logfile=/dev/null
priority=20

EOF

# Reload supervisor
supervisorctl reread
supervisorctl update

echo -e "${GREEN}=== Installation Complete ===${NC}"
echo -e "Services should be starting. Check status with: ${GREEN}supervisorctl status${NC}"
echo -e "Web UI: http://localhost:8000"
