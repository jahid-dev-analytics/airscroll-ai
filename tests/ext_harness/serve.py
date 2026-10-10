"""Serves mock social pages that load the real extension/content.js.

    python tests/ext_harness/serve.py
    http://127.0.0.1:8799/reels/                 Instagram-style reels
    http://127.0.0.1:8799/                       Instagram-style feed
    http://127.0.0.1:8799/shorts/?site=youtube   YouTube-style Shorts (nav buttons, aria-pressed like)
    http://127.0.0.1:8799/feed/?site=linkedin    LinkedIn-style feed (React Like buttons)

They mimic the page structure the content script relies on. They verify our
logic, NOT the real sites' current markup.
"""
import http.server
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
ROUTES = {
    "/": HERE / "feed.html",
    "/reels/": HERE / "reels.html",
    "/shorts/": HERE / "shorts.html",
    "/feed/": HERE / "linkedin.html",
    "/shim.js": HERE / "shim.js",
    "/content.js": ROOT / "extension" / "content.js",
}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path = ROUTES.get(self.path.split("?")[0])
        if not path:
            self.send_error(404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html" if path.suffix == ".html" else "text/javascript")
        self.send_header("Cache-Control", "no-store")
        # lets a live site's page fetch content.js for a manual check (test server only, localhost)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8799
    print(f"Mock pages on http://127.0.0.1:{port}/  (see the docstring for the list)")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
