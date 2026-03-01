import json
import logging
import os
import sqlite3
import threading
from typing import Any

logger = logging.getLogger(__name__)

class ConfigManager:
    _instance = None

    _DEFAULTS = {
        "initialized": False,
        "socks5_port": 1080,
        "panel_port": 8000,
        "panel_password": "",
        "panel_ssl_enabled": True,
        "panel_ssl_cert_file": "",
        "panel_ssl_key_file": "",
        "panel_ssl_auto_self_signed": True,
        "panel_ssl_domain": "localhost",
    }

    def __init__(self):
        data_dir = os.getenv("WARP_DATA_DIR", "/app/data")
        os.makedirs(data_dir, exist_ok=True)
        self._db_path = os.path.join(data_dir, "config.db")
        self._legacy_config_path = os.path.join(data_dir, "config.json")
        self._lock = threading.RLock()
        self._init_db()
        self._migrate_legacy_json_if_needed()
        self._seed_defaults()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = ConfigManager()
        return cls._instance

    def _connect(self):
        return sqlite3.connect(self._db_path, check_same_thread=False)

    def _init_db(self):
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                    """
                )
                conn.commit()

    def _seed_defaults(self):
        with self._lock:
            with self._connect() as conn:
                for key, value in self._DEFAULTS.items():
                    serialized = json.dumps(value)
                    conn.execute(
                        "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                        (key, serialized),
                    )
                conn.commit()

    def _migrate_legacy_json_if_needed(self):
        if not os.path.exists(self._legacy_config_path):
            return
        try:
            with open(self._legacy_config_path, "r", encoding="utf-8") as f:
                legacy_data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Skipping legacy config migration ({self._legacy_config_path}): {e}")
            return

        allowed_keys = set(self._DEFAULTS.keys())
        with self._lock:
            with self._connect() as conn:
                for key, value in legacy_data.items():
                    if key not in allowed_keys:
                        continue
                    conn.execute(
                        "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                        (key, json.dumps(value)),
                    )
                conn.commit()
        logger.info(f"Migrated legacy configuration from {self._legacy_config_path} to SQLite")

    def load(self):
        """Compatibility no-op: settings are read on demand from SQLite."""
        return

    def save(self):
        """Compatibility no-op: settings are persisted on each set()."""
        return

    def get(self, key: str, default: Any = None):
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if not row:
            return default
        raw_value = row[0]
        try:
            return json.loads(raw_value)
        except json.JSONDecodeError:
            return raw_value

    def set(self, key: str, value: Any):
        serialized = json.dumps(value)
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO settings (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value
                    """,
                    (key, serialized),
                )
                conn.commit()

    # Convenience accessors
    @property
    def initialized(self) -> bool:
        return bool(self.get("initialized", False))

    @property
    def socks5_port(self) -> int:
        return int(self.get("socks5_port", 1080))

    @property
    def panel_port(self) -> int:
        return int(self.get("panel_port", 8000))

    @property
    def panel_password(self) -> str:
        return str(self.get("panel_password", ""))
