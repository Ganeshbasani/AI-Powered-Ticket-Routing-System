"""Reachable, browser-friendly development server entry point."""

from __future__ import annotations

import os
import socket
import threading
import webbrowser

from flask import Flask

from src.config.settings import settings


def find_local_port(host: str, preferred_port: int, attempts: int = 100) -> int:
    """Return the first bindable port at or above the configured local port."""
    for port in range(preferred_port, min(65535, preferred_port + attempts) + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            try:
                listener.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No free local port found starting at {preferred_port}.")


def run_local_app(app: Flask) -> None:
    """Run Flask on a free local port and open the browser in development."""
    host = settings.flask_host
    preferred = settings.flask_port
    port = preferred
    if settings.environment == "development":
        port = find_local_port(host, preferred)
        if port != preferred:
            print(f"Port {preferred} is busy; using {port} instead.", flush=True)

    browser_host = "localhost" if host in {"0.0.0.0", "::", "127.0.0.1"} else host
    url = f"http://{browser_host}:{port}/"
    if settings.environment == "development" and os.environ.get("OPEN_BROWSER", "true").lower() not in {"0", "false", "no", "off"}:
        print(f"Opening Ticket Routing Intelligence at {url}", flush=True)
        threading.Timer(0.8, webbrowser.open, args=(url,)).start()
    else:
        print(f"Ticket Routing Intelligence is available at {url}", flush=True)

    app.run(host=host, port=port, debug=settings.flask_debug, use_reloader=False)
