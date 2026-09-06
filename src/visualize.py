"""
All on-frame drawing lives here so the main loop stays about logic, not pixels.
  draw_people(...) -> boxes: green=locked, yellow=challenger/grace candidate, grey=other
  draw_hud(...)    -> the corner readouts (status, FPS, infer ms, metrics, PID terms)
"""

import cv2

from config import WIDTH, HEIGHT, DEADZONE, DETECT_MARGIN, LOST_GRACE_FRAMES


def draw_people(frame, xyxy, ids, scores, target_idx, selector, patience):
    for i in range(len(ids)):
        bx1, by1, bx2, by2 = xyxy[i].astype(int)

        if i == target_idx:
            color, thick = (0, 255, 0), 2
            label = "id %d LOCK s%.2f" % (ids[i], scores[i])

        elif selector.pending_id is not None and ids[i] == selector.pending_id:
            color, thick = (0, 255, 255), 2
            if selector.locked_present:
                # steal building: our target is still here, this one is out-scoring it
                label = "id %d CHAL %d/%d s%.2f" % (ids[i], selector.steal_counter, patience, scores[i])
            else:
                # grace countdown: our target is gone, this is who we'll grab next
                label = "id %d ACQ %d/%d s%.2f" % (ids[i], selector.missing, LOST_GRACE_FRAMES, scores[i])

        else:
            color, thick = (160, 160, 160), 1
            label = "id %d s%.2f" % (ids[i], scores[i])

        cv2.rectangle(frame, (bx1, by1), (bx2, by2), color, thick)
        cv2.putText(frame, label, (bx1, by1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)


def draw_hud(frame, selector, turret, detector, fps, bonus, patience, n_people, elapsed_min, cx, cy):
    # guide box, deadzone, crosshair
    cv2.rectangle(frame, (DETECT_MARGIN, DETECT_MARGIN),
                  (WIDTH - DETECT_MARGIN, HEIGHT - DETECT_MARGIN), (0, 165, 255), 1)
    cv2.rectangle(frame, (cx - DEADZONE, cy - DEADZONE),
                  (cx + DEADZONE, cy + DEADZONE), (255, 255, 0), 1)
    cv2.drawMarker(frame, (cx, cy), (0, 255, 255), cv2.MARKER_CROSS, 12, 1)

    cv2.putText(frame, "%s  %.0f FPS" % (selector.status, fps), (8, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    cv2.putText(frame, "pan %.1f  tilt %.1f" % (turret.pan_angle, turret.tilt_angle), (8, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
    cv2.putText(frame, "infer %.0f ms" % detector.infer_ms, (8, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

    steal_pm = selector.steal_count / elapsed_min
    reacq_pm = selector.reacquire_count / elapsed_min
    cv2.putText(frame, "steals %d (%.1f/min)  reacq %d (%.1f/min)  people %d" % (
        selector.steal_count, steal_pm, selector.reacquire_count, reacq_pm, n_people),
        (8, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
    cv2.putText(frame, "bonus %.2f  patience %d" % (bonus, patience), (8, 100),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

    pp, tp = turret.pan_pid, turret.tilt_pid
    cv2.putText(frame, "PAN  P%+.2f I%+.2f D%+.2f" % (pp.last_p, pp.last_i, pp.last_d),
                (8, HEIGHT - 28), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
    cv2.putText(frame, "TILT P%+.2f I%+.2f D%+.2f" % (tp.last_p, tp.last_i, tp.last_d),
                (8, HEIGHT - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)