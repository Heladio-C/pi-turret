"""
"Open-loop = correction in each frame, with no smoothing yet. Exception some hunting / overshoot / or jittering may occur. 

HARDWARE: Raspberry Pi 5, Raspberry Pi Camera Module v2.1, 8GB RAM, 64-bit OS

RUN: python3 face_track.py
Then open http://turretpi.local:8000 in a browser to view the camera feed. The camera will track faces in real-time.
Stop with Ctrl+C




"""

#io is used to convert the image to a byte stream so we can send it over HTTP
import io 
import os
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
from picamera2 import Picamera2
from gpiozero import AngularServo


#control configurations
#tunable 

WIDTH = 640
HEIGHT = 480
HORIZONTAL_FOV = 66.0
VERTICAL_FOV = 41.0
GAIN = 0.10
MAX_STEP = 2.5 # Stops sudden movements of the servo, which can cause overshoot and hunting. This is the maximum angle change per frame.
DEADZONE = 25 # if face is within this many pixels of the center, don't move the servo. This prevents jittering when the face is near the center.
ANGLE_LIMIT = 80.0 #deg: never allow the servo to go beyond this angle, to prevent hitting the physical limits of the servo and causing damage.
RELAX_AFTER = 25 # frames with nothing to do , before we detach the servo and let it relax. This prevents the servo from overheating and wearing out prematurely.
PAN_DIR = -1 # 1 = normal, -1 = reverse. Change this if your servo is moving in the wrong direction.
TILT_DIR = -1 # 1 = normal, -1 = reverse. Change this if your servo is moving in the wrong direction.
PORT = 8000

SMOOTHING = 0.2

SHOW_ZONES = True
DETECT_MARGIN = 40


#functions that control the servos
#this functions clamps a value between two limits
def clamp(value, low, high):
    return max(low, min(value, high))

#this function will find the path to the Haar cascade file
def find_cascade():
    # Start by checking the current directory
    candidates = ["haarcascade_frontalface_default.xml"]
    
    haarcascades = getattr(getattr(cv2, "data", None), "haarcascades", None)
    if haarcascades:
        candidates.append(haarcascades + "haarcascade_frontalface_default.xml")
        
    candidates += [
        "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml",
        "/usr/share/opencv/haarcascades/haarcascade_frontalface_default.xml"
    ]

    for path in candidates:
        if path and os.path.exists(path):
            return path
            
    raise FileNotFoundError("Could not find .xml file.")



#servos 
# 17 and 18 are the GPIO pins on the Raspberry Pi that the servos are connected to. Change these if you are using different pins.
pan_servo = AngularServo(17, min_angle=-90, max_angle=90, min_pulse_width=0.0005, max_pulse_width=0.0025)
tilt_servo = AngularServo(18, min_angle=-90, max_angle=90, min_pulse_width=0.0005, max_pulse_width=0.0025)






#camera
cam = Picamera2()
cam.configure(cam.create_video_configuration(main={"size": (WIDTH, HEIGHT), "format": "RGB888"}))
cam.start()
time.sleep(1)  # Allow the camera to initialize
face_cascade = cv2.CascadeClassifier(find_cascade())  # Load the Haar cascade for face detection




#mjpeg streaming server
#will wait for the next frame to be available
class StreamingOutput:

    def __init__(self):
        self.frame = None
        self.condition = threading.Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()




output = StreamingOutput()

#this is the HTTP server that will stream the video feed to the browser
PAGE = (b"<html><head><title>Turret - face tracking</title></head>"
    b"<body style='margin:0;background:#111;text-align:center'>"
    b"<img src='stream.mjpg' style='max-width:100%;height:auto'/></body></html>")



class StreamingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(PAGE)
        
        elif self.path == "/stream.mjpg":
            self.send_response(200)
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Content-type", "multipart/x-mixed-replace; boundary=FRAME")
            self.end_headers()

            try:
                while True:
                    with output.condition:
                        output.condition.wait()
                        frame = output.frame
                    self.wfile.write(b"--FRAME\r\n")
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(frame)))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")

            except (BrokenPipeError, ConnectionResetError):
                pass

        else:
            self.send_error(404)
        
    def log_message(self, *args):
        pass  # Suppress logging to keep the output clean

def serve():
    ThreadingHTTPServer(("", PORT), StreamingHandler).serve_forever()

threading.Thread(target=serve, daemon=True).start()
print(f"Streaming server started on http://turretpi.local:8000")



#tracking loop that will process each frame from the camera and update the servo positions

pan_angle = 0.0
tilt_angle = 0.0
target_pan = 0.0
target_tilt = 0.0


pan_servo.angle = pan_angle
tilt_servo.angle = tilt_angle
attatched = True
idle_count = 0


cx = WIDTH / 2
cy = HEIGHT / 2

last_time = time.time()

fps = 0.0

try:
    while True:
        frame = cam.capture_array()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(60, 60))

        moved = False

        if len(faces) > 0:
            #track 1 target: the biggest face (closest to the camera)
            x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
            face_cx, face_cy = x + fw / 2, y + fh / 2

            dx = face_cx - cx #if dx is positive face is to the right of the center
            dy = face_cy - cy #if dy is positiveface is below the center

            if abs(dx) > DEADZONE or abs(dy) > DEADZONE:
                pan_error = (dx / WIDTH) * HORIZONTAL_FOV
                tilt_error = (dy / HEIGHT) * VERTICAL_FOV

                pan_step = clamp(GAIN * pan_error, -MAX_STEP, MAX_STEP)
                tilt_step = clamp(GAIN * tilt_error, -MAX_STEP, MAX_STEP)

                target_pan = clamp(target_pan + PAN_DIR * pan_step, -ANGLE_LIMIT, ANGLE_LIMIT)
                target_tilt = clamp(target_tilt + TILT_DIR * tilt_step, -ANGLE_LIMIT, ANGLE_LIMIT)


                pan_angle = clamp(target_pan - pan_angle) * SMOOTHING
                tilt_angle = clamp(target_tilt - tilt_angle) * SMOOTHING

                pan_servo.angle = pan_angle
                tilt_servo.angle = tilt_angle

                attatched = True
                idle_count = 0
                moved = True

            #draw a rectangle around the detected face for visualization
            cv2.rectangle(frame, (x, y), (x + fw, y + fh), (0, 255, 0), 2)
            cv2.line(frame, (int(cx), int(cy)), (int(face_cx), int(face_cy)), (0, 255, 255), 1)
   
        if not moved:
            idle_count += 1
            if idle_count > RELAX_AFTER and attatched:
                pan_servo.detach()
                tilt_servo.detach()
                attatched = False


        #crosshairs for visualization
        cv2.drawMarker(frame, (int(cx), int(cy)), (255, 255, 255), cv2.MARKER_CROSS, 18, 1)
        status = "Tracking" if len(faces) > 0 else "Searching..."
        now = time.time()
        fps = 0.9 * fps + 0.1 * (1.0 / max(now - last_time, 1e-3))
        last_time = now
        cv2.putText(frame, f"{status}   {fps:4.1f}  FPS", (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])

        if ok:
            output.write(jpg.tobytes())


except KeyboardInterrupt:
    print("Interrupted by user")
finally:
    #recenter servos
    if not attatched:
        pan_servo.angle = 0.0
        tilt_servo.angle = 0.0
        time.sleep(0.5)
    else:
        pan_servo.angle = 0.0
        tilt_servo.angle = 0.0
        time.sleep(0.5)
    pan_servo.detach()
    tilt_servo.detach()
    cam.stop()
