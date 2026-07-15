"""
"Open-loop = correction in each frame, with no smoothing yet. Exception some hunting / overshoot / or jittering may occur. 

HARDWARE: Raspberry Pi 4B, Raspberry Pi Camera Module v2.1, 8GB RAM, 64-bit OS

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

WIDTH = 640
HEIGHT = 480

HORIZONTAL_FOV = 66.0
VERTICAL_FOV = 41.0

GAIN = 0.20

MAX_STEP = 6.0 # Stops sudden movements of the servo, which can cause overshoot and hunting. This is the maximum angle change per frame.
DEADZONE = 35 # if face is within this many pixels of the center, don't move the servo. This prevents jittering when the face is near the center.

ANGLE_LIMIT = 80.0 #deg: never allow the servo to go beyond this angle, to prevent hitting the physical limits of the servo and causing damage.
RELAX_AFTER = 25 # frames with nothing to do , before we detach the servo and let it relax. This prevents the servo from overheating and wearing out prematurely.


PAN_DIR = 1 # 1 = normal, -1 = reverse. Change this if your servo is moving in the wrong direction.
TILT_DIR = 1 # 1 = normal, -1 = reverse. Change this if your servo is moving in the wrong direction.


PORT = 8000


def clamp(value, low, high):
    return max(low, min(value, high))


def find_cascade():
    pass


#servos 
# 17 and 18 are the GPIO pins on the Raspberry Pi that the servos are connected to. Change these if you are using different pins.
pan_servo = AngularServo(17, min_angle=-90, max_angle=90, min_pulse_width=0.0005, max_pulse_width=0.0025)
tilt_servo = AngularServo(18, min_angle=-90, max_angle=90, min_pulse_width=0.0005, max_pulse_width=0.0025)



