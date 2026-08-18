"""
Hardware PWM test - TILT servo only (Raspberry Pi 5)

Drives the tilt servo on GPIO 18 using the RP1's HARDWARE PWM instead of
software PWM, so you can hear/see whether the jitter goes away. No rewiring:
GPIO 18 is already a hardware-PWM pin and your tilt servo is already on it.
(Pan stays on software PWM for now, so you can compare the two.)

ONE-TIME SETUP:
  1. sudo nano /boot/firmware/config.txt
     add this line (its own line, near the bottom):   dtoverlay=pwm-2chan
  2. sudo reboot
  3. sudo pip3 install rpi-hardware-pwm --break-system-packages
  4. after reboot check it loaded:  ls /sys/class/pwm/   (should show a pwmchip)

RUN:  python3 pwm_test.py      Stop: Ctrl+C
  (if you get a permission error on /sys/class/pwm, run: sudo python3 pwm_test.py)
"""

import time
from rpi_hardware_pwm import HardwarePWM

# On the Pi 5: channel 2 = GPIO 18, and the PWM lives on chip 2.
tilt = HardwarePWM(pwm_channel=2, hz=50, chip=0)   # 50 Hz = standard servo frame

TILT_MIN_ANGLE = 0

tilt.start(angle_to_duty(90))   # begin near the middle
print("Hardware PWM live on GPIO 18. Watch the sweeps, LISTEN at the holds.")

try:
    while True:
        # fine 1-degree steps up (this is what mimics tracking micro-adjustments)
        for a in range(60, 121):
            tilt.change_duty_cycle(angle_to_duty(a))
            time.sleep(0.03)
        print("holding at 120 - listen for buzz (2s)")
        time.sleep(2)                       # HOLD: software PWM hums here; hardware should be silent

        # fine 1-degree steps back down
        for a in range(120, 59, -1):
            tilt.change_duty_cycle(angle_to_duty(a))
            time.sleep(0.03)
        print("holding at 60 - listen for buzz (2s)")
        time.sleep(2)

except KeyboardInterrupt:
    print("\nStopping.")
finally:
    tilt.stop()


