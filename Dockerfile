# Stage 1: Build Frontend
FROM node:20-alpine AS frontend-build
WORKDIR /frontend_app
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ .
# Ensure we build for production
RUN npm run build

# Stage 2: Final Monolithic Image
FROM ubuntu:22.04

# Install basic deps + python + warp deps + networking tools
RUN apt-get update && apt-get install -y \
    curl gpg lsb-release ca-certificates dbus \
    python3 python3-pip socat supervisor \
    iputils-ping iproute2 \
    && rm -rf /var/lib/apt/lists/*

# Install Cloudflare Warp
RUN curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | gpg --yes --dearmor --output /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ $(lsb_release -cs) main" | tee /etc/apt/sources.list.d/cloudflare-client.list \
    && apt-get update && apt-get install -y cloudflare-warp

# Setup Python App
WORKDIR /app
COPY controller-app/requirements.txt .
# Remove docker from requirements if present, or just install what we need. 
# We'll install manually to be safe/clean or rely on updated requirements.txt. 
# Better to update requirements.txt first.
RUN pip3 install --no-cache-dir -r requirements.txt
# Install uvicorn explicitly if not in requirements
RUN pip3 install uvicorn

# Copy Backend Code
COPY controller-app/app /app/app
# Copy Frontend Build
COPY --from=frontend-build /frontend_app/dist /app/static

# Configs
COPY controller-app/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY controller-app/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Ports
# 8000: Web UI + API (FastAPI serves static files now)
# 1080: SOCKS5 Proxy
EXPOSE 8000 1080

CMD ["/entrypoint.sh"]
