from gpiozero import AngularServo
from time import sleep, time
import math

# pan is for pin 11, GPIO 17
# tilt is for pin 12, GPIO 18
pan = AngularServo(17, min_angle =- 90, max_angle = 90, min_pulse = 0.5/1000, max_pulse = 2.5/1000)
tilt = AngularServo(18, min_angle =- 90, max_angle = 90, min_pulse = 0.5/1000, max_pulse = 2.5/1000)

def center():
    pan.angle = 0
    tilt.angle = 0
    sleep(0.5)

print("Centering...")
center()
sleep(1)

print("Sweeping! Press Ctrl+C to stop.")
try:
    start = time()
    while True:
        t = time() - start
        pan.angle  = 45 * math.sin(2 * math.pi * t / 4.0)   # pan: gentle ±45°
        tilt.angle = 25 * math.sin(2 * math.pi * t / 6.0)   # tilt: gentle ±25°
        sleep(0.02)
except KeyboardInterrupt:
    print("\nStopping and centering...")
    center()
    pan.detach()
    tilt.detach()
    print("Complete!")