"""
Everything that physically moves: the two servos (hardware PWM), the laser, and
the two PID loops that turn a pixel error into servo motion.

Turret.follow(dx, dy, dt)  -> aim at a target that's dx,dy pixels off center
Turret.hold()              -> target lost: freeze servos, clear PID history, laser off
Turret.stop()             -> shutdown (laser off, PWM stopped)
"""

from rpi_hardware_pwm import HardwarePWM
from gpiozero import LED

from utils import clamp
from pid import PID
from config import (
    PWM_CHIP, SERVO_HZ, PAN_CHANNEL, TILT_CHANNEL, LASER_PIN,
    TILT_LEVEL, ANGLE_LIMIT, TILT_MIN, TILT_MAX,
    PAN_DIRECTION, TILT_DIRECTION, DEADZONE,
    WIDTH, HEIGHT, HORIZONTAL_FOV, VERTICAL_FOV,
    PAN_KP, PAN_KI, PAN_KD, PAN_MAX_STEP,
    TILT_KP, TILT_KI, TILT_KD, TILT_MAX_STEP, LASER_ON
)


# angle (0..180) -> PWM duty %. 2.5%-12.5% = 0.5-2.5 ms pulse at 50 Hz.
def angle_to_duty(angle):
    angle = clamp(angle, 0.0, 180.0)
    return 2.5 + (angle / 180.0) * 10.0


class Turret:
    def __init__(self):
        self.pan_pwm = HardwarePWM(pwm_channel=PAN_CHANNEL, hz=SERVO_HZ, chip=PWM_CHIP)
        self.tilt_pwm = HardwarePWM(pwm_channel=TILT_CHANNEL, hz=SERVO_HZ, chip=PWM_CHIP)

        self.pan_angle = 0.0
        self.tilt_angle = TILT_LEVEL
        self.pan_pwm.start(angle_to_duty(self.pan_angle + 90))
        self.tilt_pwm.start(angle_to_duty(self.tilt_angle))

        self.laser = LED(LASER_PIN)

        if LASER_ON:
            self.laser.on()
        else:
            self.laser.off()

        self.pan_pid = PID(PAN_KP, PAN_KI, PAN_KD, PAN_MAX_STEP)
        self.tilt_pid = PID(TILT_KP, TILT_KI, TILT_KD, TILT_MAX_STEP)

    def follow(self, dx, dy, dt):
        """Aim at a target dx,dy pixels from center. Fires the laser when centered.
        Returns True if the target is inside the deadzone on both axes."""
        # PAN
        if abs(dx) <= DEADZONE:
            self.pan_pid.reset()
        else:
            error_deg = (dx / WIDTH) * HORIZONTAL_FOV
            self.pan_angle += PAN_DIRECTION * self.pan_pid.update(error_deg, dt)
            self.pan_angle = clamp(self.pan_angle, -ANGLE_LIMIT, ANGLE_LIMIT)

        # TILT
        if abs(dy) <= DEADZONE:
            self.tilt_pid.reset()
        else:
            error_deg = (dy / HEIGHT) * VERTICAL_FOV
            self.tilt_angle += TILT_DIRECTION * self.tilt_pid.update(error_deg, dt)
            self.tilt_angle = clamp(self.tilt_angle, TILT_MIN, TILT_MAX)

        self.pan_pwm.change_duty_cycle(angle_to_duty(self.pan_angle + 90))
        self.tilt_pwm.change_duty_cycle(angle_to_duty(self.tilt_angle))

        centered = (abs(dx) <= DEADZONE) and (abs(dy) <= DEADZONE)

        if not LASER_ON:
            if centered:
                self.laser.on()
            else:
                self.laser.off()
        return centered

    def hold(self):
        """No target: freeze servos where they are, clear PID history, laser off."""
        self.pan_pid.reset()
        self.tilt_pid.reset()
        if not LASER_ON:
            self.laser.off()

    def stop(self):
        self.laser.off()
        self.pan_pwm.stop()
        self.tilt_pwm.stop()