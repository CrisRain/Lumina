# Linux Local Installation Guide (No Docker)

This guide explains how to install and run WarpPool directly on a Linux system (e.g., Ubuntu/Debian) without using Docker.

## Prerequisites

- Ubuntu 20.04/22.04 or Debian 11/12 (Recommended)
- Root access (sudo)
- Internet connection

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your/repo.git warppool
    cd warppool
    ```

2.  **Make the installer executable:**
    ```bash
    chmod +x linux_install.sh
    ```

3.  **Run the installer:**
    ```bash
    sudo ./linux_install.sh
    ```

    This script will automatically:
    -   Install system dependencies (Python, Node.js, Supervisor, etc.).
    -   Install Cloudflare WARP official client.
    -   Download `usque` and `gost` helper binaries to `/usr/local/bin`.
    -   Set up a Python virtual environment and install dependencies.
    -   Build the Vue.js frontend and copy it to the backend's static directory.
    -   Configure `supervisor` to manage the services (API, WARP, Proxies).

## Management

Once installed, the services are managed by `supervisor`.

-   **Check Status:**
    ```bash
    sudo supervisorctl status
    ```

-   **Restart All Services:**
    ```bash
    sudo supervisorctl restart all
    ```

-   **View Logs:**
    ```bash
    tail -f /var/log/warppool/api.log
    ```

## Access

-   **Web UI:** http://localhost:8000
-   **SOCKS5 Proxy:** `socks5://localhost:1080` (when connected)
-   **HTTP Proxy:** `http://localhost:8080` (when connected)

## Uninstallation

To remove the configuration:

1.  Stop services:
    ```bash
    sudo supervisorctl stop all
    ```
2.  Remove supervisor config:
    ```bash
    sudo rm /etc/supervisor/conf.d/warppool.conf
    sudo supervisorctl reread
    sudo supervisorctl update
    ```
3.  Enable system WARP service (optional):
    ```bash
    sudo systemctl enable --now warp-svc
    ```
