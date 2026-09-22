#!/usr/bin/env python3
"""
room_cam.py — remote room camera with smooth (velocity) pan/tilt control.

Hold an arrow button and the camera sweeps in that direction; release
and it stops. Reuses your existing turret hardware. Serves one web page
you can open from anywhere on your Tailscale network.

Run on the Pi, from inside ~/pi-turret/src:
    cd ~/pi-turret/src
    python3 room_cam.py

Then, on any device signed into YOUR Tailscale account, open:
    http://turretpi:8080

Manual control only — does NOT run the tracking loop. Ctrl+C stops
cleanly and re-centres.
"""

# ---- Standard library ----
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---- Camera + your existing hardware layer ----
import cv2
from picamera2 import Picamera2

from hardware import Turret
import config


# ---- Settings ----
PORT = 8080
JPEG_QUALITY = 70

SWEEP_SPEED = 40.0        # degrees per second while a button is held
MOTION_HZ = 20.0          # how many times per second the motion loop runs
HEARTBEAT_TIMEOUT = 0.3   # seconds: if no "keep going" arrives, auto-stop for safety


# ---- Shared hardware ----
camera = Picamera2()
turret = Turret()


# ---- Shared motion state (read/written by two threads, so we guard it) ----
# pan_dir / tilt_dir are -1, 0, or +1. 0 means "not moving on that axis".
motion = {"pan_dir": 0, "tilt_dir": 0, "last_command": 0.0}
motion_lock = threading.Lock()   # prevents the two threads clobbering each other
running = True                   # flips to False on shutdown to end the loop


def setup_camera():
    """Configure and start the camera once."""
    cfg = camera.create_video_configuration(
        main={"size": (config.WIDTH, config.HEIGHT), "format": "RGB888"},
        buffer_count=2,
    )
    camera.configure(cfg)
    camera.start()
    time.sleep(1)


def center():
    """Return both axes to their resting position and stop any motion."""
    with motion_lock:
        motion["pan_dir"] = 0
        motion["tilt_dir"] = 0
    turret.set_pan(0)
    turret.set_tilt(config.TILT_LEVEL)


def motion_loop():
    """
    Background thread: the ONLY thing that moves the servos here.

    Runs ~MOTION_HZ times per second. Each tick, it looks at the current
    direction for each axis and nudges the servo by a small step sized so
    that continuous holding produces SWEEP_SPEED degrees/second.

    Safety: if no command has arrived within HEARTBEAT_TIMEOUT seconds,
    it forces both directions to 0 — so a dropped "stop" message over the
    network can't leave the camera sweeping forever.
    """
    tick = 1.0 / MOTION_HZ
    step = SWEEP_SPEED / MOTION_HZ    # degrees to move per tick

    while running:
        with motion_lock:
            pan_dir = motion["pan_dir"]
            tilt_dir = motion["tilt_dir"]
            age = time.time() - motion["last_command"]

        # Safety auto-stop: haven't heard from the browser recently -> halt.
        if age > HEARTBEAT_TIMEOUT:
            pan_dir = 0
            tilt_dir = 0
            with motion_lock:
                motion["pan_dir"] = 0
                motion["tilt_dir"] = 0

        # Move each axis that has an active direction. set_pan/set_tilt
        # already clamp to safe limits, so hitting an end just stops.
        if pan_dir != 0:
            turret.set_pan(turret.pan_angle + pan_dir * step)
        if tilt_dir != 0:
            turret.set_tilt(turret.tilt_angle + tilt_dir * step)

        time.sleep(tick)


def make_frame_jpeg():
    """Grab one camera frame and return it as JPEG bytes."""
    frame = camera.capture_array()
    ok, buffer = cv2.imencode(".jpg", frame,
                              [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    return buffer.tobytes()


PAGE_HTML = """
<!doctype html>
<html>
<head>
  <title>Room Cam</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { background:#111; color:#eee; font-family:sans-serif; text-align:center;
           user-select:none; -webkit-user-select:none; }
    img  { width:90%; max-width:640px; border:2px solid #444; border-radius:8px; }
    button { font-size:22px; margin:6px; padding:16px 24px; border-radius:8px;
             border:none; background:#333; color:#eee; touch-action:none; }
    button:active { background:#666; }
    .row { margin:8px; }
  </style>
</head>
<body>
  <h2>Room Cam</h2>
  <img src="/stream">
  <div class="row"><button id="up">Up</button></div>
  <div class="row">
    <button id="left">Left</button>
    <button onclick="center()">Center</button>
    <button id="right">Right</button>
  </div>
  <div class="row"><button id="down">Down</button></div>
  <script>
    // Tell the Pi to start moving in a direction, and keep telling it
    // (a heartbeat) so its safety timeout doesn't halt us mid-hold.
    let held = null;
    let beat = null;

    function startMove(dir) {
      held = dir;
      fetch('/start?dir=' + dir);
      clearInterval(beat);
      beat = setInterval(function() {
        if (held) fetch('/start?dir=' + held);   // heartbeat every 150ms
      }, 150);
    }
    function stopMove() {
      held = null;
      clearInterval(beat);
      fetch('/stop');
    }
    function center() { fetch('/center'); }

    // Wire each arrow to press-and-hold, for both mouse and touch.
    function wire(id, dir) {
      const b = document.getElementById(id);
      b.addEventListener('mousedown',  function(e){ e.preventDefault(); startMove(dir); });
      b.addEventListener('mouseup',    stopMove);
      b.addEventListener('mouseleave', stopMove);
      b.addEventListener('touchstart', function(e){ e.preventDefault(); startMove(dir); });
      b.addEventListener('touchend',   function(e){ e.preventDefault(); stopMove(); });
    }
    wire('up', 'tilt_up'); wire('down', 'tilt_down');
    wire('left', 'pan_left'); wire('right', 'pan_right');
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        # 1) Main page
        if self.path == "/" or self.path.startswith("/index"):
            body = PAGE_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        # 2) Live MJPEG stream
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
                    time.sleep(0.03)
            except (BrokenPipeError, ConnectionResetError):
                pass

        # 3) Start moving in a direction (also serves as the heartbeat)
        elif self.path.startswith("/start"):
            action = self.path.split("dir=")[-1]
            with motion_lock:
                if action == "pan_left":    motion["pan_dir"] = +1
                elif action == "pan_right": motion["pan_dir"] = -1
                elif action == "tilt_up":   motion["tilt_dir"] = -1
                elif action == "tilt_down": motion["tilt_dir"] = +1
                motion["last_command"] = time.time()
            self.send_response(200); self.end_headers()

        # 4) Stop all motion
        elif self.path.startswith("/stop"):
            with motion_lock:
                motion["pan_dir"] = 0
                motion["tilt_dir"] = 0
            self.send_response(200); self.end_headers()

        # 5) Recentre
        elif self.path.startswith("/center"):
            center()
            self.send_response(200); self.end_headers()

        else:
            self.send_response(404); self.end_headers()

    def log_message(self, *args):
        pass


def main():
    global running

    setup_camera()
    center()

    # Start the background motion thread. daemon=True means it won't block
    # the program from exiting when we shut down.
    mover = threading.Thread(target=motion_loop, daemon=True)
    mover.start()

    server = ThreadingHTTPServer(("", PORT), Handler)

    print("=" * 52)
    print(" Room Cam (velocity control) running.")
    print(" Open on any device on your Tailscale account:")
    print("   http://turretpi:%d" % PORT)
    print(" Hold an arrow to sweep; release to stop. Ctrl+C to quit.")
    print("=" * 52)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        running = False               # tell the motion loop to end
        time.sleep(0.1)               # let it finish its current tick
        turret.stop()                 # laser off, PWM stopped
        camera.stop()
        print("Stopped cleanly.")


if __name__ == "__main__":
    main()