import time
from gpiozero import AngularServo

# 1. Initialize servos exactly as they are in your main script
pan_servo = AngularServo(17, initial_angle=0.0, min_angle=-90, max_angle=90, min_pulse_width=0.0005, max_pulse_width=0.0025)
tilt_servo = AngularServo(18, initial_angle=90.0, min_angle=0, max_angle=180, min_pulse_width=0.0005, max_pulse_width=0.0025)

def smooth_sweep(servo, start_angle, end_angle, step=1.0, delay=0.015):
    """
    Moves a servo smoothly from start to end by taking small steps.
    - step: How many degrees to move per frame (lower = smoother)
    - delay: How long to pause between steps in seconds (lower = faster)
    """
    # Determine if we are sweeping forward (+1) or backward (-1)
    direction = 1 if end_angle > start_angle else -1
    
    current_angle = start_angle
    
    # We use a while loop so we can use decimal steps (like 0.5 degrees)
    while (direction == 1 and current_angle <= end_angle) or \
          (direction == -1 and current_angle >= end_angle):
        
        servo.angle = current_angle
        time.sleep(delay)  # The magic pause that controls the speed
        current_angle += (step * direction)

try:
    print("Sweeping Pan (Left/Right)...")
    smooth_sweep(pan_servo, 0.0, 90.0)    # Center to limit 1
    smooth_sweep(pan_servo, 90.0, -90.0)  # Limit 1 to limit 2
    smooth_sweep(pan_servo, -90.0, 0.0)   # Limit 2 back to center
    
    # Pause for a second between axes
    time.sleep(1)

    print("Sweeping Tilt (Up/Down)...")
    smooth_sweep(tilt_servo, 150.0, 65.0) # Center to upper limit
    smooth_sweep(tilt_servo, 65.0, 180.0)  # Upper limit to lower limit
    smooth_sweep(tilt_servo, 180, 150.0)   # Lower limit back to center

except KeyboardInterrupt:
    print("\nTest interrupted by user.")

finally:
    # 2. The Rest Position
    print("Returning to rest position...")
    pan_servo.angle = 0.0
    tilt_servo.angle = 90.0
    time.sleep(0.5)
    
    # Power off the signal so they don't jitter while idle
    pan_servo.detach()
    tilt_servo.detach()
    print("Done!")