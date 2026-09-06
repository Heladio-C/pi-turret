"""
Perception: wraps YOLO + the tracker. This is the seam future milestones sit behind
-- M7 swaps in a fine-tuned model here, M8 swaps in an NCNN/quantized backend here,
and nothing else in the project has to change.

Detector.track(frame) -> (xyxy, confs, ids) as numpy arrays (empty if nobody found).
"""

import time

import numpy as np
from ultralytics import YOLO

from config import MODEL_PATH, YOLO_IMAGES, CONF, PERSON_CLASS


class Detector:
    def __init__(self):
        self.model = YOLO(MODEL_PATH)   # loads the network once
        self.infer_ms = 0.0

    def warmup(self, frame):
        # first inference is always slow; do it once before the loop
        self.model(frame, imgsz=YOLO_IMAGES, verbose=False)

    def track(self, frame):
        # persist=True keeps ByteTrack/BoT-SORT ids stable between calls
        t0 = time.monotonic()
        results = self.model.track(frame, imgsz=YOLO_IMAGES, conf=CONF,
                                   classes=[PERSON_CLASS], persist=True, verbose=False)
        self.infer_ms = (time.monotonic() - t0) * 1000.0

        boxes = results[0].boxes
        # boxes.id is None on frames with no confirmed tracks
        if len(boxes) > 0 and boxes.id is not None:
            xyxy = boxes.xyxy.cpu().numpy()
            confs = boxes.conf.cpu().numpy()
            ids = boxes.id.cpu().numpy().astype(int)
        else:
            xyxy = np.empty((0, 4))
            confs = np.empty((0,))
            ids = np.empty((0,), dtype=int)
        return xyxy, confs, ids