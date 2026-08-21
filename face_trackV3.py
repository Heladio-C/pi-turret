#!/usr/bin/env python3

"""
Pan-Tilt Laser Turret: Phase 4 PID controller for face tracking

New changes:
Involve a PID controller: constantly calculating how much effort is needed to get a desired output
In this case we will get an angle as output

Proportional: Acts as a spring force, 


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

