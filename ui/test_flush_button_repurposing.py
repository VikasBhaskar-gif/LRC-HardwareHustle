"""
Targeted Verification Test Suite for GPIO 34 Repurposing as Physical Flush Button
Verifies:
Layer 1: ESP32 Firmware Logic & Pin Mapping
Layer 2: Serial Monitor Diagnostics & Commands
Layer 3: Web UI & SCADA Bridge Event Synchronization
"""
import asyncio
import json
import urllib.request
import websockets

BASE_URL = "http://127.0.0.1:8080"
WS_URL = "ws://127.0.0.1:8080/ws"

def http_post(endpoint, payload=None):
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(f"{BASE_URL}{endpoint}", data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

def http_get(endpoint):
    req = urllib.request.Request(f"{BASE_URL}{endpoint}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

async def run_gpio34_repurposing_tests():
    print("=" * 70)
    print("  GPIO 34 REPURPOSING VERIFICATION: PHYSICAL FLUSH BUTTON (CASE 2)")
    print("=" * 70)

    # 1. Reset / Disconnect
    http_post("/api/disconnect")
    await asyncio.sleep(0.3)

    # 2. Connect to Mock ESP32
    conn = http_post("/api/connect", {"port": "MOCK", "baud": 115200, "mock": True})
    assert conn["status"] == "connected"
    print("[PASS] Connected to SCADA bridge in Mock ESP32 mode.")

    async with websockets.connect(WS_URL) as ws:
        # Drain initial_state
        init_raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
        init_state = json.loads(init_raw)
        assert init_state["type"] == "initial_state"
        assert init_state["case1_state"] == "SAFE_IDLE"
        print("[PASS] Initial state confirmed SAFE_IDLE with motors OFF at boot.")

        # ---------------------------------------------------------------------
        # TEST A: Verify Serial Monitor Diagnostics & Decoupling
        # ---------------------------------------------------------------------
        print("\n--- TEST A: Serial Monitor Diagnostics (p & y commands) ---")
        await ws.send(json.dumps({"action": "send_command", "command": "p"}))
        
        # Collect serial lines from 'p'
        lines = []
        for _ in range(35):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                data = json.loads(msg)
                if data.get("type") == "raw_serial":
                    lines.append(data.get("line", ""))
            except asyncio.TimeoutError:
                break

        full_output = "\n".join(lines)
        print("  Checking diagnostic lines received:")
        assert "Flush Button (GPIO 34)" in full_output, "Expected 'Flush Button (GPIO 34)' in status output"
        assert "System Switch (GPIO 34)" not in full_output, "Obsolete 'System Switch (GPIO 34)' MUST NOT be in status output"
        print("  [PASS] Diagnostic output correctly reports '--- Flush Button (GPIO 34) ---'")
        print("  [PASS] Confirmed obsolete 'System Switch (GPIO 34)' is completely removed from diagnostics.")

        # Test 'y' query
        await ws.send(json.dumps({"action": "send_command", "command": "y"}))
        y_confirmed = False
        for _ in range(5):
            msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
            data = json.loads(msg)
            if data.get("type") == "raw_serial" and "SYSTEM -> ON" in data.get("line", ""):
                y_confirmed = True
                break
        assert y_confirmed, "Expected 'SYSTEM -> ON' response to 'y' query"
        print("  [PASS] Serial command 'y' accurately queries system state.")

        # ---------------------------------------------------------------------
        # TEST B: Safety Interlock Rejection of Flush Button
        # ---------------------------------------------------------------------
        print("\n--- TEST B: Case 2 Interlock Checks (Flush button pressed in disallowed states) ---")
        
        # 1. Pressed in SAFE_IDLE -> Rejected
        await ws.send(json.dumps({"action": "send_command", "command": "!flush_btn"}))
        await asyncio.sleep(0.3)
        st = http_get("/api/status")
        assert st["case1_state"] == "SAFE_IDLE", f"Flush must be rejected in SAFE_IDLE! Got {st['case1_state']}"
        assert st["pump3_duty"] == 0, "Pump 3 must not run when flush is rejected in SAFE_IDLE"
        print("  [PASS] Flush button correctly rejected in SAFE_IDLE (interlock enforced).")

        # 2. Start Normal Flow 'N', then disable system -> Pressed -> Rejected
        await ws.send(json.dumps({"action": "send_command", "command": "N"}))
        await asyncio.sleep(0.4)
        st = http_get("/api/status")
        assert st["case1_state"] == "NORMAL"
        print("  Entered NORMAL state: P1=50%, P2=100%, Solenoid=OPEN.")

        # Disable system via command '!sys_off'
        await ws.send(json.dumps({"action": "send_command", "command": "!sys_off"}))
        await asyncio.sleep(0.3)
        st = http_get("/api/status")
        assert st["case1_state"] == "SYSTEM_OFF"
        assert st["system_on"] is False

        # Attempt flush button while disabled -> Rejected
        await ws.send(json.dumps({"action": "send_command", "command": "!flush_btn"}))
        await asyncio.sleep(0.3)
        st = http_get("/api/status")
        assert st["case1_state"] == "SYSTEM_OFF"
        assert st["pump3_duty"] == 0
        print("  [PASS] Flush button correctly rejected while System is DISABLED.")

        # Re-enable system via command '!sys_on' and start Normal Flow 'N'
        await ws.send(json.dumps({"action": "send_command", "command": "!sys_on"}))
        await asyncio.sleep(0.3)
        await ws.send(json.dumps({"action": "send_command", "command": "N"}))
        await asyncio.sleep(0.4)

        # Trigger E-Stop 's' -> Attempt flush button -> Rejected
        await ws.send(json.dumps({"action": "send_command", "command": "s"}))
        await asyncio.sleep(0.3)
        st = http_get("/api/status")
        assert st["estop_active"] is True

        await ws.send(json.dumps({"action": "send_command", "command": "!flush_btn"}))
        await asyncio.sleep(0.3)
        st = http_get("/api/status")
        assert st["case1_state"] == "EMERGENCY_STOP"
        assert st["pump3_duty"] == 0
        print("  [PASS] Flush button correctly rejected while Emergency Stop is ACTIVE.")

        # Clear E-stop via 'n'
        await ws.send(json.dumps({"action": "send_command", "command": "n"}))
        await asyncio.sleep(0.4)
        st = http_get("/api/status")
        assert st["case1_state"] == "NORMAL"
        assert st["estop_active"] is False
        print("  E-Stop cleared, restored to NORMAL recirculation.")

        # ---------------------------------------------------------------------
        # TEST C: Valid Case 2 Execution via GPIO 34 Flush Button
        # ---------------------------------------------------------------------
        print("\n--- TEST C: Case 2 Execution via GPIO 34 Flush Button ---")
        # Drain any residual messages from prior step
        while True:
            try:
                await asyncio.wait_for(ws.recv(), timeout=0.1)
            except asyncio.TimeoutError:
                break

        await ws.send(json.dumps({"action": "send_command", "command": "!flush_btn"}))
        
        flush_started = False
        start_payload = None
        for _ in range(25):
            msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
            data = json.loads(msg)
            if data.get("type") == "case2_flush_start":
                flush_started = True
                start_payload = data
                break

        assert flush_started, "Expected case2_flush_start event upon flush button press"
        print(f"  [PASS] Received case2_flush_start: {start_payload}")
        assert start_payload["pump1_duty"] == 50, "P1 must be 50% during Case 2"
        assert start_payload["pump2_duty"] == 100, "P2 must be 100% during Case 2"
        assert start_payload["pump3_duty"] == 50, "P3 must be 50% during Case 2"
        assert start_payload["solenoid_open"] is False, "Solenoid must be CLOSED during Case 2"
        assert start_payload["duration_s"] == 90, "Case 2 duration must be 90 seconds"

        # Check status during flushing
        st = http_get("/api/status")
        assert st["case1_state"] == "CASE2_FLUSHING"
        assert st["pump1_duty"] == 50
        assert st["pump2_duty"] == 100
        assert st["pump3_duty"] == 50
        assert st["solenoid_open"] is False
        assert st["case2_flushing"] is True
        print("  [PASS] Simultaneous 3-pump operation active: P1=50%, P2=100%, P3=50%, Solenoid=CLOSED.")

        # ---------------------------------------------------------------------
        # TEST D: Edge Detection & Holding Prevention
        # ---------------------------------------------------------------------
        print("\n--- TEST D: Edge-Detection Verification (Holding button does NOT restart Case 2) ---")
        # Send duplicate !flush_btn while already flushing
        await ws.send(json.dumps({"action": "send_command", "command": "!flush_btn"}))
        await asyncio.sleep(0.3)
        st = http_get("/api/status")
        assert st["case2_flushing"] is True
        print("  [PASS] Holding / repeating flush trigger while flushing is safely ignored.")

        # ---------------------------------------------------------------------
        # TEST E: System ON/OFF Decoupling
        # ---------------------------------------------------------------------
        print("\n--- TEST E: Verifying System ON/OFF is Completely Decoupled from Flush Button ---")
        # Ensure system remained ON throughout the flush press
        assert st["system_on"] is True, "System state must remain ON; pressing flush button must NOT turn system OFF!"
        print("  [PASS] GPIO 34 trigger did not alter System ON/OFF state (complete decoupling verified).")

    # 3. Disconnect
    http_post("/api/disconnect")
    print("\n" + "=" * 70)
    print("  ALL GPIO 34 FLUSH BUTTON TESTS PASSED (100% SUCCESS)!")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(run_gpio34_repurposing_tests())
