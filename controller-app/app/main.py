import asyncio
import logging
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from .warp_controller import WarpController

# Configuration
SOCKS5_PORT = 1080

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="WARP Single Client")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Controller Instance
warp_controller = WarpController(instance_id=1, name="Primary", socks5_port=SOCKS5_PORT)

# Serve Frontend
# We assume the frontend build is copied to /app/static in the Docker image
if os.path.exists("/app/static"):
    app.mount("/assets", StaticFiles(directory="/app/static/assets"), name="assets")
    # You might need to mount other root files like favicon.ico specifically if they exist
    # For SPA, we usually serve index.html for unknown routes, but let's handle the specific static dirs first

    @app.get("/")
    async def read_index():
        return FileResponse('/app/static/index.html')

    # Catch-all for SPA routing (if any deep links are used)
    # WARNING: This might conflict with API routes if not careful. 
    # API routes are defined below So FastAPI matches them first.
    # But we need to put this at the END or ensure specific path matching.
    # Actually, Starlette routing matches in order. So we should put this LAST.
else:
    logger.warning("Static files directory /app/static not found. Frontend will not be served.")

@app.get("/api/status")
async def get_status():
    return warp_controller.get_status()

@app.post("/api/connect")
async def connect():
    success = warp_controller.connect()
    if not success:
        raise HTTPException(status_code=500, detail="Failed to connect WARP")
    return warp_controller.get_status()

@app.post("/api/disconnect")
async def disconnect():
    success = warp_controller.disconnect()
    if not success:
        raise HTTPException(status_code=500, detail="Failed to disconnect WARP")
    return warp_controller.get_status()

@app.post("/api/rotate")
async def rotate_ip():
    # To rotate IP, we usually disconnect and reconnect, or force re-registration
    # For now, let's try a disconnect/connect cycle
    warp_controller.disconnect()
    await asyncio.sleep(1) # Wait a bit
    success = warp_controller.connect()
    
    # Check if we have a new IP? (Ideally we check this, but for now just return status)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to rotate (reconnect failed)")
    
    return warp_controller.get_status()


# WebSocket for real-time updates
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass # Handle broken pipes

manager = ConnectionManager()

@app.websocket("/ws/status")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send initial status
        await websocket.send_json({"type": "status", "data": warp_controller.get_status()})
        
        # Poll and push status updates every few seconds? 
        # Or just rely on client polling/actions?
        # Let's add a background poller for this socket session or global
        while True:
            # Wait for messages (keepalive) or just sleep and push
            # Simple keepalive:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=2.0)
            except asyncio.TimeoutError:
                # Timeout is fine, just push status
                pass
                
            status = warp_controller.get_status()
            await websocket.send_json({"type": "status", "data": status})
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
