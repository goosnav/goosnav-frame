"""Entry point: bind, publish runtime state, serve the GUI.

Run by the launcher (via app/launcher/bootstrap.py) or by the top-level
"Start Goosnav Frame" scripts, which pass these options through:

    --open          open a browser on this computer once running
    --no-browser    never open a browser (headless servers)
    --port N        preferred port (default 8787)
    --local         only this computer, not the network

By owner decision the server listens on every interface (LAN) so phones and
other computers on the network can use it. Set GOOSNAV_FRAME_HOST=127.0.0.1
to keep it on this computer only.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import signal
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path

from .server import Server, lan_addresses
from .services import App

DATA_NAME = "GoosnavFrame"
DEFAULT_PORT = 8787


def _app_data() -> Path:
    if os.environ.get("GOOSNAV_APP_DATA"):
        return Path(os.environ["GOOSNAV_APP_DATA"])
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / DATA_NAME
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / DATA_NAME
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / DATA_NAME


def _bind(host: str, port: int, app: App, token: str, lan: bool) -> Server:
    try:
        return Server((host, port), app, token, lan)
    except OSError:
        return Server((host, 0), app, token, lan)  # preferred port taken: let the OS choose atomically


def _write_state(port: int) -> None:
    target = os.environ.get("GOOSNAV_RUNTIME_STATE")
    if not target:
        return
    tmp = Path(target + ".tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps({"schema_version": 1, "pid": os.getpid(), "url": f"http://127.0.0.1:{port}"}),
                   encoding="utf-8")
    os.replace(tmp, target)


def _can_open_browser() -> bool:
    # On Linux without a desktop session, webbrowser would start a text browser in the terminal.
    if sys.platform.startswith("linux"):
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return True


def _already_running(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health/ready", timeout=1.5) as r:
            return r.status == 200 and b"version" in r.read(200)
    except OSError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="Start Goosnav Frame")
    parser.add_argument("--open", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int)
    parser.add_argument("--local", action="store_true")
    args, _ = parser.parse_known_args(sys.argv[1:] if argv is None else argv)
    want_browser = args.open and not args.no_browser and _can_open_browser()
    if args.port:
        os.environ["GOOSNAV_PORT_PREFERENCE"] = str(args.port)
    if args.local:
        os.environ["GOOSNAV_FRAME_HOST"] = "127.0.0.1"
    supervised = bool(os.environ.get("GOOSNAV_RUNTIME_STATE"))

    preferred = int(os.environ.get("GOOSNAV_PORT_PREFERENCE") or DEFAULT_PORT) or DEFAULT_PORT
    if not supervised and _already_running(preferred):
        url = f"http://127.0.0.1:{preferred}"
        print(f"Goosnav Frame is already running: {url}", flush=True)
        for lan_url in lan_addresses(preferred):
            print(f"  on your network: {lan_url}", flush=True)
        if want_browser:
            webbrowser.open(url)
        return 0

    base = _app_data()
    data = Path(os.environ.get("GOOSNAV_DATA_DIR") or base / "data")
    config = Path(os.environ.get("GOOSNAV_CONFIG_DIR") or base / "config")
    roots = [str(p) for p in [Path.home() / "Desktop" / "business" / "studio" / "output"] if p.is_dir()]
    app = App(data, config, roots)

    host = os.environ.get("GOOSNAV_FRAME_HOST", "0.0.0.0")
    try:
        port = int(os.environ.get("GOOSNAV_PORT_PREFERENCE") or DEFAULT_PORT) or DEFAULT_PORT
    except ValueError:
        port = DEFAULT_PORT
    lan = host not in ("127.0.0.1", "localhost", "::1")
    server = _bind(host, port, app, secrets.token_urlsafe(24), lan)
    bound = server.server_address[1]
    _write_state(bound)

    local = f"http://127.0.0.1:{bound}"
    print(f"Goosnav Frame is running: {local}", flush=True)
    for url in lan_addresses(bound) if lan else []:
        print(f"  on your network: {url}", flush=True)

    def stop(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, stop)
        except (ValueError, OSError):
            pass
    if not supervised:
        print("Press Ctrl+C to stop.", flush=True)
    if want_browser:
        threading.Timer(0.5, lambda: webbrowser.open(local)).start()
    try:
        server.serve_forever(poll_interval=0.3)
    finally:
        server.server_close()
        state = os.environ.get("GOOSNAV_RUNTIME_STATE")
        if state:
            Path(state).unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
