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

def clamp(value, low, high):
    return max(low, min(value, high))




