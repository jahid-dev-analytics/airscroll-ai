"""Serves a mock Instagram page that loads the real extension/content.js.

    python tests/ext_harness/serve.py         then open http://127.0.0.1:8799/reels/

It mimics the page structure the content script relies on (a scroll-snap reels
container, <video> elements, svg[aria-label="Like"] buttons, feed <article>s).
It verifies our logic, NOT Instagram's current markup.
"""
import http.server
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
ROUTES = {
    "/": HERE / "feed.html",
    "/reels/": HERE / "reels.html",
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
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8799
    print(f"Mock Instagram on http://127.0.0.1:{port}/reels/ and http://127.0.0.1:{port}/")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
