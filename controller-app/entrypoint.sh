#!/bin/bash
set -e

# Start DBus (required for warp-svc)
mkdir -p /run/dbus
if [ -f /run/dbus/pid ]; then
  rm /run/dbus/pid
fi
dbus-daemon --config-file=/usr/share/dbus-1/system.conf --print-address --fork

# Create log file for warppool-api
touch /var/log/warppool-api.log

# Tail the log in background so docker logs can see it
tail -f /var/log/warppool-api.log &

# Start systemd (which manages warp-svc, warppool-api, usque, socat)
exec /sbin/init
