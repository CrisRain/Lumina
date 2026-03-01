import logging
import os
import socket
import threading
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

_HTTP_METHOD_PREFIXES = (
    b"GET ",
    b"POST ",
    b"PUT ",
    b"PATCH ",
    b"DELETE ",
    b"HEAD ",
    b"OPTIONS ",
    b"TRACE ",
    b"CONNECT ",
)


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
    forced = os.getenv("PANEL_HTTP_REDIRECT_FORCE_DOMAIN")
    if forced is not None:
        return forced.strip()

    legacy = os.getenv("PANEL_SSL_DOMAIN", "").strip()
    if legacy.lower() in {"", "localhost", "127.0.0.1", "::1"}:
        return ""
    return legacy


def _looks_like_tls(prefix: bytes) -> bool:
    # TLS record header starts with: 0x16 0x03 0x00-0x04
    return len(prefix) >= 3 and prefix[0] == 0x16 and prefix[1] == 0x03 and prefix[2] <= 0x04


def _looks_like_http(prefix: bytes) -> bool:
    upper = prefix.upper()
    return any(upper.startswith(method) for method in _HTTP_METHOD_PREFIXES)


def _read_http_prelude(conn: socket.socket, initial: bytes, max_bytes: int = 8192) -> bytes:
    data = bytearray(initial)
    while b"\r\n\r\n" not in data and len(data) < max_bytes:
        try:
            chunk = conn.recv(min(4096, max_bytes - len(data)))
        except OSError:
            break
        if not chunk:
            break
        data.extend(chunk)
    return bytes(data)


def _parse_http_host_and_path(raw_request: bytes) -> tuple[str, str]:
    text = raw_request.decode("iso-8859-1", errors="replace")
    lines = text.split("\r\n")
    host = ""
    path = "/"

    if lines:
        parts = lines[0].split()
        if len(parts) >= 2:
            target = parts[1].strip() or "/"
            parsed = urlsplit(target)
            if parsed.scheme and parsed.netloc:
                host = parsed.netloc
                path = parsed.path or "/"
                if parsed.query:
                    path += f"?{parsed.query}"
            else:
                path = target

    for line in lines[1:]:
        if not line:
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.strip().lower() == "host":
            host = value.strip()
            break

    if not path.startswith("/"):
        path = f"/{path}"

    return host, path


def _build_redirect_target(host_header: str, path: str, force_domain: str, https_port: int) -> str:
    host = host_header.split(":", 1)[0] if host_header else ""
    if force_domain:
        host = force_domain
    if not host:
        host = "localhost"

    if https_port == 443:
        netloc = host
    else:
        netloc = f"{host}:{https_port}"

    return f"https://{netloc}{path or '/'}"


def _send_redirect(conn: socket.socket, target: str, status_code: int):
    response = (
        f"HTTP/1.1 {status_code} Permanent Redirect\r\n"
        f"Location: {target}\r\n"
        "Content-Length: 0\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("utf-8")
    try:
        conn.sendall(response)
    except OSError:
        pass


def _pipe(src: socket.socket, dst: socket.socket, stop: threading.Event):
    try:
        while not stop.is_set():
            chunk = src.recv(65536)
            if not chunk:
                break
            dst.sendall(chunk)
    except OSError:
        pass
    finally:
        stop.set()
        try:
            src.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            dst.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass


def _proxy_tls(client: socket.socket, initial: bytes, target_port: int):
    try:
        upstream = socket.create_connection(("127.0.0.1", target_port), timeout=5.0)
    except OSError as exc:
        logger.warning(f"Failed to connect TLS upstream 127.0.0.1:{target_port}: {exc}")
        return

    with upstream:
        try:
            upstream.sendall(initial)
        except OSError:
            return

        stop = threading.Event()
        t1 = threading.Thread(target=_pipe, args=(client, upstream, stop), daemon=True)
        t2 = threading.Thread(target=_pipe, args=(upstream, client, stop), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()


def _handle_client(client: socket.socket, target_port: int, redirect_status: int, force_domain: str, https_port: int):
    with client:
        try:
            initial = client.recv(32)
        except OSError:
            return

        if not initial:
            return

        if _looks_like_tls(initial):
            _proxy_tls(client, initial, target_port)
            return

        if _looks_like_http(initial):
            raw = _read_http_prelude(client, initial)
            host, path = _parse_http_host_and_path(raw)
        else:
            host, path = "", "/"

        target = _build_redirect_target(host, path, force_domain, https_port)
        _send_redirect(client, target, redirect_status)


def serve_http_tls_multiplexer():
    enabled = _env_bool("PANEL_HTTP_HTTPS_MUX_ENABLED", True)
    if not enabled:
        logger.info("HTTP/TLS same-port multiplexer disabled")
        return

    listen_host = os.getenv("PANEL_LISTEN_HOST", "0.0.0.0")
    listen_port = _env_int("PANEL_PORT", 8000)
    target_port = _env_int("PANEL_HTTPS_INTERNAL_PORT", 8443)
    status_code = _env_int("PANEL_HTTP_REDIRECT_STATUS", 308)
    if status_code not in {301, 302, 307, 308}:
        status_code = 308
    force_domain = _resolve_force_domain()

    if listen_port == target_port:
        logger.warning(
            "HTTP/TLS same-port multiplexer requires PANEL_HTTPS_INTERNAL_PORT to be different from PANEL_PORT"
        )
        return

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((listen_host, listen_port))
        server.listen(256)
        logger.info(
            f"HTTP/TLS multiplexer listening on {listen_host}:{listen_port}, "
            f"TLS upstream 127.0.0.1:{target_port}"
        )

        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                continue

            threading.Thread(
                target=_handle_client,
                args=(conn, target_port, status_code, force_domain, listen_port),
                daemon=True,
            ).start()


if __name__ == "__main__":
    serve_http_tls_multiplexer()
