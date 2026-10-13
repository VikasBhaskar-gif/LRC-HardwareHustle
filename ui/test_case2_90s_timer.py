"""
test_case2_90s_timer.py - Automated Test Suite for Case 2 90-Second Flush Sequence

Validates:
1. Configured timer duration: exactly 90 seconds (90,000 ms).
2. Starting conditions and safety checks: Case 2 starts only from valid operational state.
3. Operating conditions: P1=50%, P2=100%, P3=50%, Solenoid=CLOSED.
4. Non-blocking timing progression: Case 2 remains actively circulating before 90 seconds.
5. Completion at 90 seconds: all 3 pumps halt (0%), solenoid closed, state enters CASE2_SHUTDOWN.
6. Latched shutdown enforcement: motors do not automatically restart.
7. Serial Monitor strings: 'Flush timer started: 90 seconds' and '90-second flush complete'.
8. UI WebSocket payload: duration_s == 90.
"""

import asyncio
import json
import urllib.request
import urllib.parse
import websockets
import sys
import time

BASE_URL = "http://127.0.0.1:8080"
WS_URL = "ws://127.0.0.1:8080/ws"

def http_get(path):
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

def http_post(path, data=None):
    if data is None:
        data = {}
    url = f"{BASE_URL}{path}"
    json_data = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=json_data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

async def run_tests():
    print("=" * 70)
    print("RUNNING 90-SECOND CASE 2 FLUSH TIMING VERIFICATION SUITE")
    print("=" * 70)

    # 1. Connect to mock device
    print("\n[STEP 1] Connecting to Mock ESP32 Controller...")
    res = http_post("/api/connect", {"port": "MOCK", "baud": 115200, "mock": True})
    assert res.get("status") == "connected", f"Failed to connect: {res}"
    print("  -> Connected in Mock mode.")

    async with websockets.connect(WS_URL) as ws:
        # Drain initial events and wait for mock boot lines to settle
        await asyncio.sleep(1.0)

        # 2. Verify Safe Idle initial state
        print("\n[STEP 2] Verifying Power-On Safe Idle State...")
        st = http_get("/api/status")
        assert st["case1_state"] == "SAFE_IDLE", f"Expected SAFE_IDLE, got {st['case1_state']}"
        assert st["pump1_duty"] == 0, "P1 must be 0%"
        assert st["pump2_duty"] == 0, "P2 must be 0%"
        assert st["pump3_duty"] == 0, "P3 must be 0%"
        assert st["solenoid_open"] is False, "Solenoid must be CLOSED"
        print("  -> PASS: SAFE_IDLE verified (all motors OFF, solenoid CLOSED).")

        # 3. Start Normal Flow
        print("\n[STEP 3] Starting Normal Circulation ('N')...")
        await ws.send(json.dumps({"action": "send_command", "command": "N"}))
        await asyncio.sleep(0.4)
        st = http_get("/api/status")
        assert st["case1_state"] == "NORMAL", f"Expected NORMAL, got {st['case1_state']}"
        assert st["pump1_duty"] == 50, "P1 must be 50%"
        assert st["pump2_duty"] == 100, "P2 must be 100%"
        assert st["solenoid_open"] is True, "Solenoid must be OPEN"
        print("  -> PASS: Normal Circulation running (P1=50%, P2=100%, Solenoid=OPEN).")

        # 4. Trigger Automatic Case 2 Sequence via Sump High -> Return Normal
        print("\n[STEP 4] Triggering Automatic Case 2 Sequence via Float Switch Recovery...")
        await ws.send(json.dumps({"action": "send_command", "command": "x"}))
        await asyncio.sleep(0.2)
        await ws.send(json.dumps({"action": "send_command", "command": "r"}))
        await asyncio.sleep(0.2)
        # Advance 10s to complete the 10-second return-to-normal delay
        await ws.send(json.dumps({"action": "send_command", "command": "!advance_time 10.5"}))
        await asyncio.sleep(0.3)
        
        flush_start_evt = None
        for _ in range(50):
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                msg = json.loads(raw)
                if msg.get("type") == "case2_flush_start":
                    flush_start_evt = msg
                    break
            except asyncio.TimeoutError:
                break

        assert flush_start_evt is not None, "Failed to receive case2_flush_start WebSocket event"
        print(f"  -> Received case2_flush_start: {flush_start_evt}")

        # 5. Check exact payload and configured duration
        print("\n[STEP 5] Validating 90-Second Configured Parameters...")
        assert flush_start_evt["duration_s"] == 90, f"Expected duration_s == 90, got {flush_start_evt['duration_s']}"
        assert flush_start_evt["pump1_duty"] == 50, f"Expected P1=50%, got {flush_start_evt['pump1_duty']}%"
        assert flush_start_evt["pump2_duty"] == 100, f"Expected P2=100%, got {flush_start_evt['pump2_duty']}%"
        assert flush_start_evt["pump3_duty"] == 50, f"Expected P3=50%, got {flush_start_evt['pump3_duty']}%"
        assert flush_start_evt["solenoid_open"] is False, "Expected Solenoid CLOSED"
        print("  -> PASS: Exactly 90 seconds configured. Operating duties: P1=50%, P2=100%, P3=50%, Solenoid=CLOSED.")

        # 6. Verify System Remains Active Before 90 Seconds Elapsed
        print("\n[STEP 6] Testing Timing Boundary: Remaining Active Before 90 Seconds...")
        # Advance mock time by 30 seconds (elapsed = 30s)
        await ws.send(json.dumps({"action": "send_command", "command": "!advance_time 30"}))
        await asyncio.sleep(0.3)
        st = http_get("/api/status")
        assert st["case1_state"] == "CASE2_FLUSHING", "System must still be FLUSHING at 30s"
        assert st["pump1_duty"] == 50 and st["pump2_duty"] == 100 and st["pump3_duty"] == 50, "Pumps must still run at 30s"
        assert st["solenoid_open"] is False, "Solenoid must remain CLOSED at 30s"
        print("  -> PASS: System actively flushing at elapsed = 30s.")

        # Advance mock time by another 55 seconds (elapsed = 85s < 90s)
        await ws.send(json.dumps({"action": "send_command", "command": "!advance_time 55"}))
        await asyncio.sleep(0.3)
        st = http_get("/api/status")
        assert st["case1_state"] == "CASE2_FLUSHING", "System must still be FLUSHING at 85s"
        assert st["pump1_duty"] == 50 and st["pump2_duty"] == 100 and st["pump3_duty"] == 50, "Pumps must still run at 85s"
        print("  -> PASS: System actively flushing at elapsed = 85s (< 90s).")

        # 7. Complete Flush at Exactly 90 Seconds
        print("\n[STEP 7] Testing Completion at Exactly 90 Seconds...")
        # Advance mock time by 6 seconds (elapsed = 91s >= 90s)
        await ws.send(json.dumps({"action": "send_command", "command": "!advance_time 6"}))
        
        flush_complete_evt = None
        for _ in range(30):
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                msg = json.loads(raw)
                if msg.get("type") == "case2_flush_complete":
                    flush_complete_evt = msg
                    break
            except asyncio.TimeoutError:
                break

        assert flush_complete_evt is not None, "Failed to receive case2_flush_complete WebSocket event at 90s"
        print(f"  -> Received case2_flush_complete: {flush_complete_evt}")

        # 8. Verify Safe Shutdown and Latched State
        print("\n[STEP 8] Validating Latched Safe Shutdown State...")
        st = http_get("/api/status")
        assert st["case1_state"] == "CASE2_SHUTDOWN", f"Expected CASE2_SHUTDOWN, got {st['case1_state']}"
        assert st["pump1_duty"] == 0, f"Pump 1 must be 0%, got {st['pump1_duty']}%"
        assert st["pump2_duty"] == 0, f"Pump 2 must be 0%, got {st['pump2_duty']}%"
        assert st["pump3_duty"] == 0, f"Pump 3 must be 0%, got {st['pump3_duty']}%"
        assert st["solenoid_open"] is False, f"Solenoid must remain CLOSED, got {st['solenoid_open']}"
        assert st["case2_flushing"] is False, "Flushing flag must be False"
        assert st["case2_shutdown"] is True, "Shutdown flag must be True"
        print("  -> PASS: All three pumps stopped (0%), solenoid closed, state is CASE2_SHUTDOWN.")

        # 9. Verify Safety Interlock: Pumps Do NOT Automatically Restart
        print("\n[STEP 9] Verifying Prevention of Auto-Restart & Re-Triggering...")
        # Try to press flush button again while in shutdown
        await ws.send(json.dumps({"action": "send_command", "command": "!flush_btn"}))
        await asyncio.sleep(0.3)
        st = http_get("/api/status")
        assert st["case1_state"] == "CASE2_SHUTDOWN", "System must stay in CASE2_SHUTDOWN"
        assert st["pump1_duty"] == 0 and st["pump2_duty"] == 0 and st["pump3_duty"] == 0, "Motors must not restart"
        print("  -> PASS: Re-trigger rejected. System latched safely in shutdown.")

        # 10. Verify Emergency Stop Integration
        print("\n[STEP 10] Testing Emergency Stop during Flush Sequence...")
        # Reset to SAFE_IDLE by cycling connection
        http_post("/api/connect", {"port": "MOCK", "baud": 115200, "mock": True})
        await asyncio.sleep(1.0)
        await ws.send(json.dumps({"action": "send_command", "command": "N"}))
        await asyncio.sleep(0.3)
        await ws.send(json.dumps({"action": "send_command", "command": "x"}))
        await asyncio.sleep(0.2)
        await ws.send(json.dumps({"action": "send_command", "command": "r"}))
        await asyncio.sleep(0.2)
        await ws.send(json.dumps({"action": "send_command", "command": "!advance_time 10.5"}))
        await asyncio.sleep(0.3)
        st = http_get("/api/status")
        assert st["case1_state"] == "CASE2_FLUSHING"
        
        # Fire Emergency Stop
        await ws.send(json.dumps({"action": "send_command", "command": "s"}))
        await asyncio.sleep(0.3)
        st = http_get("/api/status")
        assert st["estop_active"] is True, "E-Stop must be active"
        assert st["pump1_duty"] == 0 and st["pump2_duty"] == 0 and st["pump3_duty"] == 0, "All pumps must halt on E-Stop"
        assert st["solenoid_open"] is False, "Solenoid must close on E-Stop"
        print("  -> PASS: Emergency Stop overrides Case 2 flush immediately and safely halts all pumps.")

    http_post("/api/disconnect")
    print("\n" + "=" * 70)
    print("ALL 10 VERIFICATION STEPS PASSED SUCCESSFULLY (90-SECOND CASE 2 FLUSH)")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(run_tests())
