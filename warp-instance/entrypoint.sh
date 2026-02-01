#!/bin/bash
set -e

# Start dbus (warp-svc needs it)
mkdir -p /run/dbus
if [ -f /run/dbus/pid ]; then
    rm /run/dbus/pid
fi
dbus-daemon --config-file=/usr/share/dbus-1/system.conf --print-address &

# Start warp-svc
warp-svc --accept-tos &
item=$!

# Wait for warp-svc to be ready
sleep 2

# Register (if not registered)
# Register (if not registered)
if [ ! -f /var/lib/cloudflare-warp/reg.json ]; then
    warp-cli --accept-tos registration delete || true
    warp-cli --accept-tos registration new
fi

# Set proxy mode
warp-cli --accept-tos mode proxy
warp-cli --accept-tos proxy port 40001

# Start socat to forward 0.0.0.0:40000 -> 127.0.0.1:40001
socat TCP-LISTEN:40000,fork,bind=0.0.0.0 TCP:127.0.0.1:40001 &

# Connect
warp-cli --accept-tos connect

# Keep alive
tail -f /dev/null
