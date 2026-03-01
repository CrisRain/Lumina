import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _resolve_force_domain() -> str:
    # New explicit knob for redirect host rewrite.
    forced = os.getenv("PANEL_HTTP_REDIRECT_FORCE_DOMAIN")
    if forced is not None:
        return forced.strip()

    # Backward compatibility: treat PANEL_SSL_DOMAIN as a redirect override only
    # when it is an actual remote hostname, not localhost placeholders.
    legacy = os.getenv("PANEL_SSL_DOMAIN", "").strip()
    if legacy.lower() in {"", "localhost", "127.0.0.1", "::1"}:
        return ""
    return legacy


class RedirectHandler(BaseHTTPRequestHandler):
    https_port = 8000
    force_domain = ""
    status_code = 308

    def _build_target(self) -> str:
        host_header = self.headers.get("Host", "").strip()
        host = host_header.split(":", 1)[0] if host_header else ""
        if self.force_domain:
            host = self.force_domain
        if not host:
            host = "localhost"

        if self.https_port == 443:
            netloc = host
        else:
            netloc = f"{host}:{self.https_port}"

        path = self.path if self.path else "/"
        return f"https://{netloc}{path}"

    def _redirect(self):
        target = self._build_target()
        self.send_response(self.status_code)
        self.send_header("Location", target)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        self._redirect()

    def do_POST(self):
        self._redirect()

    def do_PUT(self):
        self._redirect()

    def do_PATCH(self):
        self._redirect()

    def do_DELETE(self):
        self._redirect()

    def do_HEAD(self):
        self._redirect()

    def do_OPTIONS(self):
        self._redirect()

    def log_message(self, format, *args):
        # Keep redirect service logs quiet by default.
        return


def serve_http_redirect():
    enabled = _env_bool("PANEL_HTTP_REDIRECT_ENABLED", True)
    if not enabled:
        logger.info("HTTP redirect service disabled")
        return

    port = _env_int("PANEL_HTTP_REDIRECT_PORT", 80)
    https_port = _env_int("PANEL_PORT", 8000)
    status_code = _env_int("PANEL_HTTP_REDIRECT_STATUS", 308)
    if status_code not in {301, 302, 307, 308}:
        status_code = 308

    RedirectHandler.https_port = https_port
    RedirectHandler.force_domain = _resolve_force_domain()
    RedirectHandler.status_code = status_code

    server = ThreadingHTTPServer(("0.0.0.0", port), RedirectHandler)
    logger.info(f"HTTP redirect service listening on 0.0.0.0:{port}, target HTTPS port: {https_port}")
    server.serve_forever()


if __name__ == "__main__":
    serve_http_redirect()
