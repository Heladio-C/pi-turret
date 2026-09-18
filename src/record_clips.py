


import argparse
import re
import time
import cv2

from datetime import datetime
from pathlib import Path

from picamera2 import Picamera2

WIDTH = 640
HEIGHT = 360 #or 1280 x 720

DEFAULT_SECS = 30
OUTPUT_DIR = Path(__file__).resolve().parent / "dataset" / "clips"

#turn free text label into a filename fragement
def slugify(text:str) -> str:
    #remove whitespace, then turn all uppercase letters to lowercase 

    text = re.sub(r"[^a-z0-9]+", "_", text.strip().lower())
    return text.strip("_") or "clip"    


def record_one(picam, label: str, secs: int) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = OUTPUT_DIR / f"{slugify(label)}_{stamp}.avi"

    #unpack string MPJPG 
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    #arguments: output file destination, 32-bit codec tag, fram rate, and frame dimensions using tuple
    writer = cv2.VideoWriter(str(path), fourcc, 30.0, (WIDTH, HEIGHT))

    if not writer.isOpened():
        raise RuntimeError("could not open video writer ")

    for n in (3, 2, 1):
        print(f"  recording in {n}...", end="\r", flush = True)
        time.sleep(1)

    print(" " * 36, end="\r")
    frames = 0
    t0 = time.time()

    try:
        while time.time() - t0 < secs:
            frame = picam.capture_array()
            writer.write(frame)
            frames += 1
            print(f"  \u25cf REC {label!r}  {time.time()-t0:4.1f}/{secs}s  "
                  f"{frames} frames", end="\r", flush=True)


    except KeyboardInterrupt:
        print("Ended early")
    finally:
        writer.release()

    print(f" saved {frames} frames to {path}")
    return path



def main():
    pass


if __name__ == "__main__":
    main()