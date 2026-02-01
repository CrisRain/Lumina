#!/bin/bash
set -e

# Start dbus (warp-svc needs it)
mkdir -p /run/dbus
if [ -f /run/dbus/pid ]; then
    rm /run/dbus/pid
fi
dbus-daemon --config-file=/usr/share/dbus-1/system.conf --print-address &

# Initialize WARP (Wait for warp-svc to be started by supervisor? No, supervisor starts things in parallel/order)
# But we need to register AT LEAST ONCE.
# Attempting to register blindly before warp-svc is running will fail.
# So we have a chicken/egg problem if we rely on supervisor for everything.
# Solution: Start warp-svc TEMPORARILY in background, do setup, then kill it? 
# OR: Just run a setup script as a one-shot supervisor process?
# Better: Just let supervisor manage warp-svc, and have a separate "bootstrap" script that loops until warp-svc is ready, then registers.
# BUT, simple approach:
# We can start supervisord. One of the programs can be a "configurator" script.
# OR, we manual start warp-svc here, configure, kill it, then let supervisord take over.

echo "Initializing WARP setup..."
# Start warp-svc in background for setup
warp-svc --accept-tos &
WARP_PID=$!
sleep 2

# Register
if [ ! -f /var/lib/cloudflare-warp/reg.json ]; then
    echo "Registering new WARP account..."
    warp-cli --accept-tos registration delete || true
    warp-cli --accept-tos registration new
    echo "Registration complete."
fi

# Set proxy mode
echo "Configuring Proxy Mode..."
warp-cli --accept-tos mode proxy
warp-cli --accept-tos proxy port 40001
warp-cli --accept-tos connect

# Kill the temporary warp-svc
echo "Killing temporary warp-svc..."
kill $WARP_PID
wait $WARP_PID || true

echo "Starting Supervisord..."
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
