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

import os
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
TILT_MAX_STEP = 7

#----PID gains THESE ARE TUNABLE---
#raise KP first, then add D, add small amount of I if slightly off center
#for panning
PAN_KP = 0.35
PAN_KI = 0.0
PAN_KD = 0.02

#for tilting
TILT_KP = 0.45
TILT_KI = 0.0
TILT_KD = 0.03

#------------------------

def clamp(value, low, high):
    return max(low, min(high, value))


#converts a wanted angle into a PWM percentage
#standard servos expect a pulse width of 0.5ms (0 deg) to 2.5ms (180 deg) every 20ms.
def angle_to_duty(angle_limits):
    angle_limits = clamp(angle_limits, 0.0, 180.0)
    return 2.5 + (angle_limits / 180.0) * 10.0

face_cascade = cv2.CascadeClassifier("haarcascade_frontalface_default.xml")

