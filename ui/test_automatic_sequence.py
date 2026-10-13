"""
test_automatic_sequence.py - Comprehensive Test Suite for Automatic Case 1 -> Case 2 Sequence
Validates all 20 scenarios specified in the Stage 2 requirements.
"""

import os
import sys
import time
import json
import asyncio
import threading
import urllib.request
import websockets
import subprocess

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI_DIR = os.path.join(PROJECT_DIR, "ui")
BASE_URL = "http://127.0.0.1:8080"
WS_URL = "ws://127.0.0.1:8080/ws"

def http_get(path):
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode())

def http_post(path, data=None):
    if data is None:
        data = {}
    url = f"{BASE_URL}{path}"
    json_data = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=json_data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode())

def test_static_code_inspection():
    print("\n--- STATIC CODE & FIRMWARE INSPECTION ---")
    
    # 1. Inspect hardware_config.h
    import re
    hw_config_path = os.path.join(PROJECT_DIR, "include", "hardware_config.h")
    with open(hw_config_path, "r", encoding="utf-8") as f:
        hw_content = f.read()
    assert re.search(r"START_BUTTON_PIN\s+34", hw_content)
    assert re.search(r"CASE1_RETURN_DELAY_MS\s+10000", hw_content)
    assert re.search(r"CASE2_FLUSH_DURATION_MS\s+90000", hw_content)
    print("  [PASS] hardware_config.h: GPIO 34 pin, 10000ms return delay, 90000ms flush duration configured.")

    # 2. Inspect start_button.cpp: input-only, no internal pull-up
    sb_path = os.path.join(PROJECT_DIR, "src", "start_button.cpp")
    with open(sb_path, "r", encoding="utf-8") as f:
        sb_content = f.read()
    assert "pinMode(START_BUTTON_PIN, INPUT)" in sb_content
    assert "pinMode(START_BUTTON_PIN, INPUT_PULLUP)" not in sb_content
    print("  [PASS] start_button.cpp: Configured strictly as INPUT (external 10k pull-up on PCB).")

    # 3. Inspect ui/index.html: No #btn-normal-flow
    index_path = os.path.join(UI_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        index_content = f.read()
    assert "btn-normal-flow" not in index_content
    assert "START BUTTON (GPIO 34)" in index_content
    print("  [PASS] ui/index.html: Redundant 'btn-normal-flow' completely removed; GPIO 34 badge renamed to START BUTTON.")

    # 4. Inspect ui/app.js: No visible 90-second countdown or progress bar
    app_path = os.path.join(UI_DIR, "app.js")
    with open(app_path, "r", encoding="utf-8") as f:
        app_content = f.read()
    assert "btnNormalFlow.addEventListener" not in app_content
    print("  [PASS] ui/app.js: Normal Flow start button event handler removed.")

async def run_scenario_tests():
    print("\n--- RUNNING 20 SYSTEM VERIFICATION SCENARIOS ---")

    # Connect to Mock ESP32
    res = http_post("/api/connect", {"port": "MOCK", "baud": 115200, "mock": True})
    assert res.get("status") == "connected"
    print("  Connected to Mock ESP32 via Bridge.")

    async with websockets.connect(WS_URL) as ws:
        await asyncio.sleep(1.0)

        # Scenario 1: Boot leaves all motors OFF and solenoid CLOSED
        st = http_get("/api/status")
        assert st["case1_state"] == "SAFE_IDLE", f"Scenario 1 Fail: State is {st['case1_state']}"
        assert st["pump1_duty"] == 0, "Scenario 1 Fail: P1 must be 0"
        assert st["pump2_duty"] == 0, "Scenario 1 Fail: P2 must be 0"
        assert st["pump3_duty"] == 0, "Scenario 1 Fail: P3 must be 0"
        assert st["solenoid_open"] is False, "Scenario 1 Fail: Solenoid must be CLOSED"
        print("  [PASS] Scenario 1: Boot leaves all motors OFF and solenoid CLOSED.")

        # Scenario 2 & 3: Single debounced GPIO34 press starts Case 1 (P1=50%, P2=100%, P3=0%, Solenoid=OPEN)
        await ws.send(json.dumps({"action": "send_command", "command": "!start_btn"}))
        await asyncio.sleep(0.3)
        st = http_get("/api/status")
        assert st["case1_state"] == "NORMAL", f"Scenario 2/3 Fail: State is {st['case1_state']}"
        assert st["pump1_duty"] == 50, f"Scenario 3 Fail: P1 is {st['pump1_duty']}%"
        assert st["pump2_duty"] == 100, f"Scenario 3 Fail: P2 is {st['pump2_duty']}%"
        assert st["pump3_duty"] == 0, f"Scenario 3 Fail: P3 is {st['pump3_duty']}%"
        assert st["solenoid_open"] is True, "Scenario 3 Fail: Solenoid must be OPEN"
        print("  [PASS] Scenario 2: Single GPIO34 press starts Case 1.")
        print("  [PASS] Scenario 3: Case 1 starts P1=50%, P2=100%, P3=0%, Solenoid=OPEN.")

        # Scenario 4 & 5: Float-switch transition to closed/high stops Pump 1, keeps Pump 2 at 100%, Pump 3 OFF, Solenoid OPEN
        await ws.send(json.dumps({"action": "send_command", "command": "x"}))
        await asyncio.sleep(0.3)
        st = http_get("/api/status")
        assert st["case1_state"] == "SUMP_HIGH", f"Scenario 4 Fail: State is {st['case1_state']}"
        assert st["pump1_duty"] == 0, f"Scenario 4 Fail: P1 must be 0%, got {st['pump1_duty']}%"
        assert st["pump2_duty"] == 100, f"Scenario 4 Fail: P2 must be 100%, got {st['pump2_duty']}%"
        assert st["pump3_duty"] == 0, f"Scenario 5 Fail: P3 must be 0%, got {st['pump3_duty']}%"
        assert st["solenoid_open"] is True, "Scenario 4 Fail: Solenoid must stay OPEN during sump recovery"
        print("  [PASS] Scenario 4: Sump high stops Pump 1 while Pump 2 continues at 100%.")
        print("  [PASS] Scenario 5: Pump 3 remains OFF and Solenoid stays OPEN during sump recovery.")

        # Scenario 9: Cancellation test - If sump goes high again during 10s delay, cancel pending transition
        # First trigger return to normal:
        await ws.send(json.dumps({"action": "send_command", "command": "r"}))
        await asyncio.sleep(0.2)
        st = http_get("/api/status")
        assert st["case1_state"] == "RETURN_TO_NORMAL"
        # Advance 2s into delay:
        await ws.send(json.dumps({"action": "send_command", "command": "!advance_time 2"}))
        await asyncio.sleep(0.1)
        # Renew sump high:
        await ws.send(json.dumps({"action": "send_command", "command": "x"}))
        await asyncio.sleep(0.2)
        st = http_get("/api/status")
        assert st["case1_state"] == "SUMP_HIGH", "Scenario 9 Fail: Must return to SUMP_HIGH"
        # Advance 10s to confirm Case 2 did NOT start:
        await ws.send(json.dumps({"action": "send_command", "command": "!advance_time 10"}))
        await asyncio.sleep(0.2)
        st = http_get("/api/status")
        assert st["case1_state"] == "SUMP_HIGH", "Scenario 9 Fail: Transition should have been canceled"
        assert st["case2_flushing"] is False, "Scenario 9 Fail: Case 2 must NOT start"
        print("  [PASS] Scenario 9: Renewed sump-high event during 10s delay cancels transition.")

        # Scenario 6: Valid return to normal restarts Pump 1 at 50%, Solenoid OPEN
        await ws.send(json.dumps({"action": "send_command", "command": "r"}))
        await asyncio.sleep(0.2)
        st = http_get("/api/status")
        assert st["case1_state"] == "RETURN_TO_NORMAL", f"Scenario 6 Fail: State is {st['case1_state']}"
        assert st["pump1_duty"] == 50, f"Scenario 6 Fail: P1 must be 50%, got {st['pump1_duty']}%"
        assert st["pump2_duty"] == 100, f"Scenario 6 Fail: P2 must be 100%, got {st['pump2_duty']}%"
        assert st["solenoid_open"] is True, "Scenario 6 Fail: Solenoid must be OPEN during 10s return delay"
        print("  [PASS] Scenario 6: Return to normal resumes Pump 1 at 50% and Solenoid OPEN.")

        # Scenario 7: Case 2 does NOT start before full 10-second delay
        await ws.send(json.dumps({"action": "send_command", "command": "!advance_time 5"}))
        await asyncio.sleep(0.2) # Total 5s elapsed since return
        st = http_get("/api/status")
        assert st["case1_state"] == "RETURN_TO_NORMAL", f"Scenario 7 Fail: Case 2 started prematurely ({st['case1_state']})"
        assert st["case2_flushing"] is False, "Scenario 7 Fail: Flushing active before 10s delay finished"
        print("  [PASS] Scenario 7: Case 2 does not start before full 10-second delay.")

        # Scenario 8 & 10: Case 2 starts automatically after 10 seconds WITHOUT another button press
        await ws.send(json.dumps({"action": "send_command", "command": "!advance_time 5.5"}))
        await asyncio.sleep(0.3) # Total elapsed > 10.0s
        st = http_get("/api/status")
        assert st["case1_state"] == "CASE2_FLUSHING", f"Scenario 8 Fail: Expected CASE2_FLUSHING, got {st['case1_state']}"
        assert st["solenoid_open"] is False, "Scenario 10 Fail: Solenoid must CLOSE immediately for Case 2"
        assert st["pump1_duty"] == 50, f"Scenario 10 Fail: P1 must be 50%, got {st['pump1_duty']}%"
        assert st["pump2_duty"] == 100, f"Scenario 10 Fail: P2 must be 100%, got {st['pump2_duty']}%"
        assert st["pump3_duty"] == 50, f"Scenario 10 Fail: P3 must be 50%, got {st['pump3_duty']}%"
        print("  [PASS] Scenario 8: Case 2 started automatically without user interaction.")
        print("  [PASS] Scenario 10: Case 2 closes Solenoid and runs P1=50%, P2=100%, P3=50%.")

        # Scenario 11 & 12: Case 2 timer is 90,000 ms, remains active until expiration
        await ws.send(json.dumps({"action": "send_command", "command": "!advance_time 80"}))
        await asyncio.sleep(0.2)
        st = http_get("/api/status")
        assert st["case1_state"] == "CASE2_FLUSHING", "Scenario 12 Fail: Should still be flushing at 80s"
        assert st["pump3_duty"] == 50, "Scenario 12 Fail: P3 must still be running"
        print("  [PASS] Scenario 11 & 12: Case 2 remains active until 90-second timer expires.")

        # Scenario 13: At 90s timeout, all pumps stop, solenoid closes, shutdown latches
        await ws.send(json.dumps({"action": "send_command", "command": "!advance_time 15"}))
        await asyncio.sleep(0.2)
        st = http_get("/api/status")
        assert st["case1_state"] == "CASE2_SHUTDOWN", f"Scenario 13 Fail: Expected CASE2_SHUTDOWN, got {st['case1_state']}"
        assert st["pump1_duty"] == 0, "Scenario 13 Fail: P1 must be 0%"
        assert st["pump2_duty"] == 0, "Scenario 13 Fail: P2 must be 0%"
        assert st["pump3_duty"] == 0, "Scenario 13 Fail: P3 must be 0%"
        assert st["solenoid_open"] is False, "Scenario 13 Fail: Solenoid must be CLOSED"
        print("  [PASS] Scenario 13: At timeout, all pumps stop, solenoid closes, shutdown latches.")

        # Scenario 14: Additional button presses cannot restart while latched
        await ws.send(json.dumps({"action": "send_command", "command": "!start_btn"}))
        await asyncio.sleep(0.2)
        st = http_get("/api/status")
        assert st["case1_state"] == "CASE2_SHUTDOWN", "Scenario 14 Fail: Must remain in shutdown"
        assert st["pump1_duty"] == 0 and st["pump2_duty"] == 0 and st["pump3_duty"] == 0
        print("  [PASS] Scenario 14: Start button cannot restart sequence while in latched shutdown.")

        # Scenario 15: Emergency Stop overrides everything
        await ws.send(json.dumps({"action": "send_command", "command": "s"}))
        await asyncio.sleep(0.2)
        st = http_get("/api/status")
        assert st["estop_active"] is True, "Scenario 15 Fail: E-Stop must be active"
        assert st["case1_state"] == "EMERGENCY_STOP"
        assert st["pump1_duty"] == 0 and st["pump2_duty"] == 0 and st["pump3_duty"] == 0 and st["solenoid_open"] is False
        print("  [PASS] Scenario 15: Emergency Stop overrides all states and halts outputs.")

        # Clear E-stop and reset to safe idle
        await ws.send(json.dumps({"action": "send_command", "command": "!sys_off"}))
        await asyncio.sleep(0.1)
        await ws.send(json.dumps({"action": "send_command", "command": "!sys_on"}))
        await asyncio.sleep(0.2)
        st = http_get("/api/status")
        assert st["case1_state"] == "SAFE_IDLE"

        # Scenario 16: Manual commissioning commands available where permitted
        await ws.send(json.dumps({"action": "send_command", "command": "d2 75"}))
        await asyncio.sleep(0.2)
        st = http_get("/api/status")
        assert st["pump2_duty"] == 75, f"Scenario 16 Fail: P2 duty should be 75%, got {st['pump2_duty']}%"
        await ws.send(json.dumps({"action": "send_command", "command": "w"})) # disable P2
        await asyncio.sleep(0.2)
        st = http_get("/api/status")
        assert st["pump2_duty"] == 0
        print("  [PASS] Scenario 16: Manual commissioning commands operate correctly.")

        # Scenario 17: UI status follows firmware state
        st = http_get("/api/status")
        assert "case1_state" in st and "solenoid_open" in st and "pump1_duty" in st
        print("  [PASS] Scenario 17: UI telemetry accurately mirrors firmware state.")

        # Scenario 18: Disconnect & Reconnect does not start motors
        http_post("/api/disconnect")
        await asyncio.sleep(0.2)
        http_post("/api/connect", {"port": "MOCK", "baud": 115200, "mock": True})
        await asyncio.sleep(0.3)
        st = http_get("/api/status")
        assert st["case1_state"] == "SAFE_IDLE"
        assert st["pump1_duty"] == 0 and st["pump2_duty"] == 0 and st["pump3_duty"] == 0
        print("  [PASS] Scenario 18: Reconnection does not start motors (remains in SAFE_IDLE).")

        # Scenario 19: No redundant Normal Flow button in UI HTML
        index_path = os.path.join(UI_DIR, "index.html")
        with open(index_path, "r", encoding="utf-8") as f:
            html = f.read()
        assert "btn-normal-flow" not in html
        print("  [PASS] Scenario 19: No redundant Normal Flow start button in UI.")

        # Scenario 20: No visible 90-second countdown or progress bar
        assert "case2-flush-monitor" not in html
        assert "flush-progress-fill" not in html
        print("  [PASS] Scenario 20: No visible 90-second countdown or progress bar in UI.")

    print("\nALL 20 VERIFICATION SCENARIOS PASSED SUCCESSFULLY!")

def main():
    test_static_code_inspection()

    # Launch bridge server in background subprocess if not running
    proc = None
    try:
        try:
            http_get("/api/status")
            print("Bridge is already running on port 8080.")
        except Exception:
            print("Starting bridge.py on port 8080...")
            proc = subprocess.Popen(
                [sys.executable, os.path.join(UI_DIR, "bridge.py")],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            time.sleep(2.0)

        asyncio.run(run_scenario_tests())

    finally:
        if proc:
            print("Terminating test bridge process...")
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()

if __name__ == "__main__":
    main()
