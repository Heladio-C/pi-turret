#record_clips.py
#milestone 7: collect hand photos for fine tuning YOLO

# How to use: 
# type a short label describing what you will show to the camera, counts down then takes a burst of photos whiile you move your
# hand around
# each photo is saved as a jpg to annotate later, no video files , 




from picamera2 import Picamera2 # controls the pi camera 
import cv2 # opencv to save images 
import time
from datetime import datetime
import os
