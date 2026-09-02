"""
MJPEG stream to the browser at http://turretpi.local:8000
Import `output` and push JPEG bytes to it; call start_server() once to serve.
"""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn


class StreamingOutput:
    "Thread-safe buffer holding the most recent JPEG frame."
    def __init__(self):
        self.frame = None
        self.condition = threading.Condition()

    def update(self, jpeg_bytes):
        with self.condition:
            self.frame = jpeg_bytes
            self.condition.notify_all()


# the orchestrator pushes frames here; the handler reads from here
output = StreamingOutput()

PAGE = (b"<html><head><title>Turret - tracking </title></head>"
        b"<body style='margin:0;background:#111'>"
        b"<img src='stream.mjpg' style='display:block;width:100vw;height:100vh;object-fit:contain'/>"
        b"</body></html>")


class StreamingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            body = PAGE
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/stream.mjpg":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FRAME")
            self.end_headers()
            try:
                while True:
                    with output.condition:
                        output.condition.wait()
                        frame = output.frame
                    if frame is None:
                        continue
                    self.wfile.write(b"--FRAME\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(("Content-Length: %d\r\n\r\n" % len(frame)).encode())
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self.send_error(404)

    def log_message(self, *args):
        pass


class StreamingServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def start_server(port=8000):
    """Start the MJPEG server in a background thread; return it so main can shut it down."""
    server = StreamingServer(("", port), StreamingHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server