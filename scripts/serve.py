#!/usr/bin/env python3
"""本地预览：带 no-store 的静态服务，避免改完刷新还是旧文件。"""
import http.server, socketserver, sys, os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8931
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class H(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"   # HTTP/1.0 会在浏览器复用连接时 RST，表现为随机破图

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


with Server(("127.0.0.1", PORT), H) as httpd:
    print("serving %s on http://127.0.0.1:%d/" % (ROOT, PORT), flush=True)
    httpd.serve_forever()
