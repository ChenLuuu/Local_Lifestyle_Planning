"""Simple static + reverse proxy server for frontend.

Serves /Users/toki/Desktop/本地生活规划/frontend/dist on port 3000,
and proxies /api/* requests to backend on port 8000.
"""

import http.server
import socketserver
import urllib.request
import urllib.error
import os

FRONTEND_DIR = "/Users/toki/Desktop/本地生活规划/frontend/dist"
BACKEND_URL = "http://127.0.0.1:8000"
PORT = 3000


class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=FRONTEND_DIR, **kwargs)

    def do_GET(self):
        if self.path.startswith("/api/"):
            self._proxy()
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            self._proxy()
        else:
            self.send_error(405)

    def do_PUT(self):
        if self.path.startswith("/api/"):
            self._proxy()
        else:
            self.send_error(405)

    def do_DELETE(self):
        if self.path.startswith("/api/"):
            self._proxy()
        else:
            self.send_error(405)

    def do_OPTIONS(self):
        if self.path.startswith("/api/"):
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.end_headers()
        else:
            self.send_error(405)

    def _proxy(self):
        url = BACKEND_URL + self.path
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length else None
            req = urllib.request.Request(url, data=body, method=self.command)
            for header in ["Content-Type", "Accept"]:
                v = self.headers.get(header)
                if v:
                    req.add_header(header, v)
            with urllib.request.urlopen(req, timeout=30) as resp:
                self.send_response(resp.status)
                for key, val in resp.getheaders():
                    if key.lower() in ("transfer-encoding", "connection"):
                        continue
                    self.send_header(key, val)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(resp.read())
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(e.read() if e.fp else b'{"error": "upstream error"}')
        except Exception as e:
            self.send_response(502)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(f'{{"error": "proxy error: {e}"}}'.encode())


if __name__ == "__main__":
    os.chdir(FRONTEND_DIR)
    with socketserver.TCPServer(("", PORT), ProxyHandler) as httpd:
        print(f"Serving {FRONTEND_DIR} on port {PORT}")
        print(f"Proxying /api/* -> {BACKEND_URL}")
        httpd.serve_forever()
