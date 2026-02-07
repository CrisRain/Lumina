#!/bin/bash
set -e

# Start DBus (required for warp-svc)
mkdir -p /run/dbus
if [ -f /run/dbus/pid ]; then
  rm /run/dbus/pid
fi
dbus-daemon --config-file=/usr/share/dbus-1/system.conf --print-address --fork

# Create log directory and file for warppool-api
mkdir -p /var/log/supervisor
touch /var/log/warppool-api.log

# Tail the log in background so docker logs can see it
tail -f /var/log/warppool-api.log &

# Start supervisor (which manages warppool-api, usque, socat)
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
