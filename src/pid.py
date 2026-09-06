"""One-axis PID controller. Pure math -- knows nothing about servos or cameras."""

from utils import clamp


class PID:
    def __init__(self, kp, ki, kd, output_limit):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.output_limit = output_limit
        self.integral = 0.0
        self.previous_error = 0.0
        self.first = True
        self.last_p = self.last_i = self.last_d = 0.0

    def reset(self):
        self.integral = 0.0
        self.previous_error = 0.0
        self.first = True
        self.last_p = self.last_i = self.last_d = 0.0

    def update(self, error, dt):
        # error = pixels off center, dt = seconds since last frame
        P = self.kp * error

        if self.first or dt <= 0:
            # no previous sample -> skip I and D this frame
            derivative = 0.0
            self.first = False
        else:
            self.integral += error * dt
            if self.ki > 0:
                windup_limit = self.output_limit / self.ki
                self.integral = clamp(self.integral, -windup_limit, windup_limit)
            derivative = (error - self.previous_error) / dt

        I = self.ki * self.integral
        D = self.kd * derivative

        self.previous_error = error
        self.last_p = P
        self.last_i = I
        self.last_d = D

        return clamp(P + I + D, -self.output_limit, self.output_limit)