#!/bin/sh
# Container initialization — runs once at startup before services start
set -e

# Runtime directories
mkdir -p /var/lib/warp /var/lib/cloudflare-warp /app/data/kernels /var/log

# Persist dynamic env vars into the s6 container environment store
# so all services launched via with-contenv pick them up correctly
S6_ENV=/var/run/s6/container_environment
mkdir -p "${S6_ENV}"

printf '%s' "${SOCKS5_PORT:-1080}"  > "${S6_ENV}/SOCKS5_PORT"
printf '%s' "${PANEL_PORT:-8000}"   > "${S6_ENV}/PANEL_PORT"
printf '%s' "${WARP_BACKEND:-usque}" > "${S6_ENV}/WARP_BACKEND"
[ -n "${WARP_DATA_DIR}" ] && printf '%s' "${WARP_DATA_DIR}" > "${S6_ENV}/WARP_DATA_DIR"
[ -n "${PANEL_PASSWORD}" ] && printf '%s' "${PANEL_PASSWORD}" > "${S6_ENV}/PANEL_PASSWORD"
