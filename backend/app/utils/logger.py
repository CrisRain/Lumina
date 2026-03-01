import logging
from collections import deque
from datetime import datetime
from threading import Lock

# Filter for noisy connection logs
class ConnectionFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage().lower()
        noisy_patterns = (
            "connection open",
            "connection closed",
            '"websocket /ws/status"',
        )
        return not any(pattern in msg for pattern in noisy_patterns)

class LogCollector(logging.Handler):
    def __init__(self, maxlen=300):
        super().__init__()
        self._lock = Lock()
        self._next_id = 1
        self.logs = deque(maxlen=maxlen)
        self.formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
    
    def set_loop(self, loop):
        """No-op for compatibility"""
        pass
    
    def emit(self, record):
        # Get the raw message
        msg = record.getMessage()
        
        # Append exception info if available
        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatter.formatException(record.exc_info)
            if record.exc_text:
                msg = f"{msg}\n{record.exc_text}"

        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).strftime('%H:%M:%S'),
            'level': record.levelname,
            'logger': record.name,
            'message': msg
        }
        with self._lock:
            log_entry['id'] = self._next_id
            self._next_id += 1
            self.logs.append(log_entry)

    @property
    def latest_id(self) -> int:
        with self._lock:
            if not self.logs:
                return 0
            return self.logs[-1]["id"]

    def get_recent(self, limit: int = 100):
        safe_limit = max(1, min(int(limit), 1000))
        with self._lock:
            return list(self.logs)[-safe_limit:]

    def get_since(self, since_id: int, limit: int = 500):
        safe_limit = max(1, min(int(limit), 1000))
        with self._lock:
            items = [entry for entry in self.logs if entry["id"] > since_id]
            return items[:safe_limit]

# Global instance
log_collector = LogCollector(maxlen=500)

def setup_logging():
    logging.basicConfig(level=logging.INFO, force=True)

    # Add collector to root logger
    root_logger = logging.getLogger()
    if log_collector not in root_logger.handlers:
        root_logger.addHandler(log_collector)

    # Apply filter to ALL handlers (console + collector)
    conn_filter = ConnectionFilter()
    for handler in root_logger.handlers:
        handler.addFilter(conn_filter)

    # Suppress noisy frameworks/libraries to improve signal quality
    logging.getLogger("uvicorn.access").addFilter(conn_filter)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
