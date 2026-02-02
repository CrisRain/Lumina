import asyncio
import logging
from collections import deque
from datetime import datetime
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from .warp_controller import WarpController

# Configuration
SOCKS5_PORT = 1080

# Logging setup with custom handler
class LogCollector(logging.Handler):
    def __init__(self, maxlen=100):
        super().__init__()
        self.logs = deque(maxlen=maxlen)
        self.formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        self._loop = None
    
    def set_loop(self, loop):
        """设置事件循环引用"""
        self._loop = loop
    
    def emit(self, record):
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).strftime('%H:%M:%S'),
            'level': record.levelname,
            'logger': record.name,
            'message': self.format(record)
        }
        self.logs.append(log_entry)
        
        # Broadcast to all websocket clients (线程安全)
        try:
            if self._loop and self._loop.is_running():
                # 从其他线程安全地调度到事件循环
                self._loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(broadcast_log(log_entry))
                )
        except Exception:
            pass  # 忽略广播失败

log_collector = LogCollector(maxlen=200)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add collector to root logger
root_logger = logging.getLogger()
root_logger.addHandler(log_collector)

# Broadcast log helper - manager will be defined later
async def broadcast_log(log_entry):
    """Broadcast log entry to all connected websocket clients"""
    try:
        # manager is defined later, so we use globals() to access it
        if 'manager' in globals():
            await globals()['manager'].broadcast({'type': 'log', 'data': log_entry})
    except:
        pass

app = FastAPI(title="WARP Single Client")

# 启动事件：设置事件循环引用
@app.on_event("startup")
async def startup_event():
    """应用启动时设置事件循环"""
    loop = asyncio.get_running_loop()
    log_collector.set_loop(loop)
    logger.info("Event loop configured for log broadcasting")

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
    """
    轮换 IP 地址（简单模式：断开重连）
    
    Returns:
        轮换结果
    """
    # 简单模式：断开重连
    warp_controller.disconnect()
    await asyncio.sleep(1)
    success = warp_controller.connect()
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to rotate (reconnect failed)")
    
    return warp_controller.get_status()



@app.get("/api/logs")
async def get_logs(limit: int = 100):
    """
    获取最近的日志记录
    
    Args:
        limit: 返回的日志数量限制（默认100）
    """
    logs = list(log_collector.logs)
    return {
        "total": len(logs),
        "logs": logs[-limit:]
    }


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

