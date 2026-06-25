# Pi Turret 🤖🚀

An automated, dual-axis Raspberry Pi camera/laser turret utilizing SG90 (or similar) servos to achieve precise pan and tilt control. This project leverages the `gpiozero` library to handle Pulse Width Modulation (PWM) and smooth servo angling via mathematical sine wave sweeps.

<!-- TIP: Record a 5-second video of your turret moving, convert it to a GIF, name it "turret-demo.gif", put it in your folder, and uncomment the line below! -->
<!-- ![Turret Demo](turret-demo.gif) -->

---

## 🛠️ Hardware Requirements

*   **Raspberry Pi** (Any model with 40-pin GPIO headers)
*   **2x Servos** (Pan and Tilt, e.g., SG90, MG90S)
*   **External 5V Power Supply** (Recommended for powering servos to avoid overloading the Pi)
*   Jumper wires & breadboard

### Wiring Guide

| Component | Servo Pin | Raspberry Pi GPIO | Physical Pin |
| :--- | :--- | :--- | :--- |
| **Pan Servo** | Signal (Yellow/Orange) | **GPIO 17** | Pin 11 |
| **Tilt Servo** | Signal (Yellow/Orange) | **GPIO 18** | Pin 12 |
| **Both Servos** | Ground (Brown/Black) | **GND** | Any Ground Pin |
| **Both Servos** | Power (Red) | **External 5V (+)** | *Do not power directly from Pi 5V pin* |

> ⚠️ **Important Note on Power:** Servos draw significant current when moving. Powering them directly from the Raspberry Pi's 5V rail can cause the Pi to brownout or sustain permanent damage. Always use an external 5V power source and ensure the external power supply's Ground is tied back to the Pi's Ground.

---

## 💻 Software Setup

This project uses a Python virtual environment to keep dependencies clean.

### 1. Clone & Navigate to Project
```bash
git clone https://github.com/Heladio-C/pi-turret
cd pi-turret
