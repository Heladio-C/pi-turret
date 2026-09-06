#!/usr/bin/env python3
"""
Pan-Tilt Laser Turret: Phase 4 PID controller for face tracking

New changes:
Involve a PID controller: constantly calculating how much effort is needed to get a desired output
In this case we will get an angle as output

Proportional: 
Acts as a spring force, 

Integral: 
This is small nudges to get to the derised location, it continously adds up over time the small error
that is left, and make the camera snap to absolute zero.

Derivative:
This is essentially the braking system by applying a negative force, it counters the springs momentum

Using 2 PID controllers that use a measured elapsed time dt, in each frame so motion is steady
"""

import time
import threading

import cv2

from picamera2 import Picamera2
from rpi_hardware_pwm import HardwarePWM
from http.server import BaseHTTPRequestHandler, HTTPServer
#allows to stream serve multiple connections w/o neither jamming the server
from socketserver import ThreadingMixIn

WIDTH = 640
HEIGHT = 360
HORIZONTAL_FOV = 66.0
VERTICAL_FOV = 38.0

DEADZONE = 20 #20 pixel radius where tracking is void

DETECT_MARGIN = 10 # for visuals for on screen detection area guide box

#servo limits 
ANGLE_LIMIT = 90.0 #left and right
TILT_MIN = 30 # looking up
TILT_MAX = 180.0 #looking down
TILT_LEVEL = 130.0 #resting position

PAN_DIRECTION = -1
TILT_DIRECTION = 1


#HARDWARE PWM (RP1 controller = chip 0 on this Pi)
PWM_CHIP = 0
SERVO_HZ = 50
PAN_CHANNEL = 3  # GPIO 19
TILT_CHANNEL = 2  #GPIO 18



#servo speed limits
PAN_MAX_STEP = 6
TILT_MAX_STEP = 6

#----PID gains THESE ARE TUNABLE---
#raise KP first, then add D, add small amount of I if slightly off center
#for panning
#force applied
PAN_KP = 0.35
#small adjustments
PAN_KI = 0.0
#braking system
PAN_KD = 0.02

#for tilting
TILT_KP = 0.35
TILT_KI = 0.0
TILT_KD = 0.02

#------------------------

def clamp(value, low, high):
    return max(low, min(high, value))


#converts a wanted angle into a PWM percentage
#standard servos expect a pulse width of 0.5ms (0 deg) to 2.5ms (180 deg) every 20ms.
def angle_to_duty(angle_limits):
    angle_limits = clamp(angle_limits, 0.0, 180.0)
    return 2.5 + (angle_limits / 180.0) * 10.0


# NEW PID CONTROLLER
class PID:
    def __init__(self, kp, ki, kd, output_limit):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.output_limit = output_limit
        self.integral = 0.0
        self.previous_error = 0.0
        self.first = True
        self.last_p = self.last_i = self.last_d = 0.0

    def reset(self):
        self.integral = 0.0
        self.previous_error = 0.0
        self.first = True
        self.last_p = self.last_i = self.last_d = 0.0


    #error is distance in pixels is face from center
    #dt is time elapsed
    def update(self, error, dt):

        #Proportional
        P = self.kp * error

        if self.first or dt <= 0:
            # No previous samples so skip I and D this frame
            derivative = 0.0
            self.first = False
        else:
            #integral: add leftover error over time 
            self.integral += error * dt
            if self.ki > 0:
                windup_limit = self.output_limit / self.ki
                self.integral = clamp(self.integral, -windup_limit, windup_limit)

            derivative = (error - self.previous_error) / dt

        I = self.ki * self.integral
        D = self.kd * derivative

        self.previous_error = error
        self.last_p = P
        self.last_i = I
        self.last_d = D

        return clamp(P + I + D, -self.output_limit, self.output_limit)


#WEB STREAMING SETUP (OPTIONAL)
class StreamingOutput:
    "THREAD safe buffer that holds the most recent jpg frame"
    def __init__(self):
        self.frame = None
        self.condition = threading.Condition() #locks the frame so it's not read while being written

    def update(self, jpeg_bytes):
        with self.condition:
            self.frame = jpeg_bytes
            self.condition.notify_all()


output = StreamingOutput()

# the html webpage that has an image tag to see our video
PAGE = (b"<html><head><title>Turret - face tracking </title></head>"
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
            self.send_header("Content-Type","multipart/x-mixed-replace; boundary=FRAME")
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




#-----------------
#MAIN
#------------------

def main():

    #start cam
    cam = Picamera2()
    cam.configure(cam.create_video_configuration(main={"size": (WIDTH, HEIGHT), "format": "RGB888"}))
    cam.start()
    time.sleep(1)


    #detect faces
    #looks for the pre-trained XML file with thousands examples of faces that will help detect faces
    face_cascade = cv2.CascadeClassifier("haarcascade_frontalface_default.xml")

    #servos on hardware PWM
    #Channel 3 is GPIO 19(Panning) and channel2 is GPIO18 (tilting)
    pan_pwm = HardwarePWM(pwm_channel=PAN_CHANNEL, hz=SERVO_HZ, chip=PWM_CHIP)
    tilt_pwm = HardwarePWM(pwm_channel=TILT_CHANNEL, hz = SERVO_HZ, chip = PWM_CHIP)
    pan_angle = 0.0
    tilt_angle = TILT_LEVEL
    pan_pwm.start(angle_to_duty(pan_angle + 90))
    tilt_pwm.start(angle_to_duty(tilt_angle))


    #----PID controllers
    pan_PID = PID(PAN_KP, PAN_KI, PAN_KD, PAN_MAX_STEP)
    tilt_PID = PID(TILT_KP, TILT_KI, TILT_KD, TILT_MAX_STEP)


    #---web server thread----
    server = StreamingServer(("", 8000), StreamingHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print("Streaming at http://turretpi.local:8000  (Ctrl+C to stop)")


    #find center of screen
    cx = WIDTH // 2
    cy = HEIGHT // 2
    previous_time = None
    fps = 0.0


    try:
        while True:
            #stopwatch
            now = time.monotonic()
            if previous_time is None:
                dt = 0.0
            else:
                dt = now - previous_time
            previous_time = now

            if dt > 0:
                fps = 0.9 * fps + 0.1 * (1.0 / dt)

            # detections 
            frame = cam.capture_array()
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            #gray = grayscale image frame, reduces CPU usage on Pi
            #scaleFactor = resizes image by 10% on each pass, lower scales like 1.05 increase accurracy
            #slows frame rate
            #minNeighbors = controls how strict the detector is against false positives 
            #this setting requires at least 5 overlapping candidate boxes before declaring a region an actual face.
            #minSize() = defines the min face size in pixels to search for, anything smaller is ignored
            faces = face_cascade.detectMultiScale(gray, scaleFactor = 1.1, minNeighbors=5, minSize=(40,40))

            status = "Searching..."
            if len(faces) > 0:
                status = "Tracking..."
                x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                #find the center pixel of the face
                face_cx, face_cy = x + w // 2, y + h // 2
                
                #find how many pixels the face is from the center of the screen
                dx = face_cx - cx
                dy = face_cy - cy


                #PAN axis
                if abs(dx) <= DEADZONE:
                    pan_PID.reset()

                else:
                    error_pan_degree = (dx / WIDTH) * HORIZONTAL_FOV
                    pan_angle += PAN_DIRECTION * pan_PID.update(error_pan_degree, dt)
                    pan_angle = clamp(pan_angle, -ANGLE_LIMIT, ANGLE_LIMIT)

                #TILT AXIS
                if abs(dy) <= DEADZONE:
                    tilt_PID.reset()
                else:
                    error_tilt_degree = (dy / HEIGHT) * VERTICAL_FOV
                    tilt_angle += TILT_DIRECTION * tilt_PID.update(error_tilt_degree, dt)
                    tilt_angle = clamp(tilt_angle, TILT_MIN, TILT_MAX)


                #command the servos
                pan_pwm.change_duty_cycle(angle_to_duty(pan_angle + 90))
                tilt_pwm.change_duty_cycle(angle_to_duty(tilt_angle))

                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            else:
               # face lost hold position, clear PID history
                pan_PID.reset()
                tilt_PID.reset() 

            # --- overlays ---
            # orange detection-area guide box
            cv2.rectangle(frame, (DETECT_MARGIN, DETECT_MARGIN),
                          (WIDTH - DETECT_MARGIN, HEIGHT - DETECT_MARGIN),
                          (0, 165, 255), 1)
            # cyan deadzone box at center
            cv2.rectangle(frame, (cx - DEADZONE, cy - DEADZONE),
                          (cx + DEADZONE, cy + DEADZONE), (255, 255, 0), 1)
            # center crosshair
            cv2.drawMarker(frame, (cx, cy), (0, 255, 255),
                           cv2.MARKER_CROSS, 12, 1)
 
            cv2.putText(frame, "%s  %.0f FPS" % (status, fps), (8, 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.putText(frame, "pan %.1f  tilt %.1f" % (pan_angle, tilt_angle),
                        (8, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
            # PID term readout (very useful while tuning)
            cv2.putText(frame, "PAN  P%+.2f I%+.2f D%+.2f" %
                        (pan_PID.last_p, pan_PID.last_i, pan_PID.last_d),
                        (8, HEIGHT - 28), cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                        (0, 255, 0), 1)
            cv2.putText(frame, "TILT P%+.2f I%+.2f D%+.2f" %
                        (tilt_PID.last_p, tilt_PID.last_i, tilt_PID.last_d),
                        (8, HEIGHT - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                        (0, 255, 0), 1)
 
            # --- push frame to the browser ---
            ok, jpeg = cv2.imencode(".jpg", frame)
            if ok:
                output.update(jpeg.tobytes())

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        pan_pwm.stop()
        tilt_pwm.stop()
        cam.stop()
        server.shutdown()



if __name__ == '__main__':
    main()