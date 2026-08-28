#!/usr/bin/env python3
"""
Pan-Tilt Laser Turret: Phase 6 Multi object tracking with priority rules
weighted score + stealable lock, sweep instrumented

How the decision on who to track works?

1. ByteTrack give every person a id (model.track(persist=True))


2. Each persion gets a weighted Score in each frame:
score = W_SIZE * size + W_CENTER *centeredness + W_CONF * confidence
each person is scaled to roughly 0 to 1 so weights are comparable



3. The person currently tracked is given a bonus added to their score (stickiness) a challenger has to out score by more to be the target, for a 
specific amount of time which is STEAL_PATIENCE frames in a row, this is hystersesis:

4. If the target is out of frame, we hold for a short time then pick a new person


Sweep instrumentation (ML): 
--bouns B set the stickiness knob for this run (overrides CURRENT_TARGET_BONUS)
--patience P set the steal patience for this run
--secs S stop after S seconds (0 = run until Ctrl + C)

after 1 run it prints 1 row to csv file 

Everything else is the same



"""
import os
import time
import threading
import argparse #accepts arguments given in terminal

import cv2
from ultralytics import YOLO # new YOLOv8 detector
import numpy as np #allows for calculating box areas, 

from picamera2 import Picamera2
from rpi_hardware_pwm import HardwarePWM
from gpiozero import LED


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



#YOLO DETECTOR (Tunable)
MODEL_PATH = "yolov8n.pt" #using nano version smallest, fast version
PERSON_CLASS = 0 #COCO class id for person # other notable ones: car = 2, traffic light = 9, 
CONF = 0.5 # keeps detections only if YOLO is more than or equal to 50% sure 
YOLO_IMAGES = 256 #YOLO shrinks the frame to this size before detecting, smaller is faster, but worse for far people

#--------------New multi-object tracking + priority (Tunable)
#weighted scores: how much each factor matters when ranking people
W_SIZE = 1.0 # bigger box is more important
W_CENTER = 0.5 #closer to the middle of the frame is more imoportant
W_CONF = 0.3 #more confident than 30% is more important 

#-----stealable priority 
CURRENT_TARGET_BONUS = 0.2 #0 = flickery, high = never lets go

STEAL_PATIENCE = 3 #other target must outscore current person this man frames in a row before it becomes priority 

LOST_GRACE_FRAMES = 8 # keep the lock this many frames while the target is off screen, before switching 


#------------------------

def clamp(value, low, high):
    return max(low, min(high, value))


#converts a wanted angle into a PWM percentage
#standard servos expect a pulse width of 0.5ms (0 deg) to 2.5ms (180 deg) every 20ms.
def angle_to_duty(angle_limits):
    angle_limits = clamp(angle_limits, 0.0, 180.0)
    return 2.5 + (angle_limits / 180.0) * 10.0




#-------NEW weighted score format
# give every detected person a score, return an array of the scores aligned with the boxes, bigger = more worth following

def score_people(xyxy, confs, cx, cy, half_diagonal):
    x1, y1, x2, y2 = xyxy[:, 0], xyxy[:, 1], xyxy[:, 2], xyxy[:, 3]

    #size = box area as fraction of frame
    size_term = ((x2 - x1) * (y2 - y1)) / float(WIDTH * HEIGHT)


    #centeredness: 1.0 = dead center, 0.0 is far corner
    box_cx  = (x1 + x2) / 2.0
    box_cy = (y1 + y2) / 2.0
    #.sqrt() calculates the sqrt of every element in array
    distance = np.sqrt((box_cx - cx) ** 2 + (box_cy - cy) ** 2)
    #.clip(input array, minumum, maxminum, optional = array to store the results) 
    # used to limit the values in a array with a min and max threshold, an value smaller than min is replaced by the min, values in range are unchanged
    
    center_term = np.clip(1.0 - distance / half_diagonal, 0.0, 1.0)

    #confidence is same
    conf_term = confs

    return W_SIZE * size_term + W_CENTER * center_term + W_CONF * conf_term



















# PID CONTROLLER
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

def main(bonus, patience, run_secs):

    #start cam
    cam = Picamera2()
    cam.configure(cam.create_video_configuration(main={"size": (WIDTH, HEIGHT), "format": "RGB888"}, buffer_count=2))
    cam.start()
    time.sleep(1)


    
    #YOLO person detector, YOLO(MODEL_PATH) loads the trained network once, after it acts like a function hand it an image, get back the objects it found
    model = YOLO(MODEL_PATH)

    #warm up: the first inference is always slow , 
    warmup = cam.capture_array()
    model(warmup, imgsz=YOLO_IMAGES, verbose=False)




    #---------OLD VERSION---------------------------
    #detect faces
    #looks for the pre-trained XML file with thousands examples of faces that will help detect faces
    #face_cascade = cv2.CascadeClassifier("haarcascade_frontalface_default.xml")

    #servos on hardware PWM
    #Channel 3 is GPIO 19(Panning) and channel2 is GPIO18 (tilting)
    pan_pwm = HardwarePWM(pwm_channel=PAN_CHANNEL, hz=SERVO_HZ, chip=PWM_CHIP)
    tilt_pwm = HardwarePWM(pwm_channel=TILT_CHANNEL, hz = SERVO_HZ, chip = PWM_CHIP)
    pan_angle = 0.0
    tilt_angle = TILT_LEVEL
    pan_pwm.start(angle_to_duty(pan_angle + 90))
    tilt_pwm.start(angle_to_duty(tilt_angle))



    #----LASERS!!!!
    laser = LED(17)
    laser.off()


    #----PID controllers
    pan_PID = PID(PAN_KP, PAN_KI, PAN_KD, PAN_MAX_STEP)
    tilt_PID = PID(TILT_KP, TILT_KI, TILT_KD, TILT_MAX_STEP)


    #---web server thread----
    server = StreamingServer(("", 8000), StreamingHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print("Streaming at http://turretpi.local:8000  (Ctrl+C to stop)")
    print("Run config -> bonus=%.3f  patience=%d  secs=%.0f" % (bonus, patience, run_secs))


    #find center of screen
    cx = WIDTH // 2
    cy = HEIGHT // 2
    half_diagonal = np.sqrt(WIDTH ** 2 + HEIGHT ** 2) / 2.0 #center to corner distance
    previous_time = None
    fps = 0.0
    infer_ms = 0.0



    #-----NEW----- Lock and hysteresis state 
    locked_id = None # id we are following
    missing = 0 # frames the locked target has been off screen
    pending_id = None # a challenger currently trying to steal lock
    steal_counter = 0 #how many frames in a row it has out scored
    switch_count = 0 #how many time the locked target changed
    track_start = time.monotonic()


    try:
        while True:
            #stopwatch
            now = time.monotonic()

            #timed auto stop for hands free sweeping
            if run_secs > 0 and (now - track_start) >= run_secs:
                break


            if previous_time is None:
                dt = 0.0
            else:
                dt = now - previous_time
            previous_time = now

            if dt > 0:
                fps = 0.9 * fps + 0.1 * (1.0 / dt)

            # detections 
            frame = cam.capture_array()


            # --- YOLO: find people in this frame (replaces the Haar cascade) ---
            # frame is already BGR-ordered (the Picamera2 RGB888 quirk), which is
            # exactly what YOLO wants -- so no color conversion, no grayscale.
            #imgsz = shrink to this size before detecting
            #conf = drop detections if below this coinfidence
            #classes = 0 reports only people
            #verbose=False don't print a line to terminal every frame
            #returns LIST (one per image): so we use results[0]
            t0 = time.monotonic()
            results = model(frame, imgsz=YOLO_IMAGES, conf=CONF, classes=[PERSON_CLASS], verbose=False)
            infer_ms = (time.monotonic() - t0) * 1000.0 #detection time

            boxes = results[0].boxes # every person found in frame (empty if none)


            if len(boxes) > 0 and boxes.id is not None:
                
                xyxy = boxes.xyxy.cpu().numpy() #boxes.xyxy gives the boundaries of detected objects in a array
                
                confs = boxes.conf.cpu().numpy() #boxes.conf gets the confidence scores for each object between 0 and 1 and puts in array
                
                ids = boxes.id.cpu().numpy().astype(int)   #boxes.id gives id's to each object when using ByteTrack in YOLO
                scores = score_people(xyxy, confs, cx, cy, half_diagonal)

            else:
                
                
                xyxy = np.empty((0, 4))  #.empty(size of array or tuple () for many dimensions, dtype=type of data to store, order by column of rows  in memory )
                confs = np.empty((0,))   #creates an array without initializing the entires 
                ids = np.empty((0,), dtype=int)
                scores = np.empty((0,))

            
            #----------------------choose who to follow with weighted score and implement stealable lock on-----------------

            laser.on()
            status = "Searching..."
            target_idx = None
            locked_present = (locked_id is not None) and (locked_id in ids)


            if locked_present:
                missing = 0
                li = int(np.where(ids == locked_id)[0][0])  #.where(condition, [x, y] =return elements chosen from x when true, and y when false)
                locked_eff = scores[li] + bonus #target score with a bonus

                #find the best alternative person

                if len(ids) > 1:
                    masked = scores.copy()
                    masked[1] = -np.inf
                    ci = int(masked.argmax())
                    challenger_won = masked[ci] > locked_eff

                else:
                    ci = None
                    challenger_won = False

                if challenger_won:
                    cand_id = int(ids[ci])
                    if cand_id == pending_id:
                        steal_counter += 1
                    else:
                        pending_id = cand_id
                        steal_counter = 1

                    if steal_counter >= patience: #stealing has occurred
                        switch_count += 1
                        locked_id = cand_id
                        target_idx = ci
                        pending_id = None
                        steal_counter = 0
                        status = "Tracking id %d" % locked_id
                    else:
                        target_idx = li #hold current target for now
                        status = "Locked id %d (challenged by %d %d/%d)" % (locked_id, cand_id, steal_counter, patience)

                else:
                    pending_id = None
                    steal_counter = 0
                    target_idx = li
                    status = "Tracking id %d" % locked_id

            else:
                if locked_id is not None:
                    missing += 1

                    if (locked_id is None) or (missing >= LOST_GRACE_FRAMES):
                        if len(ids) > 0:
                            new_idx = int(scores.argmax())



            
























            if len(boxes) > 0:
                status = "Tracking..."

                #boxes.xyxy gets bounding box coords in [x1, y1, x2, y2] format:
                xyxy = boxes.xyxy.cpu().numpy()
               
                confs = boxes.conf.cpu().numpy()

                #---------------if serveral are in frame, pick biggest box----------------------
                # here it's x2 - x1 = width, and y2 - y1  = height
                #argamax() returns the largest value in the areas array
                areas =(xyxy[:, 2] - xyxy[:, 0]) * (xyxy[:, 3] - xyxy[:, 1])
                best = int(areas.argmax())
                x1, y1, x2, y2 = xyxy[best].astype(int)
                conf = float(confs[best])


                HEAD_FOCUS = 0.35 #0.0 is top of box, 0.5 is center, lower aims higher on body
                #get center of body frame
                body_cx = (x1 + x2) // 2
                body_cy = (y1 + HEAD_FOCUS * (y2 - y1))
                #body_cy = (y1 + y2) // 2
                
                #find how many pixels the body is from the center of the screen
                dx = body_cx - cx
                dy = body_cy - cy


                #PAN axis-------------------
                if abs(dx) <= DEADZONE:
                    pan_PID.reset()

                else:
                    error_pan_degree = (dx / WIDTH) * HORIZONTAL_FOV
                    pan_angle += PAN_DIRECTION * pan_PID.update(error_pan_degree, dt)
                    pan_angle = clamp(pan_angle, -ANGLE_LIMIT, ANGLE_LIMIT)

                #TILT AXIS--------------------
                if abs(dy) <= DEADZONE:
                    tilt_PID.reset()
                else:
                    error_tilt_degree = (dy / HEIGHT) * VERTICAL_FOV
                    tilt_angle += TILT_DIRECTION * tilt_PID.update(error_tilt_degree, dt)
                    tilt_angle = clamp(tilt_angle, TILT_MIN, TILT_MAX)


                #command the servos
                pan_pwm.change_duty_cycle(angle_to_duty(pan_angle + 90))
                tilt_pwm.change_duty_cycle(angle_to_duty(tilt_angle))

                #draw the tracked person: green box _ confidence level
                #2 is the thickness of the frame around person
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                #position is (x1, y1 - 6) 
                cv2.putText(frame, "person %.2f" % conf, (x1, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

            else:
               # body lost hold position, clear PID history
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
            cv2.putText(frame, "pan %.1f  tilt %.1f" % (pan_angle, tilt_angle),(8, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

            cv2.putText(frame, "infer %.0f ms" % infer_ms, (8, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)


            
            # PID term readout (very useful while tuning)
            cv2.putText(frame, "PAN  P%+.2f I%+.2f D%+.2f" % (pan_PID.last_p, pan_PID.last_i, pan_PID.last_d), (8, HEIGHT - 28), cv2.FONT_HERSHEY_SIMPLEX, 0.4,(0, 255, 0), 1)
            cv2.putText(frame, "TILT P%+.2f I%+.2f D%+.2f" % (tilt_PID.last_p, tilt_PID.last_i, tilt_PID.last_d), (8, HEIGHT - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
 
            # --- push frame to the browser ---
            ok, jpeg = cv2.imencode(".jpg", frame)
            if ok:
                output.update(jpeg.tobytes())

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        laser.off()
        pan_pwm.stop()
        tilt_pwm.stop()
        cam.stop()
        server.shutdown()


if __name__ == '__main__':
    main()