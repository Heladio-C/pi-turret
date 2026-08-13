"""
Pan tilt turret tracking:

Open loop face tracking with Raspberry Pi 5 HARDWARE PWM version.

Camera module 3 finds face, converts offset from the center frame into pan/tilt angles, making servos 
to follow. Live view is at http://turretpi.local:8000

Servos are driven by RP1's hardware PWM 


WIRING (Changed):

    Tilt servo signal has moved from pin 11(GPIO 17) to pin 35 (GPIO 19)
    Pan servo signal has remained unchanged pin 12
    Servos still powered from battery pack, common ground with Pi. 


    



"""