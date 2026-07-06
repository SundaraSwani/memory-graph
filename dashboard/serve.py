#!/usr/bin/env python3
"""Memory Observatory — local HTTP server (stdlib only)."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scan import scan_all  # noqa: E402

_CACHE: dict = {"data": None, "error": None, "updated": 0.0}
_CACHE_LOCK = threading.Lock()
_STOP = threading.Event()


def _refresh_loop(interval: float) -> None:
    while not _STOP.is_set():
        try:
            payload = scan_all()
            with _CACHE_LOCK:
                _CACHE["data"] = payload
                _CACHE["error"] = None
                _CACHE["updated"] = time.time()
        except Exception as exc:  # noqa: BLE001
            with _CACHE_LOCK:
                _CACHE["error"] = str(exc)
        _STOP.wait(interval)


def cached_state() -> dict:
    with _CACHE_LOCK:
        if _CACHE["data"] is not None:
            return _CACHE["data"]
        if _CACHE["error"]:
            return {"error": _CACHE["error"]}
    return scan_all()


class ObservatoryHandler(BaseHTTPRequestHandler):
    server_version = "MemoryObservatory/1.0"

    def log_message(self, fmt: str, *args) -> None:
        if os.environ.get("OBSERVATORY_QUIET") == "1":
            return
        super().log_message(fmt, *args)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        if not path.is_file():
            self.send_error(404, "Not found")
            return
        data = path.read_bytes()
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/api/state", "/api/state/"):
            try:
                payload = cached_state()
                status = 500 if payload.get("error") else 200
                self._send_json(payload, status=status)
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": str(exc)}, status=500)
            return

        if path in ("/", "/index.html"):
            self._send_file(STATIC / "index.html")
            return

        if path.startswith("/static/"):
            rel = path.removeprefix("/static/")
            target = (STATIC / rel).resolve()
            if not str(target).startswith(str(STATIC.resolve())):
                self.send_error(403, "Forbidden")
                return
            self._send_file(target)
            return

        self.send_error(404, "Not found")


def main() -> None:
    parser = argparse.ArgumentParser(description="Memory Observatory local dashboard")
    parser.add_argument("--host", default=os.environ.get("OBSERVATORY_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("OBSERVATORY_PORT", "8765")))
    parser.add_argument("--poll", type=float, default=float(os.environ.get("OBSERVATORY_POLL", "2")))
    args = parser.parse_args()

    interval = max(1.0, args.poll)
    refresher = threading.Thread(target=_refresh_loop, args=(interval,), daemon=True)
    refresher.start()

    server = HTTPServer((args.host, args.port), ObservatoryHandler)
    url = f"http://{args.host}:{args.port}/"
    print(f"Memory Observatory → {url}", flush=True)
    print(f"Refresh every {interval}s · Ctrl+C to stop", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
    finally:
        _STOP.set()
        refresher.join(timeout=1)
        server.server_close()


if __name__ == "__main__":
    main()
