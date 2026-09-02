"""
Central config: every tunable constant for the turret lives here.
Change behavior by editing this file -- no other module hard-codes these values.
"""

# --- camera / frame ---
WIDTH = 640
HEIGHT = 360
HORIZONTAL_FOV = 66.0
VERTICAL_FOV = 38.0

DEADZONE = 20          # pixel radius around center where we don't chase
DETECT_MARGIN = 10     # on-screen guide box only (cosmetic)

# --- servo limits / geometry ---
ANGLE_LIMIT = 90.0     # pan, left/right
TILT_MIN = 30          # looking up
TILT_MAX = 180.0       # looking down
TILT_LEVEL = 130.0     # resting tilt (level with a seated person)
PAN_DIRECTION = -1
TILT_DIRECTION = 1

# --- hardware PWM (RP1 controller = chip 0 on this Pi) ---
PWM_CHIP = 0
SERVO_HZ = 50
PAN_CHANNEL = 3        # GPIO 19
TILT_CHANNEL = 2       # GPIO 18
LASER_PIN = 17         # GPIO 17 (on/off via transistor)

# --- servo speed caps (per-frame move limit; also the PID output limit) ---
PAN_MAX_STEP = 6
TILT_MAX_STEP = 6

# --- PID gains (raise KP, then add D, add small I only if it parks off-center) ---
PAN_KP = 0.35
PAN_KI = 0.0
PAN_KD = 0.02

TILT_KP = 0.35
TILT_KI = 0.0
TILT_KD = 0.02

# --- YOLO detector ---
MODEL_PATH = "yolov8n.pt"   # nano: smallest / fastest, CPU-appropriate
PERSON_CLASS = 0            # COCO id for "person"
CONF = 0.5                  # keep detections >= 50% confidence
YOLO_IMAGES = 256           # inference size (imgsz). Must be a multiple of 32. M8 speed dial.

HEAD_FOCUS = 0.35          # aim point up the box: 0.0 top, 0.5 center

# --- M6: weighted-score priority ---
W_SIZE = 1.0               # bigger box (usually closer) matters more
W_CENTER = 0.5             # closer to frame center matters more
W_CONF = 0.3               # more confident detection matters more

# --- M6: stealable lock (hysteresis) ---
CURRENT_TARGET_BONUS = 0.2  # stickiness added to the locked person's score (the sweep knob)
STEAL_PATIENCE = 3          # frames a challenger must out-score us before it can steal
LOST_GRACE_FRAMES = 8       # frames we hold a lock while the target is briefly off-screen