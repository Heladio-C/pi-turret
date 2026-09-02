#!/usr/bin/env python3
"""
Pan-Tilt Laser Turret -- Milestone 6 entry point.

Thin orchestrator: capture a frame, detect+track people, decide who to follow,
aim, draw, stream. All the real work lives in the modules:

  config.py     every tunable constant
  detector.py   YOLO + tracker  -> boxes/ids/confs
  tracking.py   weighted score + stealable lock (the M6 brain)
  hardware.py   servos + laser + PID loops
  streaming.py  MJPEG web server
  visualize.py  on-frame drawing
  pid.py        PID controller     utils.py  clamp

Run:
  python3 yolo_track.py                         # defaults, Ctrl+C to stop
  python3 yolo_track.py --bonus 0.2 --patience 3 --secs 120   # timed sweep run
"""

import os
import time
import argparse

import cv2
import numpy as np
from picamera2 import Picamera2

from config import WIDTH, HEIGHT, HEAD_FOCUS, CURRENT_TARGET_BONUS, STEAL_PATIENCE
from detector import Detector
from hardware import Turret
from tracking import score_people, TargetSelector
from streaming import output, start_server
import visualize


def main(bonus, patience, run_secs):
    # camera
    cam = Picamera2()
    cam.configure(cam.create_video_configuration(
        main={"size": (WIDTH, HEIGHT), "format": "RGB888"}, buffer_count=2))
    cam.start()
    time.sleep(1)

    # perception, hardware, decision brain, stream
    detector = Detector()
    detector.warmup(cam.capture_array())

    turret = Turret()
    selector = TargetSelector()
    server = start_server()
    print("Streaming at http://turretpi.local:8000  (Ctrl+C to stop)")
    print("Run config -> bonus=%.3f  patience=%d  secs=%.0f" % (bonus, patience, run_secs))

    cx = WIDTH // 2
    cy = HEIGHT // 2
    half_diag = np.sqrt(WIDTH ** 2 + HEIGHT ** 2) / 2.0
    previous_time = None
    fps = 0.0
    track_start = time.monotonic()

    try:
        while True:
            now = time.monotonic()

            # timed auto-stop for hands-free sweeping
            if run_secs > 0 and (now - track_start) >= run_secs:
                break

            dt = 0.0 if previous_time is None else (now - previous_time)
            previous_time = now
            if dt > 0:
                fps = 0.9 * fps + 0.1 * (1.0 / dt)

            frame = cam.capture_array()

            # detect + track
            xyxy, confs, ids = detector.track(frame)
            if len(ids) > 0:
                scores = score_people(xyxy, confs, cx, cy, half_diag)
            else:
                scores = np.empty((0,))

            # decide who to follow (M6 brain)
            target_idx = selector.update(ids, scores, bonus, patience)

            # aim (or hold)
            if target_idx is not None:
                x1, y1, x2, y2 = xyxy[target_idx].astype(int)
                body_cx = (x1 + x2) // 2
                body_cy = (y1 + HEAD_FOCUS * (y2 - y1))
                dx = body_cx - cx
                dy = body_cy - cy
                turret.follow(dx, dy, dt)
            else:
                turret.hold()

            # draw + stream
            visualize.draw_people(frame, xyxy, ids, scores, target_idx, selector, patience)
            elapsed_min = max((now - track_start) / 60.0, 1e-6)
            visualize.draw_hud(frame, selector, turret, detector, fps,
                               bonus, patience, len(ids), elapsed_min, cx, cy)

            ok, jpeg = cv2.imencode(".jpg", frame)
            if ok:
                output.update(jpeg.tobytes())

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        turret.stop()
        cam.stop()
        server.shutdown()

        # log one sweep row
        runtime = time.monotonic() - track_start
        mins = max(runtime / 60.0, 1e-6)
        steal_pm = selector.steal_count / mins
        reacq_pm = selector.reacquire_count / mins
        row = "%.3f,%d,%d,%d,%.1f,%.2f,%.2f" % (
            bonus, patience, selector.steal_count, selector.reacquire_count,
            runtime, steal_pm, reacq_pm)
        print("\nSweep row (bonus,patience,steals,reacquires,runtime_s,steals_per_min,reacq_per_min):")
        print(row)
        new_file = not os.path.exists("sweep.csv")
        with open("sweep.csv", "a") as f:
            if new_file:
                f.write("bonus,patience,steals,reacquires,runtime_s,steals_per_min,reacq_per_min\n")
            f.write(row + "\n")
        print("Added to sweep.csv")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="M6 turret tracker")
    ap.add_argument("--bonus", type=float, default=CURRENT_TARGET_BONUS,
                    help="current-target stickiness bonus (the sweep knob)")
    ap.add_argument("--patience", type=int, default=STEAL_PATIENCE,
                    help="frames a challenger must win before stealing the lock")
    ap.add_argument("--secs", type=float, default=0.0,
                    help="auto-stop after N seconds (0 = run until Ctrl+C)")
    args = ap.parse_args()
    main(args.bonus, args.patience, args.secs)