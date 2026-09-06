import cv2
from picamera2 import Picamera2
from time import sleep
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

# --- Camera setup ---
picam = Picamera2()
picam.configure(picam.create_video_configuration(main={"size": (640, 480)}))
picam.start()
sleep(2)

# Built-in face detector
cascade = "haarcascade_frontalface_default.xml"
face_detector = cv2.CascadeClassifier(cascade)

latest_jpeg = None          # most recent annotated frame, as JPEG bytes
lock = threading.Lock()

def detection_loop():
    global latest_jpeg
    while True:
        frame = picam.capture_array()
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_detector.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))
        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 3)
        cv2.putText(frame, f"Faces: {len(faces)}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        ok, buf = cv2.imencode(".jpg", frame)
        if ok:
            with lock:
                latest_jpeg = buf.tobytes()

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Stream the frames as a simple MJPEG feed
        self.send_response(200)
        self.send_header("Content-Type",
                         "multipart/x-mixed-replace; boundary=frame")
        self.end_headers()
        while True:
            with lock:
                jpg = latest_jpeg
            if jpg:
                self.wfile.write(b"--frame\r\n")
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(jpg)))
                self.end_headers()
                self.wfile.write(jpg)
                self.wfile.write(b"\r\n")
            sleep(0.1)

    def log_message(self, *args):
        pass  # keep the terminal quiet

threading.Thread(target=detection_loop, daemon=True).start()
print("Live view: open http://turretpi.local:8000 in your laptop browser")
print("Press Ctrl+C here to stop.\n")
try:
    HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
except KeyboardInterrupt:
    print("\nStopping.")
finally:
    picam.stop()
