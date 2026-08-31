"""
ALL TUNABLES IN THE PROGRAM: change behavior by editing this file
"""

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



#----PID gains--------
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
