"""Entry point:  python -m airscroll  [--port 8765] [--no-browser]"""
from __future__ import annotations

import argparse
import errno
import logging
import sys
import webbrowser
from logging.handlers import RotatingFileHandler

from aiohttp import web

from . import __version__
from .app import AirScrollApp
from .config import DEFAULT_PORT, LOG_DIR, Settings
from .server import create_web_app
from .tracker import ensure_model


def setup_logging(verbose: bool) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles default to cp1252
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    file = RotatingFileHandler(LOG_DIR / "airscroll.log", maxBytes=1_000_000, backupCount=2,
                               encoding="utf-8")
    file.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.addHandler(console)
    root.addHandler(file)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)


def main() -> int:
    parser = argparse.ArgumentParser(prog="airscroll", description="AirScroll AI gesture controller")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help="local port (the browser extension expects 8765)")
    parser.add_argument("--no-browser", action="store_true", help="do not open the dashboard")
    parser.add_argument("--verbose", action="store_true", help="debug logging")
    args = parser.parse_args()

    setup_logging(args.verbose)
    log = logging.getLogger("airscroll")
    log.info("AirScroll AI %s starting", __version__)

    try:
        ensure_model()
    except RuntimeError as e:
        log.error("%s", e)
        return 1

    app = AirScrollApp(Settings.load())
    webapp = create_web_app(app)
    url = f"http://127.0.0.1:{args.port}/"

    async def announce(_):
        log.info("Dashboard: %s   (Ctrl+C to quit)", url)
        if not args.no_browser:
            webbrowser.open(url)

    webapp.on_startup.append(announce)
    try:
        # 127.0.0.1 only: the dashboard and preview are never reachable from the network.
        web.run_app(webapp, host="127.0.0.1", port=args.port, print=None, shutdown_timeout=3)
    except OSError as e:
        if e.errno in (errno.EADDRINUSE, 10048):
            log.error("Port %s is already in use: AirScroll may already be running. "
                      "Open %s or close the other copy.", args.port, url)
            return 1
        raise
    finally:
        app.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
