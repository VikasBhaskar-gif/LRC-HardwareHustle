# LRC Hardware Controller — Industrial SCADA Dashboard & Bridge

An interactive, light-industrial SCADA/HMI dashboard for the Lam Research Challenge 3.0 (Stage 2) Liquid-Handling System, interfacing with the ESP32 NodeMCU over USB Serial at 115200 baud.

## Architecture

- **Frontend**: Clean, light-themed single-page application in [`ui/`](file:///d:/Projects/LRC_Hardware_Controller/ui) (`index.html`, `styles.css`, `app.js`).
- **Hydraulic Schematic**: Dominant SVG Piping & Instrumentation Diagram (P&ID) with **direct component clickability** (click pumps or solenoid valve directly on the schematic to control them).
- **Python Serial Bridge**: `ui/bridge.py` (FastAPI + WebSocket + PySerial + Mock Firmware Emulator).
- **Communication Protocol**: USB Serial (115200 baud) $\longleftrightarrow$ Python Bridge $\longleftrightarrow$ WebSocket (`ws://127.0.0.1:8080/ws`) $\longleftrightarrow$ Browser UI.

---

## 1. Quick Start Guide

### Prerequisites
Python 3.10+ installed with dependencies:
```bash
cd d:\Projects\LRC_Hardware_Controller\ui
pip install -r requirements.txt
```

### Launch the Bridge & Dashboard
From the project root:
```bash
python ui/bridge.py
```

Open your browser to:
**[http://127.0.0.1:8080](http://127.0.0.1:8080)**

---

## 2. Redesigned Light Industrial Interface

### Direct Schematic Interactions (No Cluttered Bottom Toolbar)
- **Click Pump 1 (U2)**: Opens popover with duty presets (25%, 50%, 75%, 100%), Stop (`0`), Enable (`e`), Disable (`d`).
- **Click Pump 2 (U3)**: Opens popover with duty presets (25%, 50%, 75%, 100%), Stop (`9`), Enable (`q`), Disable (`w`), Direction (`f`/`v`).
- **Click Pump 3 (U4)**: Opens popover with Stop (`i`), Status (`p`), and firmware safety restriction note (manual start rejected because flush line valve has no sensor).
- **Click Solenoid Valve (GPIO 27)**: Directly toggles solenoid (`k`) or displays explicit Open (`a`) / Close (`c`).
- **Hover/Click FT-01**: Displays live flow rate (L/min), frequency (Hz), and data freshness.
- **Click Flush Button (GPIO 34)**: In Mock mode, triggers the Case 2 90-second continuous flush sequence.

### Compact Status & Flush Countdown
- Located directly above the hydraulic diagram:
  - System state indicator: `● CASE 1 · NORMAL`, `● SUMP HIGH`, `● FLUSH PROCESS IN PROGRESS`, etc.
  - Case 2 countdown monitor: `⏱ FLUSHING: 88.2s` with animated progress bar during the 90-second flush.
  - Action presets: `▶ Normal Flow [N]`, `Sim Norm [n]`, `Sump High [x]`, `Return [r]`, and `Status [p]`.

### Narrow Left Column & Flow Table
- Narrowed by ~22% to maximize center diagram size.
- Contains compact ESP32 connection card with port selector, Connect/Disconnect, and Mock toggle.
- Displays strictly the **latest 10 flow records** without scrolling.
- Includes CSV export and clear log buttons.

### Clean Right Column
- Light-themed real-time Canvas graph plotting Flow Rate (L/min) against rolling 30-second window.
- Dual-tab console toggleable between **Event Log** and **Serial Terminal** (send custom commands and view raw output).

---

## 3. Connecting to Hardware or Simulation

### A. Real ESP32 Hardware
1. Connect the ESP32 NodeMCU to the PC via USB.
2. In the top-left card, click **Refresh (&#x21BB;)** to scan COM ports.
3. Select your ESP32 COM port (e.g., `COM3`, `COM4`).
4. Click **CONNECT**.

### B. Mock / Simulation Mode (No Hardware Needed)
1. Check the **Mock Mode** box (or select `MOCK ESP32` from the dropdown).
2. Click **CONNECT**.
3. The bridge launches an in-memory ESP32 firmware emulator that accurately mimics all commands, periodic heartbeats, CSV flow streaming, and Case 2 flush sequences.

---

## 4. Arduino Serial Monitor Coexistence

The USB COM port on Windows is **exclusive**—only one program can hold it open at a time.

- **To use Arduino IDE Serial Monitor or PlatformIO Monitor**:
  Click **DISCONNECT** in the dashboard. This releases the COM port immediately without stopping the bridge server.
- **To resume dashboard control**:
  Close Arduino Serial Monitor and click **CONNECT** in the dashboard.
- **Built-in Serial Terminal**:
  You can also use the **SERIAL TERMINAL** tab in the dashboard's right column to send raw firmware commands without opening the Arduino IDE!

---

## 5. Firmware Protection Compliance

This entire SCADA dashboard and communication bridge is isolated strictly inside `ui/`.
Zero firmware files (`src/`, `include/`, `platformio.ini`, `flow_logger.py`, etc.) were modified, refactored, or touched.
