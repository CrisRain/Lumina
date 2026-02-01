# WarpPanel

WarpPanel is a modern web-based control panel for managing a single Cloudflare WARP client instance. It provides a premium, responsive interface to connect, disconnect, and rotate your IP address with ease.

## Features

- **🎯 Single Instance Management**: Control a dedicated WARP container with real-time monitoring
- **🎨 Premium UI**: Built with Vue 3 and Tailwind CSS v4, featuring glassmorphism effects and smooth animations
- **⚡ Real-time Updates**: WebSocket integration for instant status synchronization
- **🔄 IP Rotation**: Rotate your IP address instantly with a single click
- **🔒 SOCKS5 Proxy**: Built-in SOCKS5 proxy server on port `1080`
- **🌍 Connection Info**: View detailed information including IP, city, country, ISP, and protocol

## Architecture

- **Frontend**: Vue 3 + Vite + Tailwind CSS (v4)
- **Backend**: FastAPI (Python)
- **Container**: Cloudflare WARP official client running in Docker

## Getting Started

### Prerequisites

- Docker Desktop (or Docker Engine with Docker Compose)
- Git

### Installation

1. Clone the repository:

```bash
git clone https://github.com/CrisRain/warppanel.git
cd warppanel
```

2. Build and start the services using Docker Compose:

```bash
docker-compose up --build -d
```

3. Access the Web Interface at: **http://localhost:5173**

### Ports

- **Web UI**: 5173
- **API**: 8000
- **SOCKS5 Proxy**: 1080

## Usage

1. Click **Connect** to start the WARP connection
2. Monitor real-time status and connection information
3. Use **Rotate IP** to get a new IP address
4. Configure your applications to use the SOCKS5 proxy at `localhost:1080`

## Development

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Backend
```bash
cd controller-app
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## License

MIT License - feel free to use this project for your own purposes.