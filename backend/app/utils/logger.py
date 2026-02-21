import logging
import asyncio
from collections import deque
from datetime import datetime

# Filter for noisy connection logs
class ConnectionFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        return "connection open" not in msg and "connection closed" not in msg

class LogCollector(logging.Handler):
    def __init__(self, maxlen=300):
        super().__init__()
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
        self.logs.append(log_entry)

# Global instance
log_collector = LogCollector(maxlen=500)

def setup_logging():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # Add collector to root logger
    root_logger = logging.getLogger()
    if log_collector not in root_logger.handlers:
        root_logger.addHandler(log_collector)

    # Apply filter to ALL handlers (console + collector)
    conn_filter = ConnectionFilter()
    for handler in root_logger.handlers:
        handler.addFilter(conn_filter)
        
    # Also suppress uvicorn access logs if needed
    logging.getLogger("uvicorn.access").addFilter(conn_filter)
    logging.getLogger("uvicorn.error").addFilter(conn_filter)
