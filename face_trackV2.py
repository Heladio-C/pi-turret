"""
Pan tilt turret tracking:

Open loop face tracking with Raspberry Pi 5 HARDWARE PWM version.

Camera module 3 finds face, converts offset from the center frame into pan/tilt angles, making servos 
to follow. Live view is at http://turretpi.local:8000

Servos are driven by RP1's hardware PWM 


WIRING (Changed):

    Tilt servo signal has moved from pin 11(GPIO 17) to pin 35 (GPIO 19)
    Pan servo signal has remained unchanged pin 12
    Servos still powered from battery pack, common ground with Pi. 

Setup
dtoverlay=pwm-2chan in /boot/firmware/config.txt activates GPIO18 and GPIO19

sudo pip3 install rpi-harware-pwm --break-system-packages

run: python face_track.py 

To stop: Ctrl + C 
    
"""

import os 
import time
import threading
import cv2
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from picamera2 import Picamera2
#this is the new improvement instead of using gpiozero 
from rpi_hardware_pwm import HardwarePWM

#setup camera resolution
WIDTH = 640
HEIGHT = 360
HORIZONTAL_FOV = 66.0
VERTICAL_FOV = 38.0

#this determines how small adjustments will servos make to lock on target
#increase to get more mini movements
PAN_GAIN = 0.2
TILT_GAIN = 0.3

#This is the max speed limit servos can get with swift movement
PAN_MAX_STEP = 6.0
TILT_MAX_STEP = 7.0

DEADZONE = 20  #area of center where tracking is void


ANGLE_LIMIT = 90.0   #MAX limits of panning left and right

#TILT LIMITS
TILT_LEVEL = 130.0 #resting position
TILT_MIN = 30
TILT_MAX = 180.0

PAN_DIRECTION = -1
TILT_DIRECTION = 1
PORT = 8000

SMOOTHING = 0.5 #higher is snappier, lower is smoother/laggier

#guidelines on screen
SHOW_ZONES = True
DETECT_MARGIN = 10

#THIS IS THE BIGGEST CHANGE
#HARDWARE PWM 
PWM_CHIP = 0
SERVO_HZ = 50
PAN_SERVO_MIN, PAN_SERVO_MAX = -90.0, 90.0 #RANGE OF PANNING
TILT_SERVO_MIN, TILT_SERVO_MAX = 0.0, 180.0 #RANGE OF TILTING


 #this will limit hardware from being damaged by not going over limits   
def clamp(value, low, high):
    return max(low, min(value, high))




def angle_to_duty(angle, low, high):
    fraction = clamp((angle - low) / (high - low), 0.0, 1.0)
    return 2.5 + fraction * 10.0



#looks for the pre-trained XML file with thousands examples of faces that will help detect faces

def find_cascade():
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


#Channel 3 is GPIO 19(Panning) and channel2 is GPIO18 (tilting)
pan_pwm = HardwarePWM(pwm_channel=3, hz=SERVO_HZ, chip=PWM_CHIP)
tilt_pwm = HardwarePWM(pwm_channel=2, hz = SERVO_HZ, chip = PWM_CHIP)

pan_pwm.start(angle_to_duty(0.0, PAN_SERVO_MIN, PAN_SERVO_MAX))
tilt_pwm.start(angle_to_duty(TILT_LEVEL, TILT_SERVO_MIN, TILT_SERVO_MAX))



#activate camera
cam = Picamera2()
cam.configure(cam.create_video_coinfguration(main={"size": (WIDTH, HEIGHT), "format": "RGB888"}))
cam.start()
time.sleep(1)
face_cascade = cv2.CascadeClassifier(find_cascade())


class StreamingOutput:
    def __init__(self):
        self.frame = None
        self.condition = threading.Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()


output = StreamingOutput()


PAGE = (b"<html><head><title>Turret - face tracking </title></head>"
        b"<body style='margin:0;background:#111'>"
        b"<img src='strean.mjpg' style='display:block;width:100vw;height:100vh;object-fit:cointain'/>"
        b"</body></html>")


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
        pass


def serve():
    ThreadingHTTPServer(("", PORT), StreamingHandler).serve_forever()


threading.Thread(target=serve, daemon=True).start()
print(f"Streaming server on http://turretpi.local:{PORT}")


pan_angle = 0.0
tilt_angle = TILT_LEVEL
target_pan = 0.0
target_tilt = TILT_LEVEL

cx = WIDTH / 2
cy = HEIGHT / 2

last_time = time.time()
fps = 0.0

try:
    while True:
        frame = cam.capture_array()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(60, 60))

        if len(faces) > 0:
            x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
            face_cx, face_cy = x + fw / 2, y + fh / 2

            dx = face_cx - cx
            dy = face_cy - cy

            if abs(dx) > DEADZONE or abs(dy) > DEADZONE:
                pan_error = (dx / WIDTH) * HORIZONTAL_FOV
                tilt_error = (dy / HEIGHT) * VERTICAL_FOV

                pan_step = clamp(PAN_GAIN * pan_error, -PAN_MAX_STEP, PAN_MAX_STEP)
                tilt_step = clamp(TILT_GAIN * tilt_error, -TILT_MAX_STEP, TILT_MAX_STEP)

                target_pan = clamp(target_pan + PAN_DIRECTION * pan_step, -ANGLE_LIMIT, ANGLE_LIMIT)
                target_tilt = clamp(target_tilt + TILT_DIRECTION * tilt_step, TILT_MIN, TILT_MAX)


                #go toward target gently, then command servos to hold their position
                pan_angle += (target_pan - pan_angle) * SMOOTHING
                tilt_angle += (target_tilt - tilt_angle) * SMOOTHING
                pan_pwm.change_duty_cycle(angle_to_duty(pan_angle, PAN_SERVO_MIN, PAN_SERVO_MAX))
                tilt_pwm.change_duty_cyle(angle_to_duty(tilt_angle, TILT_SERVO_MIN, TILT_SERVO_MAX))

            cv2.rectangle(frame, (x, y), (x + fw, y + fh), (0, 255, 0), 2)
            cv2.line(frame, (int(cx), int(cy)), (int(face_cx), int(face_cy)), (0, 255, 255), 1)

        #Overlays to guide 
        if SHOW_ZONES:
            cv2.rectangle(frame, (DETECT_MARGIN, DETECT_MARGIN), 
                          (WIDTH - DETECT_MARGIN, HEIGHT - DETECT_MARGIN), (0, 165, 255), 1)
            cv2.putText(frame, "detection area", (DETECT_MARGIN + 500, DETECT_MARGIN + 16), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 1)
            cv2.rectangle(frame, (int(cx-DEADZONE), int(cy-DEADZONE)), 
                          (int(cx + DEADZONE), int(cy + DEADZONE)), (255, 255, 0), 1)
            cv2.putText(frame, "target zone", (int(cx-DEADZONE), int(cy-DEADZONE) - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)


        cv2.drawMarker(frame, (int(cx), int(cy)), (255, 255, 255), cv2.MARKER_CROSS, 18, 1)
        status = "Tracking" if len(faces) > 0 else "Searching...."
        now = time.time()
        fps = 0.9 * fps + 0.1 * (1.0 / max(now - last_time, 1e-3))
        last_time = now
        cv2.putText(frame, f"{status}     {fps:4.1f}  FPS", (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            output.write(jpg.tobytes())

except KeyboardInterrupt:
    print("Ended by input")
finally:
    pan_pwm.change_duty_cycle(angle_to_duty(0.0, PAN_SERVO_MIN, PAN_SERVO_MAX))
    tilt_pwm.change_duty_cycle(angle_to_duty(TILT_LEVEL, TILT_SERVO_MIN, TILT_SERVO_MAX))
    time.sleep(0.5)
    pan_pwm.stop()
    tilt_pwm.stop()
    cam.stop()
    




