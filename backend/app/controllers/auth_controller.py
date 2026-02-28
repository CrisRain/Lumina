import hmac
import logging
import os
import secrets
import time
from collections import deque
from typing import Deque, Dict
from fastapi import HTTPException, Security, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .config_controller import ConfigManager

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

class AuthHandler:
    _instance = None
    
    def __init__(self):
        self._token_ttl_seconds = int(os.getenv("AUTH_TOKEN_TTL_SECONDS", "43200"))
        self._max_login_attempts = int(os.getenv("AUTH_MAX_LOGIN_ATTEMPTS", "10"))
        self._attempt_window_seconds = int(os.getenv("AUTH_ATTEMPT_WINDOW_SECONDS", "300"))
        self._tokens: Dict[str, float] = {}
        self._failed_attempts_by_ip: Dict[str, Deque[float]] = {}
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = AuthHandler()
        return cls._instance

    @staticmethod
    def verify_password(password: str) -> bool:
        """Verify the provided password against config."""
        config_pass = ConfigManager.get_instance().panel_password
        if not config_pass:
            return False

        return hmac.compare_digest(password, config_pass)

    def is_auth_enabled(self) -> bool:
        config = ConfigManager.get_instance()
        return config.initialized and bool(config.panel_password)

    def _cleanup_expired_tokens(self):
        now = time.time()
        expired = [token for token, exp in self._tokens.items() if exp <= now]
        for token in expired:
            self._tokens.pop(token, None)

    def _can_attempt_login(self, client_ip: str) -> bool:
        now = time.time()
        attempts = self._failed_attempts_by_ip.setdefault(client_ip, deque())
        while attempts and now - attempts[0] > self._attempt_window_seconds:
            attempts.popleft()
        return len(attempts) < self._max_login_attempts

    def _record_failed_attempt(self, client_ip: str):
        attempts = self._failed_attempts_by_ip.setdefault(client_ip, deque())
        attempts.append(time.time())

    def create_token(self) -> str:
        """Generate a session token."""
        self._cleanup_expired_tokens()
        token = secrets.token_hex(32)
        self._tokens[token] = time.time() + self._token_ttl_seconds
        return token

    def revoke_token(self, token: str):
        self._tokens.pop(token, None)

    def is_token_valid(self, token: str) -> bool:
        if not token:
            return False
        self._cleanup_expired_tokens()
        return token in self._tokens

    def authenticate(self, password: str, client_ip: str = "unknown") -> str:
        config = ConfigManager.get_instance()
        if not config.initialized:
            raise HTTPException(status_code=400, detail="Panel is not initialized yet")
        if not config.panel_password:
            raise HTTPException(status_code=400, detail="Authentication is disabled: configure panel password in setup")

        if not self._can_attempt_login(client_ip):
            raise HTTPException(status_code=429, detail="Too many login attempts. Please retry later.")

        if not self.verify_password(password):
            self._record_failed_attempt(client_ip)
            raise HTTPException(status_code=401, detail="Invalid password")

        self._failed_attempts_by_ip.pop(client_ip, None)
        return self.create_token()

    async def get_current_user(self, request: Request, creds: HTTPAuthorizationCredentials = Security(security)):
        """Dependency for protected endpoints."""
        config_mgr = ConfigManager.get_instance()
        if not config_mgr.initialized:
            raise HTTPException(status_code=503, detail="Panel is not initialized")
        config_pass = config_mgr.panel_password

        # If no password configured, authentication is disabled
        if not config_pass:
            return "admin"

        if not creds:
            raise HTTPException(status_code=401, detail="Not authenticated")

        self._cleanup_expired_tokens()
        token = creds.credentials
        expiry = self._tokens.get(token)
        if not expiry:
            raise HTTPException(status_code=401, detail="Invalid token")

        return "admin"
