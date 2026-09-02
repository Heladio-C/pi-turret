"""
The M6 decision brain: given this frame's detections, decide WHO to follow.

  score_people(...)   -> a weighted score per person (size + centeredness + confidence)
  TargetSelector      -> holds the lock state machine (stealable lock + grace window)
                         and the two honest metrics (steal_count, reacquire_count).

selector.update(ids, scores, bonus, patience) -> target_idx (row index) or None to hold.
"""

import numpy as np

from config import WIDTH, HEIGHT, W_SIZE, W_CENTER, W_CONF, LOST_GRACE_FRAMES


def score_people(xyxy, confs, cx, cy, half_diag):
    """One weighted score per detected person. Bigger = more worth following."""
    x1, y1, x2, y2 = xyxy[:, 0], xyxy[:, 1], xyxy[:, 2], xyxy[:, 3]

    # size: box area as a fraction of the frame (~0..1)
    size_term = ((x2 - x1) * (y2 - y1)) / float(WIDTH * HEIGHT)

    # centeredness: 1.0 dead-center, 0.0 at the far corner
    box_cx = (x1 + x2) / 2.0
    box_cy = (y1 + y2) / 2.0
    distance = np.sqrt((box_cx - cx) ** 2 + (box_cy - cy) ** 2)
    center_term = np.clip(1.0 - distance / half_diag, 0.0, 1.0)

    conf_term = confs  # already 0..1

    return W_SIZE * size_term + W_CENTER * center_term + W_CONF * conf_term


class TargetSelector:
    def __init__(self):
        self.locked_id = None        # id we are currently following
        self.missing = 0             # frames the locked target has been off-screen
        self.pending_id = None       # a challenger (steal) or the grace candidate
        self.steal_counter = 0       # frames the challenger has out-scored us in a row
        self.locked_present = False  # was the locked target on-screen this frame?

        # honest metrics
        self.steal_count = 0         # bonus-gated switches (what the sweep measures)
        self.reacquire_count = 0     # switches caused by the target being lost

        self.status = "Searching..."

    def update(self, ids, scores, bonus, patience):
        target_idx = None
        self.status = "Searching..."
        self.locked_present = (self.locked_id is not None) and (self.locked_id in ids)

        if self.locked_present:
            self.missing = 0
            li = int(np.where(ids == self.locked_id)[0][0])
            locked_eff = scores[li] + bonus   # our score, inflated by stickiness

            # best OTHER person (mask out our own index)
            if len(ids) > 1:
                masked = scores.copy()
                masked[li] = -np.inf
                ci = int(masked.argmax())
                challenger_won = masked[ci] > locked_eff
            else:
                ci = None
                challenger_won = False

            if challenger_won:
                cand_id = int(ids[ci])
                if cand_id == self.pending_id:
                    self.steal_counter += 1
                else:
                    self.pending_id = cand_id
                    self.steal_counter = 1

                if self.steal_counter >= patience:      # STEAL
                    self.steal_count += 1
                    self.locked_id = cand_id
                    target_idx = ci
                    self.pending_id = None
                    self.steal_counter = 0
                    self.status = "Tracking id %d" % self.locked_id
                else:
                    target_idx = li                     # hold current for now
                    self.status = "Locked id %d (challenged by %d %d/%d)" % (
                        self.locked_id, cand_id, self.steal_counter, patience)
            else:
                self.pending_id = None
                self.steal_counter = 0
                target_idx = li
                self.status = "Tracking id %d" % self.locked_id

        else:
            # locked target is off-screen (or we have no lock yet)
            if self.locked_id is not None:
                self.missing += 1

            if (self.locked_id is None) or (self.missing >= LOST_GRACE_FRAMES):
                if len(ids) > 0:
                    new_idx = int(scores.argmax())
                    new_id = int(ids[new_idx])
                    if (self.locked_id is not None) and (new_id != self.locked_id):
                        self.reacquire_count += 1
                    self.locked_id = new_id
                    self.missing = 0
                    self.pending_id = None
                    self.steal_counter = 0
                    target_idx = new_idx
                    self.status = "Tracking id %d" % self.locked_id
                else:
                    self.locked_id = None
                    self.missing = 0
                    self.pending_id = None
                    self.steal_counter = 0
                    self.status = "Searching..."
            else:
                # short dropout -> hold, and mark who we'd grab if it stays gone
                self.status = "Reacquiring id %d" % self.locked_id
                if len(ids) > 0:
                    cand_idx = int(scores.argmax())
                    self.pending_id = int(ids[cand_idx])
                    self.steal_counter = 0
                else:
                    self.pending_id = None

        return target_idx