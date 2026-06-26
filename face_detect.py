import cv2
from picamera2 import Picamera2
from time import sleep

#start the camera
picam = Picamera2()
config = picam.create_still_configuration(main={"size": (640, 480)})
picam.configure(config)
picam.start()
sleep(3) # lets the cam warm up, and auto focus

#load in the built in face detector
cascade_path = "haarcascade_frontalface_default.xml"
face_detector = cv2.CascadeClassifier(cascade_path)

print("Detecting faces. Press Ctrl + C to stop")
print("Open 'lastest.jpg' to see results")

try:
	while True:
		frame = picam.capture_array()
		frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

		gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
		faces = face_detector.detectMultiScale(gray, scaleFactor = 1.1, minNeighbors = 5, minSize = (60, 60))

		for(x, y, w, h) in faces:
			cv2.rectangle(frame, (x,y), (x + w ,y + h), (0,255,0), 3)

		#save frame
		cv2.imwrite("latest.jpg", frame)
		print(f"\rFaces found: {len(faces)}   ", end= "", flush = True)
		sleep(2)

except KeyboardInterrupt:
	print("\nStopping.")
finally:
	picam.stop()
	print("Cam released")

