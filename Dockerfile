# ============================================================
# Lumina Dockerfile — multi-stage, layer-optimized build
# ============================================================

# --------------- ARGs (pinned versions) ---------------
ARG NODE_VERSION=20
ARG UBUNTU_VERSION=22.04
ARG ALPINE_VERSION=3.21
ARG S6_OVERLAY_VERSION=3.2.0.2
ARG CLOUDFLARE_WARP_KEY_REFRESH=2025-09-12

# ============================================================
# Stage 1: Download external binaries
# ============================================================
FROM alpine:${ALPINE_VERSION} AS downloader
WORKDIR /tmp
RUN apk add --no-cache curl unzip jq xz

# Download usque (WARP MASQUE client) — auto-detect latest release
RUN USQUE_VERSION=$(curl -fsSL https://api.github.com/repos/Diniboy1123/usque/releases/latest | jq -r '.tag_name' | sed 's/^v//') \
    && echo "Detected usque version: ${USQUE_VERSION}" \
    && curl -fSL -o usque.zip \
    "https://github.com/Diniboy1123/usque/releases/download/v${USQUE_VERSION}/usque_${USQUE_VERSION}_linux_amd64.zip" \
    && unzip usque.zip \
    && chmod +x usque \
    && rm -f usque.zip

# Download and extract s6-overlay in Alpine (native xz support); result copied to Ubuntu stage
ARG S6_OVERLAY_VERSION
RUN mkdir /s6-overlay \
    && curl -fsSL "https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz" \
    | tar -C /s6-overlay -Jxp \
    && curl -fsSL "https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-x86_64.tar.xz" \
    | tar -C /s6-overlay -Jxp

# ============================================================
# Stage 2: Build Frontend
# ============================================================
FROM node:${NODE_VERSION}-alpine AS frontend-build
WORKDIR /build

# Install deps first (layer cache for package.json changes only)
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --prefer-offline 2>/dev/null || npm install

# Then copy source & build
COPY frontend/ .
RUN npm run build

# ============================================================
# Stage 3: Final runtime image
# ============================================================
FROM ubuntu:${UBUNTU_VERSION}

LABEL org.opencontainers.image.title="Lumina" \
    org.opencontainers.image.description="Cloudflare WARP management dashboard with proxy support" \
    org.opencontainers.image.source="https://github.com/CrisRain/lumina"

# ---- Install s6-overlay (pre-extracted in downloader stage) ----
COPY --from=downloader /s6-overlay /

# ---- System dependencies (single RUN to minimize layers) ----
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gpg lsb-release ca-certificates dbus \
    python3 python3-pip \
    socat iputils-ping iproute2 iptables procps \
    && ARCH="$(dpkg --print-architecture)" \
    && if [ "$ARCH" = "amd64" ]; then \
    echo "Cloudflare WARP key refresh: ${CLOUDFLARE_WARP_KEY_REFRESH}" \
    && rm -f /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg \
    && curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg \
    | gpg --yes --dearmor --output /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ $(lsb_release -cs) main" \
    | tee /etc/apt/sources.list.d/cloudflare-client.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends cloudflare-warp \
    # Prevent cloudflare-warp from being auto-removed
    && apt-mark manual cloudflare-warp \
    # Debug: show where warp binaries were installed
    && echo "=== Searching for warp binaries ===" \
    && find / -name 'warp-cli' -o -name 'warp-svc' 2>/dev/null || true \
    && dpkg -L cloudflare-warp 2>/dev/null | head -30 || true \
    # Create symlinks: try known paths, then fall back to find
    && for BIN in warp-cli warp-svc; do \
    if ! command -v "$BIN" >/dev/null 2>&1; then \
    FOUND=$(find /opt /usr -name "$BIN" -type f 2>/dev/null | head -1); \
    if [ -n "$FOUND" ]; then \
    echo "Symlinking $FOUND -> /usr/bin/$BIN"; \
    ln -sf "$FOUND" "/usr/bin/$BIN"; \
    fi; \
    fi; \
    done \
    && command -v warp-cli >/dev/null && command -v warp-svc >/dev/null; \
    else \
    echo "Skipping cloudflare-warp install on arch: $ARCH"; \
    fi \
    # Only remove lsb-release (build-only). DO NOT purge gpg — cloudflare-warp depends on gnupg2.
    && apt-get purge -y lsb-release \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# ---- Copy external binaries ----
COPY --from=downloader /tmp/usque /usr/local/bin/usque

# ---- Python app setup ----
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PATH="/opt/cloudflare-warp/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
    WARP_DATA_DIR=/app/data \
    SOCKS5_PORT=1080 \
    PANEL_PORT=8000 \
    # s6-overlay: no CMD to run, services are managed via s6-rc
    S6_CMD_WAIT_FOR_SERVICES_MAXTIME=0

# Install Python deps (separate layer for caching)
COPY backend/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# ---- Create runtime directories ----
RUN mkdir -p /app/data/kernels /var/lib/warp /var/lib/cloudflare-warp /var/log

# ---- s6-overlay service definitions ----
COPY backend/s6-rc.d /etc/s6-overlay/s6-rc.d/
# s6-overlay v3 legacy cont-init.d scripts must live at /etc/cont-init.d/
COPY backend/cont-init.d /etc/cont-init.d/
RUN chmod +x /etc/cont-init.d/01-init.sh \
    && find /etc/s6-overlay/s6-rc.d -name run -exec chmod +x {} + \
    # Strip Windows CRLF line endings from all s6/cont-init scripts
    && find /etc/s6-overlay/s6-rc.d /etc/cont-init.d -type f | while read f; do \
    tr -d '\r' < "$f" > "$f.tmp" && mv "$f.tmp" "$f" && chmod +x "$f"; \
    done \
    # Only warppool-api auto-starts; warp-svc/usque/socat started on-demand by Python
    && rm -f /etc/s6-overlay/s6-rc.d/user/contents.d/warp-svc \
    /etc/s6-overlay/s6-rc.d/user/contents.d/usque \
    /etc/s6-overlay/s6-rc.d/user/contents.d/socat

# ---- Application code (changes most often → last) ----
COPY backend/app /app/app
COPY --from=frontend-build /build/dist /app/static

# ---- Ports ----
# 8000: Web UI + API (default, configurable via PANEL_PORT)
# 1080: SOCKS5 Proxy (default, configurable via SOCKS5_PORT)
EXPOSE 8000 1080

# ---- Health check ----
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PANEL_PORT:-8000}/api/status || exit 1

ENTRYPOINT ["/init"]
