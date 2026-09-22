#!/usr/bin/env python3
"""
room_cam.py — remote room camera with manual pan/tilt control.

Reuses your existing turret hardware (servos + laser) and serves a
single web page you can open from anywhere on your Tailscale network:
a live camera view with arrow buttons to aim it.

Run on the Pi, from inside ~/pi-turret/src (so the module imports work):
    cd ~/pi-turret/src
    python3 room_cam.py

Then, on any device signed into YOUR Tailscale account, open:
    http://turretpi:8080

This is a standalone utility — it does NOT run the tracking loop.
It is manual control only. Ctrl+C stops it and re-centres safely.
"""

# ---- Standard library ----
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---- Camera + your existing hardware layer ----
import cv2
from picamera2 import Picamera2

# We import YOUR turret class rather than rewriting servo code. This keeps
# all your tuned constants (limits, directions, PWM channels) intact.
from hardware import Turret
import config


# ---- Settings ----
PORT = 8080                 # different from the tracker's 8000, so both can coexist
STEP_DEGREES = 5            # how far each button press nudges an axis
JPEG_QUALITY = 70           # 0-100; lower = smaller/faster stream


# One shared camera and one shared turret for the whole program.
camera = Picamera2()
turret = Turret()

# Current aim, in degrees. We start centred using your config's resting values.
pan_angle = 0
tilt_angle = config.TILT_LEVEL


def setup_camera():
    """Configure and start the camera once, at program start."""
    cfg = camera.create_video_configuration(
        main={"size": (config.WIDTH, config.HEIGHT), "format": "RGB888"},
        buffer_count=2,          # low latency for a live view (your documented fix)
    )
    camera.configure(cfg)
    camera.start()
    time.sleep(1)                # let exposure / white balance settle


def move(axis, direction):
    """
    Nudge one servo axis by STEP_DEGREES.

    Arguments:
        axis (str): "pan" or "tilt"
        direction (int): +1 or -1

    Returns nothing; it just moves the servo and remembers the new angle.
    """
    global pan_angle, tilt_angle

    if axis == "pan":
        # Clamp keeps us inside the safe travel range from your config.
        pan_angle = max(-config.ANGLE_LIMIT,
                        min(config.ANGLE_LIMIT, pan_angle + direction * STEP_DEGREES))
        turret.set_pan(pan_angle)
    else:
        tilt_angle = max(config.TILT_MIN,
                         min(config.TILT_MAX, tilt_angle + direction * STEP_DEGREES))
        turret.set_tilt(tilt_angle)


def make_frame_jpeg():
    """
    Grab one camera frame and encode it as JPEG bytes for the browser.

    Returns:
        bytes: a single JPEG image.
    """
    frame = camera.capture_array()               # RGB888 -> already OpenCV-friendly
    ok, buffer = cv2.imencode(".jpg", frame,
                              [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    return buffer.tobytes()


# The web page: a live image plus five buttons. Kept intentionally simple.
PAGE_HTML = """
<!doctype html>
<html>
<head>
  <title>Room Cam</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { background:#111; color:#eee; font-family:sans-serif; text-align:center; }
    img  { width:90%; max-width:640px; border:2px solid #444; border-radius:8px; }
    button { font-size:22px; margin:6px; padding:14px 20px; border-radius:8px;
             border:none; background:#333; color:#eee; }
    button:active { background:#666; }
    .row { margin:8px; }
  </style>
</head>
<body>
  <h2>Room Cam</h2>
  <img src="/stream">
  <div class="row"><button onclick="cmd('tilt_up')">? Up</button></div>
  <div class="row">
    <button onclick="cmd('pan_left')">? Left</button>
    <button onclick="cmd('center')">Center</button>
    <button onclick="cmd('pan_right')">Right ?</button>
  </div>
  <div class="row"><button onclick="cmd('tilt_down')">? Down</button></div>
  <script>
    // Send a movement command to the Pi, then do nothing else.
    function cmd(action) { fetch('/move?dir=' + action); }
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    """Handles the three kinds of request the browser makes."""

    def do_GET(self):
        # 1) The main page.
        if self.path == "/" or self.path.startswith("/index"):
            body = PAGE_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        # 2) The live video stream (MJPEG: a never-ending series of JPEGs).
        elif self.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type",
                             "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            try:
                while True:
                    jpeg = make_frame_jpeg()
                    self.wfile.write(b"--frame\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(("Content-Length: %d\r\n\r\n" % len(jpeg)).encode())
                    self.wfile.write(jpeg)
                    self.wfile.write(b"\r\n")
                    time.sleep(0.03)             # ~30 fps ceiling
            except (BrokenPipeError, ConnectionResetError):
                pass                            # browser tab closed; fine

        # 3) A movement command, e.g. /move?dir=pan_left
        elif self.path.startswith("/move"):
            action = self.path.split("dir=")[-1]
            if action == "pan_left":    move("pan", +1)
            elif action == "pan_right": move("pan", -1)
            elif action == "tilt_up":   move("tilt", -1)
            elif action == "tilt_down": move("tilt", +1)
            elif action == "center":
                move_to_center()
            self.send_response(200)
            self.end_headers()

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass                                    # silence per-request console spam


def move_to_center():
    """Return both axes to their resting position."""
    global pan_angle, tilt_angle
    pan_angle = 0
    tilt_angle = config.TILT_LEVEL
    turret.set_pan(pan_angle)
    turret.set_tilt(tilt_angle)


def main():
    setup_camera()
    move_to_center()                            # start aimed at a known position

    # Bind to "" (all interfaces) so Tailscale can reach it. Access is still
    # limited to your tailnet — this is NOT open to the public internet.
    server = ThreadingHTTPServer(("", PORT), Handler)

    print("=" * 52)
    print(" Room Cam running.")
    print(" Open on any device on your Tailscale account:")
    print("   http://turretpi:%d" % PORT)
    print(" Press Ctrl+C here to stop.")
    print("=" * 52)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        turret.stop()                           # your safe path: laser off, servos released
        camera.stop()
        print("Stopped cleanly.")


if __name__ == "__main__":
    main()
