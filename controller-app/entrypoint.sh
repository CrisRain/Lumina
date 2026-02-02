#!/bin/bash
set -e

# Start dbus (warp-svc needs it)
mkdir -p /run/dbus
if [ -f /run/dbus/pid ]; then
    rm /run/dbus/pid
fi
dbus-daemon --config-file=/usr/share/dbus-1/system.conf --print-address &
sleep 1

echo "Starting warp-svc..."
warp-svc --accept-tos &
sleep 3

# Wait for warp-svc to be ready
echo "Waiting for warp-svc to be ready..."
for i in {1..15}; do
    if warp-cli --accept-tos status &>/dev/null; then
        echo "warp-svc is ready!"
        break
    fi
    echo "Waiting... ($i/15)"
    sleep 1
done

# Register if needed
if [ ! -f /var/lib/cloudflare-warp/reg.json ]; then
    echo "Registering new WARP account..."
    warp-cli --accept-tos registration delete || true
    warp-cli --accept-tos registration new
    echo "Registration complete."
fi

# Reset endpoint to default (in case there's a bad cached one)
echo "Resetting endpoint to default..."
warp-cli --accept-tos tunnel endpoint reset || true

# Set MASQUE protocol (required for proxy mode)
echo "Setting MASQUE protocol..."
warp-cli --accept-tos tunnel protocol set MASQUE

# Set proxy mode
echo "Configuring Proxy Mode..."
warp-cli --accept-tos mode proxy
warp-cli --accept-tos proxy port 40001

# Connect WARP
echo "Connecting to WARP..."
warp-cli --accept-tos connect

# Start socat to expose SOCKS5 on port 1080
echo "Starting socat proxy..."
socat TCP-LISTEN:1080,fork,bind=0.0.0.0 TCP:127.0.0.1:40001 &

# Start FastAPI
echo "Starting FastAPI server..."
cd /app
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
