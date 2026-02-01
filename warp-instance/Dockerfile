FROM ubuntu:22.04

RUN apt-get update && apt-get install -y curl gpg lsb-release ca-certificates dbus

# Install Cloudflare Registry
RUN curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | gpg --yes --dearmor --output /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ $(lsb_release -cs) main" | tee /etc/apt/sources.list.d/cloudflare-client.list

# Install WARP
RUN apt-get update && apt-get install -y cloudflare-warp socat

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 40000

CMD ["/entrypoint.sh"]
