"""HTTP adapter: static GUI + JSON API over the application services.

Every state-changing request must carry the per-launch token (X-Frame-Token)
and, when the browser sends one, a same-origin Origin header. Machine-level
actions (quit, choosing library folders) are limited to this computer.
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import socket
import threading
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from . import __version__
from .core import fonts
from .core.media import MediaError
from .core import settings as S
from .services import App, ServiceError

STATIC = Path(__file__).resolve().parents[2] / "static"
MAX_JSON = 2 * 1024 * 1024
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("font/otf", ".otf")


def lan_addresses(port: int) -> list[str]:
    ips = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # no packet is sent; picks the LAN interface
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return [f"http://{ip}:{port}" for ip in sorted(ips) if not ip.startswith("127.")]


class Server(ThreadingHTTPServer):
    daemon_threads = True
    # Rebind right after a restart (TIME_WAIT) so the address stays :8787. Unsafe on Windows, where it
    # would let two servers share a port.
    allow_reuse_address = os.name != "nt"
    request_queue_size = 64

    def __init__(self, addr, app: App, token: str, lan: bool):
        super().__init__(addr, Handler)
        self.app = app
        self.token = token
        self.lan = lan


class Handler(BaseHTTPRequestHandler):
    server: Server
    protocol_version = "HTTP/1.1"
    server_version = "GoosnavFrame"

    # ------------------------------------------------------------ plumbing
    def log_message(self, fmt, *args):  # quiet access log; errors still reach stderr
        pass

    def _local(self) -> bool:
        return self.client_address[0] in ("127.0.0.1", "::1", "::ffff:127.0.0.1")

    def _send(self, status: int, body: bytes, ctype: str, headers: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, status: int = 200):
        self._send(status, json.dumps(obj).encode(), "application/json")

    def _error(self, status: int, code: str, message: str):
        self._json({"error": {"code": code, "message": message}}, status)

    def _body_json(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_JSON:
            raise ServiceError(413, "TOO_BIG", "Request too large")
        raw = self.rfile.read(n) if n else b"{}"
        try:
            data = json.loads(raw or b"{}")
        except ValueError as exc:
            raise ServiceError(400, "BAD_JSON", "Malformed request") from exc
        if not isinstance(data, dict):
            raise ServiceError(400, "BAD_JSON", "Malformed request")
        return data

    def _check_write(self):
        if self.headers.get("X-Frame-Token") != self.server.token:
            raise ServiceError(403, "TOKEN", "Reload the page and try again")
        origin = self.headers.get("Origin")
        if origin and urlsplit(origin).netloc != self.headers.get("Host", ""):
            raise ServiceError(403, "ORIGIN", "Cross-site request refused")

    def _file(self, path: Path, ctype: str | None = None, download: str | None = None, cache: bool = False):
        size = path.stat().st_size
        ctype = ctype or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        start, end = 0, size - 1
        rng = self.headers.get("Range")
        status = 200
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)$", rng.strip())
            if m and (m.group(1) or m.group(2)):
                if m.group(1):
                    start = int(m.group(1))
                    end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
                else:
                    start = max(0, size - int(m.group(2)))
                if start > end or start >= size:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                status = 206
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Cache-Control", "max-age=3600" if cache else "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if download:
            safe = re.sub(r'[^A-Za-z0-9_.-]', "_", download)
            self.send_header("Content-Disposition", f'attachment; filename="{safe}"')
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(path, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(1 << 18, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                left -= len(chunk)

    def _dispatch(self):
        url = urlsplit(self.path)
        path = unquote(url.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            self.route(self.command, path, q)
        except ServiceError as e:
            self._error(e.status, e.code, e.message)
        except MediaError as e:
            self._error(415, "MEDIA", str(e))
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            traceback.print_exc()
            self._error(500, "INTERNAL", f"Something went wrong: {exc.__class__.__name__}")

    do_GET = do_HEAD = do_POST = do_PUT = do_DELETE = _dispatch

    # ------------------------------------------------------------ routes
    def route(self, method: str, path: str, q: dict):
        app = self.server.app
        if method in ("POST", "PUT", "DELETE"):
            self._check_write()

        if method in ("GET", "HEAD"):
            if path == "/":
                html = (STATIC / "index.html").read_text(encoding="utf-8")
                html = html.replace("{{TOKEN}}", self.server.token).replace("{{VERSION}}", __version__)
                return self._send(200, html.encode(), "text/html; charset=utf-8",
                                  {"Content-Security-Policy": "default-src 'self'; img-src 'self' blob: data:; "
                                   "media-src 'self' blob:; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"})
            if path == "/health/ready":
                return self._json({"ok": True, "version": __version__})
            if path.startswith("/static/"):
                rel = Path(path[len("/static/"):])
                target = (STATIC / rel).resolve()
                if STATIC.resolve() not in target.parents or not target.is_file():
                    raise ServiceError(404, "NOT_FOUND", "Not found")
                return self._file(target, cache=False)
            if path == "/api/state":
                port = self.server.server_address[1]
                return self._json({
                    "version": __version__, "defaults": S.defaults(), "presets_builtin": list(S.CANVAS_PRESETS),
                    "fonts": fonts.listing(), "presets": app.presets(), "exports": app.list_exports(),
                    "local": self._local(), "lan": lan_addresses(port) if self.server.lan else [],
                    "library_roots": app.config["library_roots"] if self._local() else None,
                })
            if path == "/api/media":
                return self._json({"items": app.list_media(refresh=q.get("refresh") == "1")})
            m = re.match(r"^/api/media/([\w-]+)/thumb$", path)
            if m:
                return self._file(app.thumb(m.group(1)), "image/jpeg", cache=True)
            m = re.match(r"^/api/jobs/(\w+)$", path)
            if m:
                return self._json(app.job(m.group(1)).public())
            if path == "/api/exports":
                return self._json({"items": app.list_exports()})
            m = re.match(r"^/api/(exports|previews)/([^/]+)$", path)
            if m:
                p = app.export_path(m.group(2), preview=m.group(1) == "previews")
                return self._file(p, download=None if q.get("inline") else p.name)
            raise ServiceError(404, "NOT_FOUND", "Not found")

        if method == "PUT" and path == "/api/upload":
            n = int(self.headers.get("Content-Length") or 0)
            item = app.save_upload(q.get("name", "upload"), self.rfile, n)
            return self._json(item)
        if method == "PUT" and path == "/api/fonts":
            n = int(self.headers.get("Content-Length") or 0)
            return self._json({"font": app.save_font(q.get("name", "font.ttf"), self.rfile, n), "fonts": fonts.listing()})

        if method == "POST":
            body = self._body_json()
            if path == "/api/preview":
                png = app.preview_png(body.get("settings") or {}, body.get("media_id"), float(body.get("t") or 0))
                return self._send(200, png, "image/png")
            if path == "/api/plan":
                return self._json(app.plan(body.get("settings") or {}, body.get("media_id")))
            if path == "/api/export":
                job = app.start_export(body.get("settings") or {}, body.get("media_id"), bool(body.get("quick")))
                return self._json(job.public())
            m = re.match(r"^/api/jobs/(\w+)/cancel$", path)
            if m:
                app.job(m.group(1)).cancel.set()
                return self._json({"ok": True})
            if path == "/api/presets":
                app.save_preset(body.get("name", ""), body.get("settings") or {})
                return self._json({"presets": app.presets()})
            if path == "/api/library":
                if not self._local():
                    raise ServiceError(403, "LOCAL_ONLY", "Library folders can only be changed on the host computer")
                roots = body.get("roots") or []
                return self._json({"roots": app.set_roots([str(r) for r in roots if isinstance(r, str)])})
            if path == "/api/quit":
                if not self._local():
                    raise ServiceError(403, "LOCAL_ONLY", "Quit from the host computer")
                self._json({"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
        if method == "DELETE":
            m = re.match(r"^/api/media/([\w-]+)$", path)
            if m:
                app.delete_upload(m.group(1))
                return self._json({"ok": True})
            m = re.match(r"^/api/exports/([^/]+)$", path)
            if m:
                app.delete_export(m.group(1))
                return self._json({"ok": True})
            m = re.match(r"^/api/presets/(.+)$", path)
            if m:
                app.delete_preset(m.group(1))
                return self._json({"presets": app.presets()})
        raise ServiceError(404, "NOT_FOUND", "Not found")
