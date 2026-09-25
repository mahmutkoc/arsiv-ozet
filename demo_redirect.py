"""İsimli paylaşım bağlantısını çalışan şifreli demoya yönlendirir."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
from urllib.parse import urlparse


def main():
    target = sys.argv[1]
    parsed = urlparse(target)
    if (parsed.scheme != "https" or not (parsed.hostname or "").endswith(".trycloudflare.com")
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise SystemExit("Hedef, HTTPS Cloudflare demo adresi olmalı.")

    class Redirect(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", target)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_HEAD = do_GET

        def log_message(self, *args):
            pass

    ThreadingHTTPServer(("127.0.0.1", 8504), Redirect).serve_forever()


if __name__ == "__main__":
    main()
