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


#settings 
FOLDER_NAME = "dataset/images"
WIDTH = 640
HEIGHT = 360


IMAGES_PER_CLIP = 20 # how many photos each burst takes
SECONDS_BETWEEN = 0.5 # pause between photos
COUNTDOWN = 3


MAX_TOTAL_IMAGES = 600

#get camera ready 
os.makedirs(FOLDER_NAME, exist_ok=True)

picam2 = Picamera2()
#configuration is just the camera's settings, 
camera_config = picam2.create_video_configuration(main={"size": (WIDTH, HEIGHT), "format": "RGB888"})
picam2.configure(camera_config)
picam2.start()
time.sleep(1)

print(f"Camera Ready! Saving pics to: {FOLDER_NAME}")
print("Type a label before each burst. Prese Enter on an empty line to quit.\n")


#helper turn a typed label into safe filename piece
