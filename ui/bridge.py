"""
LRC Hardware Controller - Serial WebSocket Bridge & Local Web Server
Binds locally on 127.0.0.1:8080.
Connects browser frontend to ESP32 over USB Serial (115200 baud).
Preserves exclusive serial access: can disconnect anytime to allow Arduino Serial Monitor.
Includes realistic Mock/Simulation mode for testing when no ESP32 is plugged in.
"""

import sys
import os
import time
import json
import asyncio
import threading
import re
from typing import Optional, Set

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
import serial
import serial.tools.list_ports

from contextlib import asynccontextmanager

# Directory paths
UI_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(UI_DIR)

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.event_loop = asyncio.get_running_loop()
    yield

app = FastAPI(title="LRC ESP32 Hardware Bridge", version="1.0.0", lifespan=lifespan)

# Connected WebSocket clients
connected_clients: Set[WebSocket] = set()

# Bridge state
class BridgeState:
    def __init__(self):
        self.serial_port: Optional[str] = None
        self.baud_rate: int = 115200
        self.ser: Optional[serial.Serial] = None
        self.is_connected: bool = False
        self.is_mock: bool = False
        self.mock_thread: Optional[threading.Thread] = None
        self.serial_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        
        # Parsed system state for fast frontend sync (Strict SAFE_IDLE default)
        self.system_on: bool = True
        self.float_triggered: bool = False
        self.solenoid_open: bool = False
        self.pump1_duty: int = 0
        self.pump2_duty: int = 0
        self.pump3_duty: int = 0
        self.case1_state: str = "SAFE_IDLE"
        self.estop_active: bool = False
        self.csv_logging: bool = False
        self.last_flow_lpm: float = 0.0
        self.last_flow_hz: float = 0.0
        self.case2_flushing: bool = False
        self.case2_flush_start: float = 0.0
        self.case2_shutdown: bool = False
        self.case1_transition_start: float = 0.0
        self.case1_transition_active: bool = False

bridge = BridgeState()

# Request schemas
class ConnectRequest(BaseModel):
    port: str
    baud: int = 115200
    mock: bool = False

class CommandRequest(BaseModel):
    command: str

# Broadcast message to all connected WebSocket clients
def broadcast_json(data: dict):
    if not connected_clients:
        return
    msg = json.dumps(data)
    # Schedule coroutine for each websocket in event loop
    loop = getattr(app, "event_loop", None)
    if loop and loop.is_running():
        for ws in list(connected_clients):
            try:
                asyncio.run_coroutine_threadsafe(ws.send_text(msg), loop)
            except Exception:
                pass

# Parse incoming serial lines for structured telemetry
def parse_and_broadcast_line(line: str, is_mock: bool = False):
    clean_line = line.strip()
    if not clean_line:
        return

    now = time.time()
    
    # 1. Check for CSV record: timestamp_ms,pump2_pwm,frequency_hz,estimated_flow_lpm
    # Example: 12345,100,285,2.91
    csv_match = re.match(r"^(\d+),(\d+),([\d\.]+),([\d\.]+)$", clean_line)
    if csv_match:
        ts_ms = int(csv_match.group(1))
        p2_pwm = int(csv_match.group(2))
        freq_hz = float(csv_match.group(3))
        flow_lpm = float(csv_match.group(4))
        
        bridge.last_flow_hz = freq_hz
        bridge.last_flow_lpm = flow_lpm
        bridge.last_reading_time = now
        
        broadcast_json({
            "type": "flow_record",
            "timestamp_ms": ts_ms,
            "pump2_pwm": p2_pwm,
            "frequency_hz": freq_hz,
            "flow_lpm": flow_lpm,
            "arrival_time": now,
            "is_mock": is_mock
        })
        # Also emit raw terminal line
        broadcast_json({
            "type": "raw_serial",
            "line": clean_line,
            "is_csv": True,
            "is_mock": is_mock
        })
        return

    # Broadcast raw serial line
    broadcast_json({
        "type": "raw_serial",
        "line": clean_line,
        "is_csv": False,
        "is_mock": is_mock
    })

    # 2. Check for Heartbeat line
    # [HEARTBEAT] ESP32 Alive | Sys: ON | Solenoid: OPEN | Flow: 0.00 L/min | Float: NORMAL | State: NORMAL | P1: 50% | P2: 100% | P3: 0%
    if "[HEARTBEAT]" in clean_line:
        hb_data = {}
        sys_m = re.search(r"Sys:\s*(\w+)", clean_line)
        if sys_m:
            bridge.system_on = (sys_m.group(1) == "ON")
            hb_data["system_on"] = bridge.system_on
            
        sol_m = re.search(r"Solenoid:\s*(\w+)", clean_line)
        if sol_m:
            bridge.solenoid_open = (sol_m.group(1) == "OPEN")
            hb_data["solenoid_open"] = bridge.solenoid_open
            
        flow_m = re.search(r"Flow:\s*([\d\.]+)", clean_line)
        if flow_m:
            bridge.last_flow_lpm = float(flow_m.group(1))
            hb_data["flow_lpm"] = bridge.last_flow_lpm
            
        float_m = re.search(r"Float:\s*(\w+)", clean_line)
        if float_m:
            bridge.float_triggered = (float_m.group(1) == "TRIGGERED" or float_m.group(1) == "SUMP_HIGH")
            hb_data["float_triggered"] = bridge.float_triggered
            
        state_m = re.search(r"State:\s*([A-Za-z0-9_]+)", clean_line)
        if state_m:
            bridge.case1_state = state_m.group(1)
            hb_data["case1_state"] = bridge.case1_state
            
        p1_m = re.search(r"P1:\s*(\d+)%", clean_line)
        if p1_m:
            bridge.pump1_duty = int(p1_m.group(1))
            hb_data["pump1_duty"] = bridge.pump1_duty
            
        p2_m = re.search(r"P2:\s*(\d+)%", clean_line)
        if p2_m:
            bridge.pump2_duty = int(p2_m.group(1))
            hb_data["pump2_duty"] = bridge.pump2_duty
            
        p3_m = re.search(r"P3:\s*(\d+)%", clean_line)
        if p3_m:
            bridge.pump3_duty = int(p3_m.group(1))
            hb_data["pump3_duty"] = bridge.pump3_duty

        broadcast_json({
            "type": "heartbeat",
            "data": hb_data,
            "is_mock": is_mock
        })
        return

    # 3. Check for Case 2 Flush Sequence Events
    if "[CASE 2] Automatic flush sequence started" in clean_line or "[CASE 2] Physical flush button detected" in clean_line or "Flush timer started:" in clean_line:
        bridge.case2_flushing = True
        bridge.case2_flush_start = now
        bridge.case2_shutdown = False
        bridge.solenoid_open = False
        bridge.pump1_duty = 50
        bridge.pump2_duty = 100
        bridge.pump3_duty = 50
        bridge.case1_state = "CASE2_FLUSHING"
        # Parse duration dynamically if reported in line (e.g. "Flush timer started: 90 seconds")
        duration_s = 90
        dur_match = re.search(r"Flush timer started:\s*(\d+)\s*seconds", clean_line)
        if dur_match:
            try:
                duration_s = int(dur_match.group(1))
            except ValueError:
                duration_s = 90
        broadcast_json({
            "type": "case2_flush_start",
            "duration_s": duration_s,
            "pump1_duty": 50,
            "pump2_duty": 100,
            "pump3_duty": 50,
            "solenoid_open": False,
            "is_mock": is_mock
        })
        return

    if "flush complete" in clean_line.lower() or "System latched in SHUTDOWN" in clean_line:
        bridge.case2_flushing = False
        bridge.case2_shutdown = True
        bridge.pump1_duty = 0
        bridge.pump2_duty = 0
        bridge.pump3_duty = 0
        bridge.solenoid_open = False
        bridge.case1_state = "CASE2_SHUTDOWN"
        broadcast_json({
            "type": "case2_flush_complete",
            "is_mock": is_mock
        })
        return

    # 4. Check for Emergency Stop
    if "E-STOP -> ACTIVE" in clean_line:
        bridge.estop_active = True
        bridge.pump1_duty = 0
        bridge.pump2_duty = 0
        bridge.pump3_duty = 0
        bridge.solenoid_open = False
        bridge.case1_state = "EMERGENCY_STOP"
        broadcast_json({
            "type": "estop_change",
            "active": True,
            "is_mock": is_mock
        })
        return

    if "E-STOP -> CLEARED" in clean_line:
        bridge.estop_active = False
        broadcast_json({
            "type": "estop_change",
            "active": False,
            "is_mock": is_mock
        })
        return

    # 5. Check for State changes
    if "CASE 1 -> SAFE IDLE" in clean_line or "CASE 1 -> SAFE_IDLE" in clean_line or "State:    SAFE_IDLE" in clean_line:
        bridge.case1_state = "SAFE_IDLE"
        bridge.solenoid_open = False
        bridge.pump1_duty = 0
        bridge.pump2_duty = 0
        bridge.pump3_duty = 0
        broadcast_json({
            "type": "state_change",
            "state": "SAFE_IDLE",
            "pump1": 0,
            "pump2": 0,
            "pump3": 0,
            "solenoid": False,
            "float_triggered": bridge.float_triggered,
            "is_mock": is_mock
        })
        return

    if "NORMAL FLOW ->" in clean_line:
        bridge.case1_state = "NORMAL"
        bridge.float_triggered = False
        bridge.solenoid_open = True
        bridge.pump1_duty = 50
        bridge.pump2_duty = 100
        bridge.case2_shutdown = False
        bridge.case2_flushing = False
        broadcast_json({
            "type": "state_change",
            "state": "NORMAL",
            "pump1": 50,
            "pump2": 100,
            "pump3": bridge.pump3_duty,
            "solenoid": True,
            "float_triggered": False,
            "is_mock": is_mock
        })
        broadcast_json({"type": "float_switch", "triggered": False, "is_mock": is_mock})
        return

    if "CASE 1 -> NORMAL" in clean_line:
        bridge.case1_state = "NORMAL"
        bridge.float_triggered = False
        bridge.solenoid_open = True
        bridge.pump1_duty = 50
        bridge.pump2_duty = 100
        bridge.pump3_duty = 0
        bridge.case2_shutdown = False
        bridge.case2_flushing = False
        broadcast_json({
            "type": "state_change",
            "state": "NORMAL",
            "pump1": 50,
            "pump2": 100,
            "pump3": 0,
            "solenoid": True,
            "float_triggered": False,
            "is_mock": is_mock
        })
        broadcast_json({"type": "float_switch", "triggered": False, "is_mock": is_mock})
        return

    if "CASE 1 -> SUMP HIGH" in clean_line:
        bridge.case1_state = "SUMP_HIGH"
        bridge.float_triggered = True
        bridge.pump1_duty = 0
        bridge.pump2_duty = 100
        broadcast_json({
            "type": "state_change",
            "state": "SUMP_HIGH",
            "pump1": 0,
            "pump2": 100,
            "pump3": 0,
            "solenoid": True,
            "float_triggered": True,
            "is_mock": is_mock
        })
        broadcast_json({"type": "float_switch", "triggered": True, "is_mock": is_mock})
        return

    if "CASE 1 -> RETURN TO NORMAL" in clean_line:
        bridge.case1_state = "RETURN_TO_NORMAL"
        bridge.float_triggered = False
        bridge.pump1_duty = 50
        bridge.pump2_duty = 100
        broadcast_json({
            "type": "state_change",
            "state": "RETURN_TO_NORMAL",
            "pump1": 50,
            "pump2": 100,
            "pump3": 0,
            "solenoid": True,
            "float_triggered": False,
            "is_mock": is_mock
        })
        broadcast_json({"type": "float_switch", "triggered": False, "is_mock": is_mock})
        return

    if "SYSTEM -> OFF" in clean_line:
        bridge.system_on = False
        bridge.case1_state = "SYSTEM_OFF"
        bridge.pump1_duty = 0
        bridge.pump2_duty = 0
        bridge.pump3_duty = 0
        bridge.solenoid_open = False
        broadcast_json({"type": "system_switch", "system_on": False, "is_mock": is_mock})
        return

    if "SYSTEM -> ON" in clean_line:
        bridge.system_on = True
        broadcast_json({"type": "system_switch", "system_on": True, "is_mock": is_mock})
        return

    if "FLOAT -> SUMP HIGH" in clean_line:
        bridge.float_triggered = True
        broadcast_json({"type": "float_switch", "triggered": True, "is_mock": is_mock})
        return

    if "FLOAT -> NORMAL" in clean_line:
        bridge.float_triggered = False
        broadcast_json({"type": "float_switch", "triggered": False, "is_mock": is_mock})
        return

    # 6. Check Solenoid messages
    if "[SOLENOID] Opened" in clean_line or "Solenoid: OPEN" in clean_line:
        bridge.solenoid_open = True
        broadcast_json({"type": "solenoid_change", "open": True, "is_mock": is_mock})
        return

    if "[SOLENOID] Closed" in clean_line or "Solenoid: CLOSED" in clean_line:
        bridge.solenoid_open = False
        broadcast_json({"type": "solenoid_change", "open": False, "is_mock": is_mock})
        return

    # 7. Check Flow Logging started/stopped
    if "Flow logging started" in clean_line:
        bridge.csv_logging = True
        broadcast_json({"type": "csv_logging", "active": True, "is_mock": is_mock})
        return

    if "Flow logging stopped" in clean_line:
        bridge.csv_logging = False
        broadcast_json({"type": "csv_logging", "active": False, "is_mock": is_mock})
        return

    # 8. Single flow reading: FLOW -> 2.91 L/min | 285 Hz
    flow_reading_m = re.search(r"FLOW -> ([\d\.]+) L/min \| ([\d\.]+) Hz", clean_line)
    if flow_reading_m:
        fl = float(flow_reading_m.group(1))
        hz = float(flow_reading_m.group(2))
        bridge.last_flow_lpm = fl
        bridge.last_flow_hz = hz
        bridge.last_reading_time = now
        broadcast_json({
            "type": "flow_oneshot",
            "flow_lpm": fl,
            "frequency_hz": hz,
            "is_mock": is_mock
        })
        return

    # 9. Individual Pump Duty and Stop Events (Real & Mock)
    p1_m = re.search(r"\[PUMP 1\] Duty set to (\d+)%", clean_line)
    if p1_m:
        bridge.pump1_duty = int(p1_m.group(1))
        broadcast_json({"type": "pump_update", "pump": 1, "duty": bridge.pump1_duty, "is_mock": is_mock})
        return

    if "[PUMP 1] Driver DISABLED" in clean_line:
        bridge.pump1_duty = 0
        broadcast_json({"type": "pump_update", "pump": 1, "duty": 0, "enabled": False, "is_mock": is_mock})
        return

    p2_m = re.search(r"\[PUMP 2\] Duty set to (\d+)%", clean_line)
    if p2_m:
        bridge.pump2_duty = int(p2_m.group(1))
        broadcast_json({"type": "pump_update", "pump": 2, "duty": bridge.pump2_duty, "is_mock": is_mock})
        return

    if "[PUMP 2] Driver DISABLED" in clean_line:
        bridge.pump2_duty = 0
        broadcast_json({"type": "pump_update", "pump": 2, "duty": 0, "enabled": False, "is_mock": is_mock})
        return

    if "[PUMP 3] Stopped" in clean_line or "[PUMP 3] STOPPED" in clean_line:
        bridge.pump3_duty = 0
        broadcast_json({"type": "pump_update", "pump": 3, "duty": 0, "is_mock": is_mock})
        return

    norm_flow_m = re.search(r"NORMAL FLOW -> Pump 1:\s*(\d+)%\s*\|\s*Pump 2:\s*(\d+)%", clean_line)
    if norm_flow_m:
        bridge.pump1_duty = int(norm_flow_m.group(1))
        bridge.pump2_duty = int(norm_flow_m.group(2))
        broadcast_json({
            "type": "state_change",
            "state": "NORMAL",
            "pump1": bridge.pump1_duty,
            "pump2": bridge.pump2_duty,
            "pump3": 0,
            "solenoid": True,
            "is_mock": is_mock
        })
        return

# Real serial reader thread function
def serial_reader_worker(ser: serial.Serial):
    buffer = ""
    while not bridge.stop_event.is_set():
        try:
            if ser.in_waiting > 0:
                raw_bytes = ser.read(ser.in_waiting)
                text = raw_bytes.decode('utf-8', errors='replace')
                buffer += text
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    parse_and_broadcast_line(line, is_mock=False)
            else:
                time.sleep(0.01)
        except Exception as e:
            if not bridge.stop_event.is_set():
                broadcast_json({"type": "error", "message": f"Serial read error: {str(e)}"})
                disconnect_serial()
            break

# Mock ESP32 simulation thread function
def mock_esp32_worker():
    # Send mock startup lines
    startup_lines = [
        "--- LRC ESP32 Hardware Controller ---",
        "Outputs: Active (SIMULATION)",
        "[PUMP 1] Initialized (GPIO 32/33/13/26, 5000Hz).",
        "[PUMP 2] Initialized (GPIO 18/19/16/17, 5000Hz).",
        "[PUMP 3] Initialized (GPIO 23/25/21/22, 5000Hz).",
        "[SYSTEM] Initialized (Software control).",
        "[SYSTEM] State: SYSTEM ON",
        "[FLOAT_SWITCH] Initialized (GPIO 35).",
        "[FLOAT_SWITCH] State: NORMAL",
        "[FLOW_SENSOR] Initialized (GPIO 14, YF-S401).",
        "[FLUSH_BUTTON] Initialized (GPIO 34, external 10k pull-up).",
        "[SOLENOID] Initialized (GPIO 27, CLOSED).",
        "[CASE1] Initialized in SAFE_IDLE (Pumps: OFF, Solenoid: CLOSED).",
        "Initial State: SYSTEM -> ON | FLOAT -> NORMAL | SOLENOID -> CLOSED | CASE 1 -> SAFE_IDLE"
    ]
    for line in startup_lines:
        parse_and_broadcast_line(line, is_mock=True)
        time.sleep(0.01)

    last_heartbeat = time.time()
    last_csv = time.time()
    mock_start_ms = int(time.time() * 1000)

    # Initial mock states (Strict SAFE_IDLE)
    bridge.system_on = True
    bridge.float_triggered = False
    bridge.solenoid_open = False
    bridge.pump1_duty = 0
    bridge.pump2_duty = 0
    bridge.pump3_duty = 0
    bridge.case1_state = "SAFE_IDLE"
    bridge.csv_logging = True  # Start CSV stream so user immediately sees live flow graph and table!

    parse_and_broadcast_line("\n[LOG] Flow logging started", is_mock=True)
    parse_and_broadcast_line("timestamp_ms,pump2_pwm,frequency_hz,estimated_flow_lpm", is_mock=True)

    while not bridge.stop_event.is_set():
        now = time.time()
        now_ms = int(now * 1000) - mock_start_ms

        # Check Return-to-Normal 10-second transition timing in mock
        if bridge.case1_state == "RETURN_TO_NORMAL" and bridge.case1_transition_active:
            if now - bridge.case1_transition_start >= 10.0:
                bridge.case1_transition_active = False
                bridge.case2_flushing = True
                bridge.case2_flush_start = now
                bridge.case2_shutdown = False
                bridge.solenoid_open = False
                bridge.pump1_duty = 50
                bridge.pump2_duty = 100
                bridge.pump3_duty = 50
                bridge.case1_state = "CASE2_FLUSHING"
                parse_and_broadcast_line("\n[AUTO-SEQUENCE] 10-second return delay completed.", is_mock=True)
                parse_and_broadcast_line("[CASE 2] Automatic flush sequence started.", is_mock=True)
                parse_and_broadcast_line("[CASE 2] Solenoid CLOSED (Isolating 10L process tank).", is_mock=True)
                parse_and_broadcast_line("[CASE 2] PUMP 3 STARTED at 50% duty.", is_mock=True)
                parse_and_broadcast_line("[CASE 2] All three pumps running (P1: 50%, P2: 100%, P3: 50%). Flush timer started: 90 seconds.", is_mock=True)

        # Check Case 2 flush timing in mock
        if bridge.case2_flushing:
            elapsed = now - bridge.case2_flush_start
            if elapsed >= 90.0:
                bridge.case2_flushing = False
                bridge.case2_shutdown = True
                bridge.pump1_duty = 0
                bridge.pump2_duty = 0
                bridge.pump3_duty = 0
                bridge.solenoid_open = False
                bridge.case1_state = "CASE2_SHUTDOWN"
                parse_and_broadcast_line("\n[CASE 2] 90-second flush complete.", is_mock=True)
                parse_and_broadcast_line("[CASE 2] All pumps STOPPED.", is_mock=True)
                parse_and_broadcast_line("[CASE 2] Solenoid remains CLOSED. System latched in SHUTDOWN.", is_mock=True)

        # Periodic CSV logging every 2.5s
        if bridge.csv_logging and (now - last_csv >= 2.5):
            last_csv = now
            # Realistic flow calculation based on Pump 2 duty
            if bridge.pump2_duty > 0 and bridge.system_on and not bridge.estop_active and not bridge.case2_shutdown:
                # 100% duty -> ~5.7 L/min -> ~558 Hz with minor noise
                base_flow = (bridge.pump2_duty / 100.0) * 5.7
                import random
                noise = random.uniform(-0.06, 0.06)
                flow_lpm = max(0.0, round(base_flow + noise, 2))
                freq_hz = round(flow_lpm * 98.0, 1)
            else:
                flow_lpm = 0.0
                freq_hz = 0.0

            p2_pwm = bridge.pump2_duty if bridge.system_on and not bridge.estop_active else 0
            csv_line = f"{now_ms},{p2_pwm},{freq_hz:.1f},{flow_lpm:.2f}"
            parse_and_broadcast_line(csv_line, is_mock=True)

        # Periodic Heartbeat every 15s (if CSV logging is not active)
        if not bridge.csv_logging and (now - last_heartbeat >= 15.0):
            last_heartbeat = now
            hb_line = (f"[HEARTBEAT] ESP32 Alive | Sys: {'ON' if bridge.system_on else 'OFF'} | "
                       f"Solenoid: {'OPEN' if bridge.solenoid_open else 'CLOSED'} | "
                       f"Flow: {bridge.last_flow_lpm:.2f} L/min | "
                       f"Float: {'TRIGGERED' if bridge.float_triggered else 'NORMAL'} | "
                       f"State: {bridge.case1_state} | "
                       f"P1: {bridge.pump1_duty}% | P2: {bridge.pump2_duty}% | P3: {bridge.pump3_duty}%")
            parse_and_broadcast_line(hb_line, is_mock=True)

        time.sleep(0.05)

def mock_handle_command(cmd: str):
    """Accurately mimics the existing firmware's main.cpp command parser"""
    if not cmd:
        return
    clean = str(cmd).strip().strip("'\"").strip()
    if not clean:
        return

    # Check E-Stop: 's', 'S', or space
    if clean in ['s', 'S', ' ']:
        bridge.estop_active = True
        bridge.pump1_duty = 0
        bridge.pump2_duty = 0
        bridge.pump3_duty = 0
        bridge.solenoid_open = False
        bridge.case1_state = "EMERGENCY_STOP"
        parse_and_broadcast_line("\nE-STOP -> ACTIVE (All 3 Pumps Halted, Solenoid Closed)", is_mock=True)
        return

    # Query Status: 'p'
    if clean in ['p', 'P']:
        status_dump = [
            "--- System Status ---",
            f"  State:    {bridge.case1_state}",
            f"  E-Stop:   {'ACTIVE' if bridge.estop_active else 'CLEARED'}",
            f"  Pump 1:   {bridge.pump1_duty}%",
            f"  Pump 2:   {bridge.pump2_duty}%",
            f"  Pump 3:   {bridge.pump3_duty}%",
            "--- System Enable (Software Control) ---",
            f"  State: {'SYSTEM ON' if bridge.system_on else 'SYSTEM OFF'}",
            "--- Float Switch (GPIO 35) ---",
            f"  State: {'SUMP HIGH' if bridge.float_triggered else 'NORMAL'}",
            "--- Flow Sensor (GPIO 14) ---",
            f"  Frequency: {bridge.last_flow_hz:.2f} Hz",
            f"  Flow Rate: {bridge.last_flow_lpm:.3f} L/min",
            "--- Solenoid Valve (GPIO 27) ---",
            f"  State:    {'OPEN' if bridge.solenoid_open else 'CLOSED'}",
            "--- Pump 1 (U2) ---",
            f"  Duty:      {bridge.pump1_duty}%",
            "--- Pump 2 (U3) ---",
            f"  Duty:      {bridge.pump2_duty}%",
            "--- Pump 3 (U4) ---",
            f"  Duty:      {bridge.pump3_duty}%",
            "--- Flush Button (GPIO 34) ---",
            f"  State: {'PRESSED' if bridge.case2_flushing else 'RELEASED'}"
        ]
        for l in status_dump:
            parse_and_broadcast_line(l, is_mock=True)
        return

    # System switch query: 'y'
    if clean in ['y', 'Y']:
        parse_and_broadcast_line(f"SYSTEM -> {'ON' if bridge.system_on else 'OFF'}", is_mock=True)
        return

    # Mock system switch toggle: '!sys_off', '!sys_on'
    if clean in ['!sys_off', '!switch_off']:
        bridge.system_on = False
        bridge.case1_state = "SYSTEM_OFF"
        bridge.pump1_duty = 0
        bridge.pump2_duty = 0
        bridge.pump3_duty = 0
        bridge.solenoid_open = False
        parse_and_broadcast_line("\nSYSTEM -> OFF", is_mock=True)
        parse_and_broadcast_line("CASE 1 -> SYSTEM OFF", is_mock=True)
        parse_and_broadcast_line("P1: 0% | P2: 0% | P3: 0% | Solenoid: CLOSED", is_mock=True)
        return

    if clean in ['!sys_on', '!switch_on']:
        bridge.system_on = True
        bridge.case1_state = "SAFE_IDLE"
        bridge.pump1_duty = 0
        bridge.pump2_duty = 0
        bridge.pump3_duty = 0
        bridge.solenoid_open = False
        parse_and_broadcast_line("\nSYSTEM -> ON", is_mock=True)
        parse_and_broadcast_line("CASE 1 -> SAFE IDLE", is_mock=True)
        parse_and_broadcast_line("P1: 0% | P2: 0% | P3: 0% | Solenoid: CLOSED", is_mock=True)
        return

    # Float switch query: 't'
    if clean == 't':
        parse_and_broadcast_line(f"FLOAT -> {'SUMP HIGH' if bridge.float_triggered else 'NORMAL'}", is_mock=True)
        return

    # One-shot flow query: 'l'
    if clean == 'l':
        parse_and_broadcast_line(f"FLOW -> {bridge.last_flow_lpm:.2f} L/min | {bridge.last_flow_hz:.0f} Hz", is_mock=True)
        return

    # Toggle CSV log: 'L'
    if clean == 'L':
        bridge.csv_logging = not bridge.csv_logging
        if bridge.csv_logging:
            parse_and_broadcast_line("\n[LOG] Flow logging started", is_mock=True)
            parse_and_broadcast_line("timestamp_ms,pump2_pwm,frequency_hz,estimated_flow_lpm", is_mock=True)
        else:
            parse_and_broadcast_line("[LOG] Flow logging stopped\n", is_mock=True)
        return

    # Solenoid open: 'a'
    if clean in ['a', 'A']:
        if bridge.estop_active:
            parse_and_broadcast_line("[SAFETY] Blocked: Cannot open solenoid while Emergency Stop is active.", is_mock=True)
            return
        if not bridge.system_on:
            parse_and_broadcast_line("[SAFETY] Blocked: Cannot open solenoid while System Switch is OFF.", is_mock=True)
            return
        bridge.solenoid_open = True
        parse_and_broadcast_line("[SOLENOID] Opened (GPIO 27 HIGH).", is_mock=True)
        return

    # Solenoid close: 'c'
    if clean in ['c', 'C']:
        bridge.solenoid_open = False
        parse_and_broadcast_line("[SOLENOID] Closed (GPIO 27 LOW).", is_mock=True)
        return

    # Solenoid toggle: 'k'
    if clean in ['k', 'K']:
        if not bridge.solenoid_open:
            if bridge.estop_active or not bridge.system_on:
                parse_and_broadcast_line("[SAFETY] Blocked: Solenoid open inhibited.", is_mock=True)
                return
            bridge.solenoid_open = True
            parse_and_broadcast_line("[SOLENOID] Opened (GPIO 27 HIGH).", is_mock=True)
        else:
            bridge.solenoid_open = False
            parse_and_broadcast_line("[SOLENOID] Closed (GPIO 27 LOW).", is_mock=True)
        return

    # Normal Flow: 'N'
    if clean == 'N':
        if bridge.estop_active or not bridge.system_on or bridge.case2_flushing or bridge.case2_shutdown:
            parse_and_broadcast_line("[SAFETY] Blocked: Cannot start Normal Flow.", is_mock=True)
            return
        bridge.solenoid_open = True
        bridge.case2_shutdown = False
        bridge.case2_flushing = False
        if bridge.float_triggered:
            bridge.case1_state = "SUMP_HIGH"
            bridge.pump1_duty = 0
            bridge.pump2_duty = 100
            bridge.pump3_duty = 0
            parse_and_broadcast_line("\nCASE 1 -> SUMP HIGH", is_mock=True)
            parse_and_broadcast_line(f"NORMAL FLOW -> Pump 1: 0% | Pump 2: {bridge.pump2_duty}% | Solenoid: OPEN (Sump High)", is_mock=True)
        else:
            bridge.case1_state = "NORMAL"
            bridge.pump1_duty = 50
            bridge.pump2_duty = 100
            bridge.pump3_duty = 0
            parse_and_broadcast_line("\nCASE 1 -> NORMAL", is_mock=True)
            parse_and_broadcast_line(f"NORMAL FLOW -> Pump 1: {bridge.pump1_duty}% | Pump 2: {bridge.pump2_duty}% | Solenoid: OPEN", is_mock=True)
        return

    # Case 1 Simulation Normal: 'n'
    if clean == 'n':
        if bridge.estop_active:
            bridge.estop_active = False
            parse_and_broadcast_line("\nE-STOP -> CLEARED", is_mock=True)
        bridge.case1_state = "NORMAL"
        bridge.float_triggered = False
        bridge.pump1_duty = 50
        bridge.pump2_duty = 100
        bridge.pump3_duty = 0
        bridge.solenoid_open = True
        parse_and_broadcast_line("\nCASE 1 -> NORMAL", is_mock=True)
        parse_and_broadcast_line(f"P1: {bridge.pump1_duty}% | P2: {bridge.pump2_duty}% | P3: 0% | Solenoid: OPEN", is_mock=True)
        return

    # Case 1 Simulation Sump High: 'x'
    if clean in ['x', 'X']:
        bridge.case1_transition_active = False
        bridge.case1_state = "SUMP_HIGH"
        bridge.float_triggered = True
        bridge.pump1_duty = 0
        bridge.pump2_duty = 100
        bridge.pump3_duty = 0
        bridge.solenoid_open = True
        parse_and_broadcast_line("\nCASE 1 -> SUMP HIGH", is_mock=True)
        parse_and_broadcast_line(f"P1: 0% | P2: {bridge.pump2_duty}% | P3: 0% | Solenoid: OPEN", is_mock=True)
        return

    # Case 1 Simulation Return to Normal: 'r'
    if clean in ['r', 'R']:
        bridge.case1_state = "RETURN_TO_NORMAL"
        bridge.float_triggered = False
        bridge.pump1_duty = 50
        bridge.pump2_duty = 100
        bridge.pump3_duty = 0
        bridge.solenoid_open = True
        bridge.case1_transition_start = time.time()
        bridge.case1_transition_active = True
        parse_and_broadcast_line("\nCASE 1 -> RETURN TO NORMAL", is_mock=True)
        parse_and_broadcast_line(f"P1: {bridge.pump1_duty}% | P2: {bridge.pump2_duty}% | P3: 0% | Solenoid: OPEN", is_mock=True)
        parse_and_broadcast_line("[AUTO-SEQUENCE] 10-second delay started. Flush starts automatically.", is_mock=True)
        return

    # Pump 3 manual start: 'u' -> Reject per firmware
    if clean in ['u', 'U']:
        parse_and_broadcast_line("\n[PUMP 3] Manual start requested.", is_mock=True)
        parse_and_broadcast_line("[PUMP 3] Start rejected: flush line valve has no sensor.", is_mock=True)
        parse_and_broadcast_line("[PUMP 3] Use physical start button (GPIO 34) to start automatic sequence.", is_mock=True)
        return

    # Pump 3 manual stop: 'i'
    if clean in ['i', 'I']:
        if bridge.case2_flushing:
            parse_and_broadcast_line("\n[PUMP 3] Stop rejected: Case 2 flush active (use E-Stop to halt).", is_mock=True)
        else:
            bridge.pump3_duty = 0
            parse_and_broadcast_line("\n[PUMP 3] Stopped by serial command.", is_mock=True)
        return

    # Trigger mock physical start button: '!start_btn' (or '!flush_btn' for compat)
    if clean in ['!start_btn', '!flush_btn']:
        if bridge.estop_active or not bridge.system_on:
            parse_and_broadcast_line("\n[START] Blocked: Emergency Stop or System OFF.", is_mock=True)
            return
        if bridge.case1_state in ["NORMAL", "SUMP_HIGH", "RETURN_TO_NORMAL"]:
            parse_and_broadcast_line("\n[START] Ignored: Automatic sequence is already running.", is_mock=True)
            return
        if bridge.case2_flushing:
            parse_and_broadcast_line("\n[START] Ignored: Case 2 flush is already active.", is_mock=True)
            return
        if bridge.case2_shutdown:
            parse_and_broadcast_line("\n[START] Ignored: System latched in final shutdown. Reset system to re-arm.", is_mock=True)
            return

        bridge.case2_shutdown = False
        bridge.case2_flushing = False
        bridge.solenoid_open = True
        if bridge.float_triggered:
            bridge.case1_state = "SUMP_HIGH"
            bridge.pump1_duty = 0
            bridge.pump2_duty = 100
            bridge.pump3_duty = 0
            parse_and_broadcast_line("\n[START] Physical start button detected: Starting automatic Case 1 -> Case 2 sequence.", is_mock=True)
            parse_and_broadcast_line("CASE 1 -> SUMP HIGH", is_mock=True)
            parse_and_broadcast_line("NORMAL FLOW -> Pump 1: 0% | Pump 2: 100% | Solenoid: OPEN (Sump High)", is_mock=True)
        else:
            bridge.case1_state = "NORMAL"
            bridge.pump1_duty = 50
            bridge.pump2_duty = 100
            bridge.pump3_duty = 0
            parse_and_broadcast_line("\n[START] Physical start button detected: Starting automatic Case 1 -> Case 2 sequence.", is_mock=True)
            parse_and_broadcast_line("CASE 1 -> NORMAL", is_mock=True)
            parse_and_broadcast_line("NORMAL FLOW -> Pump 1: 50% | Pump 2: 100% | Solenoid: OPEN", is_mock=True)
        return

    # Fast-forward mock timer for testing: '!advance_time <seconds>'
    if clean.startswith('!advance_time '):
        try:
            secs = float(clean.split()[1])
            if bridge.case2_flushing:
                bridge.case2_flush_start -= secs
            if bridge.case1_state == "RETURN_TO_NORMAL" and bridge.case1_transition_active:
                bridge.case1_transition_start -= secs
        except Exception:
            pass
        return

    # Help: 'h'
    if clean in ['h', 'H', '?']:
        help_text = [
            "\n----------------- COMMAND MENU -----------------",
            "Auto Sequence: Start Button (GPIO 34) starts Case 1 -> Case 2",
            "               Case 1: Normal recirculation (P1 50%, P2 100%, Solenoid OPEN)",
            "               Sump High: P1 halts (0%), P2 continues 100%",
            "               Return Normal: 10s delay then Case 2 auto-starts",
            "               Case 2: 90s flush (P1 50%, P2 100%, P3 50%, Solenoid CLOSED)",
            "               Final: 90s timeout -> latched shutdown (all motors OFF)",
            "System:      s/[Space]=E-Stop | p=Status | h=Help",
            "P1 (U2):     1=25% 2=50% 3=75% 4=100% 0=Stop | e=Enable d=Disable",
            "             d1 <0-100> in 5% steps (e.g. d1 50)",
            "P2 (U3):     5=25% 6=50% 7=75% 8=100% 9=Stop | q=Enable w=Disable",
            "             d<0-100> in 5% steps (e.g. d5, d10, d50, d100) | d2 <0-100>",
            "             f=Fwd v=Rev o=P2 Status",
            "P3 (U4):     u=Start Req (Rejected: Unsafe) | i=Stop",
            "Solenoid:    a=Open c=Close k=Toggle",
            "Sensors:     y=System State | t=Float Switch | l=Flow Rate | L=CSV Log",
            "Manual Flow: N=Manual Start Case 1 (Commissioning)",
            "Case 1 Sim:  n=Normal x=Sump High r=Return to Normal (Auto Case 2 in 10s)",
            "Commission:  T/m=Enter Commissioning Mode",
            "------------------------------------------------\n"
        ]
        for l in help_text:
            parse_and_broadcast_line(l, is_mock=True)
        return

    # Pump 1 overrides: 0, 1, 2, 3, 4, e, d
    if clean in ['0', '1', '2', '3', '4']:
        d_map = {'0': 0, '1': 25, '2': 50, '3': 75, '4': 100}
        bridge.pump1_duty = d_map[clean]
        parse_and_broadcast_line(f"[PUMP 1] Duty set to {bridge.pump1_duty}%.", is_mock=True)
        return
    if clean in ['e', 'E']:
        parse_and_broadcast_line("[PUMP 1] Driver ENABLED.", is_mock=True)
        return
    if clean in ['d', 'D']:
        bridge.pump1_duty = 0
        parse_and_broadcast_line("[PUMP 1] Driver DISABLED.", is_mock=True)
        return

    # Pump 2 overrides: 5, 6, 7, 8, 9, q, w
    if clean in ['5', '6', '7', '8', '9']:
        d_map = {'5': 25, '6': 50, '7': 75, '8': 100, '9': 0}
        bridge.pump2_duty = d_map[clean]
        parse_and_broadcast_line(f"[PUMP 2] Duty set to {bridge.pump2_duty}%.", is_mock=True)
        return
    if clean in ['q', 'Q']:
        parse_and_broadcast_line("[PUMP 2] Driver ENABLED.", is_mock=True)
        return
    if clean in ['w', 'W']:
        bridge.pump2_duty = 0
        parse_and_broadcast_line("[PUMP 2] Driver DISABLED.", is_mock=True)
        return

    # Duty commands d<0-100>
    d_match = re.match(r"^d(?:([12])\s*)?(\d+)$", clean, re.IGNORECASE)
    if d_match:
        target = int(d_match.group(1)) if d_match.group(1) else 2
        val = int(d_match.group(2))
        if 0 <= val <= 100 and val % 5 == 0:
            if target == 1:
                bridge.pump1_duty = val
                parse_and_broadcast_line(f"[PUMP 1] Duty set to {val}%.", is_mock=True)
            else:
                bridge.pump2_duty = val
                parse_and_broadcast_line(f"[PUMP 2] Duty set to {val}%.", is_mock=True)
            return
        else:
            parse_and_broadcast_line(f"[CMD] Invalid duty {val}. Must be 0-100 in 5% steps.", is_mock=True)
            return

    # Fallback unknown
    parse_and_broadcast_line(f"[CMD] Unknown command: '{clean}'. Send 'h' for help.", is_mock=True)

def disconnect_serial():
    with bridge.lock:
        bridge.stop_event.set()
        if bridge.ser:
            try:
                bridge.ser.close()
            except Exception:
                pass
            bridge.ser = None
        bridge.is_connected = False
        bridge.is_mock = False
        bridge.serial_port = None
        broadcast_json({"type": "connection_status", "connected": False, "port": None, "is_mock": False})
        broadcast_json({
            "type": "initial_state",
            "connected": False,
            "is_mock": False,
            "port": None,
            "baud": 115200,
            "system_on": False,
            "float_triggered": False,
            "solenoid_open": False,
            "pump1_duty": 0,
            "pump2_duty": 0,
            "pump3_duty": 0,
            "case1_state": "DISCONNECTED",
            "estop_active": False,
            "csv_logging": False,
            "last_flow_lpm": 0.0,
            "last_flow_hz": 0.0,
            "case2_flushing": False,
            "case2_shutdown": False
        })

@app.get("/api/ports")
def list_ports():
    ports = []
    try:
        com_list = list(serial.tools.list_ports.comports())
        for p in com_list:
            ports.append({
                "device": p.device,
                "description": p.description,
                "hwid": p.hwid
            })
    except Exception as e:
        pass
    return {"ports": ports}

@app.post("/api/connect")
def connect_port(req: ConnectRequest):
    disconnect_serial()
    time.sleep(0.1)
    
    with bridge.lock:
        bridge.stop_event.clear()
        if req.mock or req.port.upper() == "MOCK":
            bridge.is_mock = True
            bridge.is_connected = True
            bridge.serial_port = "MOCK_ESP32"
            bridge.case2_shutdown = False
            bridge.case2_flushing = False
            bridge.estop_active = False
            bridge.system_on = True
            bridge.solenoid_open = False
            bridge.pump1_duty = 0
            bridge.pump2_duty = 0
            bridge.pump3_duty = 0
            bridge.case1_state = "SAFE_IDLE"
            bridge.mock_thread = threading.Thread(target=mock_esp32_worker, daemon=True)
            bridge.mock_thread.start()
            broadcast_json({"type": "connection_status", "connected": True, "port": "MOCK_ESP32", "is_mock": True})
            broadcast_json({
                "type": "initial_state",
                "connected": True,
                "is_mock": True,
                "port": "MOCK_ESP32",
                "baud": 115200,
                "system_on": bridge.system_on,
                "float_triggered": bridge.float_triggered,
                "solenoid_open": bridge.solenoid_open,
                "pump1_duty": bridge.pump1_duty,
                "pump2_duty": bridge.pump2_duty,
                "pump3_duty": bridge.pump3_duty,
                "case1_state": bridge.case1_state,
                "estop_active": bridge.estop_active,
                "csv_logging": bridge.csv_logging,
                "last_flow_lpm": bridge.last_flow_lpm,
                "last_flow_hz": bridge.last_flow_hz,
                "case2_flushing": bridge.case2_flushing,
                "case2_shutdown": bridge.case2_shutdown
            })
            return {"status": "connected", "port": "MOCK_ESP32", "is_mock": True}
        
        try:
            ser = serial.Serial(
                port=req.port,
                baudrate=req.baud,
                timeout=0.1,
                write_timeout=0.5
            )
            bridge.ser = ser
            bridge.serial_port = req.port
            bridge.baud_rate = req.baud
            bridge.is_connected = True
            bridge.is_mock = False
            bridge.serial_thread = threading.Thread(target=serial_reader_worker, args=(ser,), daemon=True)
            bridge.serial_thread.start()
            broadcast_json({"type": "connection_status", "connected": True, "port": req.port, "is_mock": False})
            broadcast_json({
                "type": "initial_state",
                "connected": True,
                "is_mock": False,
                "port": req.port,
                "baud": req.baud,
                "system_on": bridge.system_on,
                "float_triggered": bridge.float_triggered,
                "solenoid_open": bridge.solenoid_open,
                "pump1_duty": bridge.pump1_duty,
                "pump2_duty": bridge.pump2_duty,
                "pump3_duty": bridge.pump3_duty,
                "case1_state": bridge.case1_state,
                "estop_active": bridge.estop_active,
                "csv_logging": bridge.csv_logging,
                "last_flow_lpm": bridge.last_flow_lpm,
                "last_flow_hz": bridge.last_flow_hz,
                "case2_flushing": bridge.case2_flushing,
                "case2_shutdown": bridge.case2_shutdown
            })
            return {"status": "connected", "port": req.port, "is_mock": False}
        except Exception as e:
            bridge.is_connected = False
            bridge.is_mock = False
            return JSONResponse(status_code=400, content={"status": "error", "message": f"Failed to open {req.port}: {str(e)}"})

@app.post("/api/disconnect")
def disconnect_port():
    disconnect_serial()
    return {"status": "disconnected"}

@app.get("/api/status")
def get_status():
    return {
        "connected": bridge.is_connected,
        "is_mock": bridge.is_mock,
        "port": bridge.serial_port,
        "baud": bridge.baud_rate,
        "system_on": bridge.system_on,
        "float_triggered": bridge.float_triggered,
        "solenoid_open": bridge.solenoid_open,
        "pump1_duty": bridge.pump1_duty,
        "pump2_duty": bridge.pump2_duty,
        "pump3_duty": bridge.pump3_duty,
        "case1_state": bridge.case1_state,
        "estop_active": bridge.estop_active,
        "csv_logging": bridge.csv_logging,
        "last_flow_lpm": bridge.last_flow_lpm,
        "last_flow_hz": bridge.last_flow_hz,
        "case2_flushing": bridge.case2_flushing,
        "case2_shutdown": bridge.case2_shutdown
    }

@app.post("/api/send")
def send_command(req: CommandRequest):
    if not bridge.is_connected:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Not connected to ESP32 or Mock"})

    cmd_str = str(req.command).strip().strip("'\"").strip()
    if not cmd_str:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Command cannot be empty"})

    if bridge.is_mock:
        mock_handle_command(cmd_str)
        return {"status": "sent", "command": cmd_str, "is_mock": True}

    if bridge.ser and bridge.ser.is_open:
        try:
            # Send command directly with newline if multi-char or if single command
            to_send = (cmd_str + "\n").encode('utf-8')
            bridge.ser.write(to_send)
            bridge.ser.flush()
            return {"status": "sent", "command": cmd_str, "is_mock": False}
        except Exception as e:
            return JSONResponse(status_code=500, content={"status": "error", "message": f"Write failed: {str(e)}"})

    return JSONResponse(status_code=400, content={"status": "error", "message": "Serial port not open"})

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    # Send current state snapshot immediately on connection
    init_state = {
        "type": "initial_state",
        "connected": bridge.is_connected,
        "is_mock": bridge.is_mock,
        "port": bridge.serial_port,
        "system_on": bridge.system_on,
        "float_triggered": bridge.float_triggered,
        "solenoid_open": bridge.solenoid_open,
        "pump1_duty": bridge.pump1_duty,
        "pump2_duty": bridge.pump2_duty,
        "pump3_duty": bridge.pump3_duty,
        "case1_state": bridge.case1_state,
        "estop_active": bridge.estop_active,
        "csv_logging": bridge.csv_logging,
        "last_flow_lpm": bridge.last_flow_lpm,
        "last_flow_hz": bridge.last_flow_hz,
        "case2_flushing": bridge.case2_flushing,
        "case2_shutdown": bridge.case2_shutdown
    }
    await websocket.send_text(json.dumps(init_state))
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                action = payload.get("action")
                if action == "send_command":
                    cmd = payload.get("command", "")
                    clean_cmd = str(cmd).strip().strip("'\"").strip()
                    if not clean_cmd:
                        continue
                    if bridge.is_mock:
                        mock_handle_command(clean_cmd)
                    elif bridge.ser and bridge.ser.is_open:
                        to_send = (clean_cmd + "\n").encode('utf-8')
                        bridge.ser.write(to_send)
                        bridge.ser.flush()
                elif action == "connect":
                    port = payload.get("port")
                    baud = payload.get("baud", 115200)
                    mock = payload.get("mock", False)
                    connect_port(ConnectRequest(port=port, baud=baud, mock=mock))
                elif action == "disconnect":
                    disconnect_serial()
            except Exception as e:
                pass
    except WebSocketDisconnect:
        connected_clients.discard(websocket)
    except Exception:
        connected_clients.discard(websocket)

# Serve static frontend files
app.mount("/static", StaticFiles(directory=UI_DIR), name="static")

@app.get("/")
def get_index():
    return FileResponse(os.path.join(UI_DIR, "index.html"))



if __name__ == "__main__":
    print("\n" + "="*60)
    print("  LRC ESP32 Liquid-Handling System - Local SCADA Bridge")
    print("  Serving Dashboard at: http://127.0.0.1:8080")
    print("  Baud Rate: 115200 (Default for LRC ESP32 Firmware)")
    print("  Press Ctrl+C to stop bridge server")
    print("="*60 + "\n")
    uvicorn.run(app, host="127.0.0.1", port=8080, log_level="warning")
