# Pan-Tilt Laser Turret — Real-Time Person Tracking on the Edge

A pan-tilt camera turret that detects people with **YOLOv8**, follows **one chosen
target** through a priority + lock system, and keeps a laser pointer centered on them —
running entirely on a **Raspberry Pi 5 CPU**, no GPU, no cloud.

The project is a computer-vision / edge-ML build: a modern detector, a multi-object
tracking-and-priority layer, and a measurement-driven approach to tuning — deployed on
constrained hardware with a real actuation loop.

<!-- TODO: record a ~30s clip (tracking + a yellow "challenger" steal + the laser) and save it as docs/demo.gif -->
![Demo](docs/demo.gif)

---

## Highlights

- **Modern detector, on CPU.** YOLOv8n via Ultralytics on a CPU-only PyTorch build, tracking people in real time on a Pi 5.
- **Follows a *specific* person.** BoT-SORT assigns stable IDs; a weighted-score priority rule + a stealable lock (hysteresis) decide who to follow when several people are in frame, and hold that choice instead of flickering.
- **Measurement-driven tuning.** Two documented parameter sweeps — detector resolution (speed/accuracy) and lock stickiness (switch stability) — each with a chosen operating point and the reasoning behind it.
- **Honest evaluation.** Tracking switches are split into *steals* vs *re-acquires* and logged to CSV, which surfaced a real limitation (see [Limitations](#limitations--future-work)) rather than hiding it.
- **Smooth control.** Two-axis PID on real measured `dt`, driven by the Pi 5's RP1 **hardware PWM** (zero servo jitter).

**Stack:** Python · Ultralytics YOLOv8 · PyTorch (CPU) · OpenCV · Picamera2 · Raspberry Pi 5

---

## Contents
- [How it works](#how-it-works)
- [Results & engineering decisions](#results--engineering-decisions)
- [Hardware](#hardware)
- [Setup & run](#setup--run)
- [Milestone roadmap](#milestone-roadmap)
- [Limitations & future work](#limitations--future-work)
- [Repo structure](#repo-structure)
- [Safety](#safety)

---

## How it works

Each frame runs a five-stage loop:

1. **Capture** — Picamera2 grabs a frame (a shallow 2-buffer queue keeps it fresh, not ~0.5 s stale).
2. **Detect + track** — `model.track(persist=True)` returns every person with a stable ID.
3. **Decide** — each person gets a weighted score (size + centeredness + confidence); a lock + hysteresis rule picks who to follow.
4. **Aim** — the target's offset from center feeds a per-axis PID that drives the servos; the laser fires when the target is centered.
5. **Stream** — the annotated frame is served as MJPEG to a browser.

The code is organized so each concern is swappable — in particular, the detector sits
behind a single interface, which is where the planned fine-tuning (M7) and quantization
(M8) work will plug in without touching the rest:

| Module | Responsibility |
|---|---|
| `config.py` | Every tunable constant (one dial-board) |
| `detector.py` | YOLO + tracker → boxes / IDs / confidences |
| `tracking.py` | Weighted-score priority + stealable lock (the decision brain) |
| `hardware.py` | Servos, laser, and the two PID loops |
| `pid.py`, `utils.py` | PID controller; small helpers |
| `streaming.py`, `visualize.py` | MJPEG server; on-frame drawing |
| `yolo_track.py` | Thin orchestrator wiring it together |

---

## Results & engineering decisions

### Detector resolution sweep (M5)

Inference dominates the loop, and its cost scales roughly with pixel area, so input
resolution (`imgsz`) is the main speed dial. Measured on YOLOv8n, Pi 5 CPU:

| imgsz | FPS | infer (ms) | notes |
|---:|---:|---:|---|
| 640 | 4 | 255 | sharpest, too slow to track motion |
| 320 | 13 | 76 | comfortable; longest detection range |
| **256** | **18** | **53** | **operating point — steady boxes, minimal FPS cost** |
| 224 | 22 | 42 | sweet spot for pure speed; smooth tracking |
| 192 | 25 | 37 | fastest, but box jitter makes the aim sway |

**Key insight:** the fastest size that *detects* (192) is not the fastest that *tracks
smoothly* (224) — at 192 the box jitters and the controller chases the noise. The
stability floor, not raw FPS, sets the operating point. The turret runs one step up at 256
for slightly steadier boxes and range at a small FPS cost (18 vs 22).

### Priority-lock stickiness sweep (M6)

The lock gives the current target a score **bonus**; a challenger must beat it for several
frames straight to steal the lock. Sweeping that bonus (60 s per setting, two people in
frame), with switches split into bonus-gated *steals* and lost-target *re-acquires*:

| bonus | steals | re-acquires | steals/min | reacq/min |
|---:|---:|---:|---:|---:|
| 0.0 | 2 | 3 | 2.00 | 2.99 |
| 0.1 | 2 | 3 | 1.98 | 2.98 |
| **0.2** | **0** | **2** | **0.00** | **1.99** |
| 0.4 | 0 | 6 | 0.00 | 5.98 |
| 0.8 | 0 | 4 | 0.00 | 3.97 |

<!-- TODO: add a line chart of steals/min and reacq/min vs bonus as docs/m6_sweep.png -->

**Operating point: bonus = 0.2** — the smallest value that fully stabilizes the lock
against opportunistic steals. (Counts are small, so this is a directional result, not a
precision measurement.) The sweep also exposed the limitation below: at any sane operating
point, re-acquires — not the priority logic — drive most of the switching.

---

## Hardware

| Part | Notes |
|---|---|
| Raspberry Pi 5 | active cooler; run headless over SSH |
| Camera Module 3 (imx708) | needs a **22→15-pin adapter** cable on the Pi 5 |
| 2× SG90 servos | on a pan-tilt bracket |
| KY-008 laser module | 5 mW, 650 nm, **Class 2**; switched via transistor |
| 2N2222 (NPN) + 1 kΩ | low-side switch so the GPIO doesn't source the laser current |
| 4×AA battery pack | powers the servos; shares a common ground with the Pi |
| Breadboard + jumpers | |

**Signal wiring** (Pi sends signal + ground only; the battery powers the motors):

```
Pan servo signal   -> GPIO 19 (pin 35)   hardware PWM ch3
Tilt servo signal  -> GPIO 18 (pin 12)   hardware PWM ch2
Laser (via 2N2222) -> GPIO 17 (pin 11)
Pi GND             -> breadboard (–) rail (common ground with battery)
```

Only GPIO 12/13/18/19 support hardware PWM on the Pi 5, which is why pan lives on 19 and
tilt on 18. Camera geometry: 0° tilt looks up at the ceiling, ~125° looks level at a
seated person; rest tilt is 130°.

---

## Setup & run

**OS:** Raspberry Pi OS Trixie (64-bit) on a Pi 5.

**Enable hardware PWM** — add `dtoverlay=pwm-2chan` to `/boot/firmware/config.txt`, reboot.

**Install (order matters).** Installing `ultralytics` first pulls the GPU build of
PyTorch (gigabytes of CUDA the Pi can't use, which overflowed the SD card). Install
CPU-only PyTorch **first**:

```bash
pip3 install torch torchvision \
    --index-url https://download.pytorch.org/whl/cpu \
    --break-system-packages --no-cache-dir
pip3 install ultralytics rpi-hardware-pwm --break-system-packages --no-cache-dir
# if the first .track() asks for lap:
pip3 install lapx --break-system-packages --no-cache-dir
```

Verify CPU-only: `python3 -c "import torch; print(torch.__version__, torch.version.cuda)"`
should print `...+cpu None`.

**Run** (from inside `src/`, so the module imports resolve):

```bash
cd src
python3 yolo_track.py                                   # defaults, Ctrl+C to stop
python3 yolo_track.py --bonus 0.2 --patience 3 --secs 120   # timed run, logs a row to sweep.csv
```

Then open **http://turretpi.local:8000** in a browser to watch the stream. Reproduce the
M6 sweep with:

```bash
for b in 0 0.1 0.2 0.4 0.8; do
  python3 yolo_track.py --bonus $b --patience 3 --secs 120
done
```

Always stop with **Ctrl+C** (never Ctrl+Z) so the shutdown handler turns the laser off and
releases the servos.

---

## Milestone roadmap

| # | Milestone | Status | Signal |
|---|---|---|---|
| 1 | Servos + manual control | ✅ | Control/wiring foundation |
| 2 | Haar face detection + browser stream | ✅ | Perception pipeline online |
| 3 | Open-loop tracking (pixel→angle, hardware PWM) | ✅ | Closed the see→move loop |
| 4 | Two-axis PID on real `dt` | ✅ | Smooth control quality |
| 5 | YOLOv8 swap + resolution/latency sweep | ✅ | Classical→DL; measured baseline |
| 6 | Multi-object tracking + priority (weighted score + stealable lock) | ✅ | Tracking logic + evaluation rigor |
| 7 | Fine-tune on a custom class; mAP before/after on a held-out set | ⏳ | Training loop + honest evaluation |
| 8 | Edge inference profiling + INT8 / NCNN quantization | ⏳ | Latency/accuracy tradeoff on edge HW |

---

## Limitations & future work

- **ID stability under camera motion.** The tracker (BoT-SORT) assumes a roughly static
  camera, but this turret *pans to cancel* its target's motion — a near worst case. The M6
  sweep showed re-acquires (a dropped ID being replaced) dominate switching, not the
  priority logic. The measured next step is a tracker config tuned for a moving camera
  (motion compensation + a longer lost-track memory), weighed against its FPS cost on the Pi.
- **Aim point drifts with distance.** The aim uses a fixed fraction up the body box; a
  robust fix is dedicated head detection.
- **Next milestones (7–8)** target the core ML-engineer signal: fine-tuning with honest
  before/after mAP, then quantization (INT8 via NCNN) with the speed-vs-accuracy tradeoff
  measured against the M5 baseline.

---

## Repo structure

```
pi-turret/
├── src/            # the live system (modular)
│   ├── yolo_track.py    # entry point / orchestrator
│   ├── config.py       # all tunable constants
│   ├── detector.py     # YOLO + tracker
│   ├── tracking.py     # priority + stealable lock
│   ├── hardware.py     # servos, laser, PID
│   ├── pid.py  utils.py
│   └── streaming.py  visualize.py
├── archive/        # progression: Haar → face-track v1–v4 → YOLO (kept intentionally)
├── requirements.txt
└── README.md
```

The `archive/` folder is deliberate: it preserves the classical-CV → deep-learning
progression the project actually went through.

---

## Safety

The laser is a **Class 2** (5 mW, 650 nm) module. It is transistor-switched and turned off
on shutdown. Even at Class 2, avoid direct eye exposure — keep the aim in a controlled area
during demos and don't leave it running unattended. This is a learning/portfolio build, not
a product.