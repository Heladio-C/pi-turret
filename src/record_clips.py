


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
OUT_DIR = Path(__file__).resolve().parent / "dataset" / "clips"


def slugify(text:str) -> str:
    pass


def record_one(picam, label: str, secs: int) -> Path:
    pass

