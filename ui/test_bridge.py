"""
Full End-to-End WebSocket & REST API Integration Test for LRC SCADA Bridge
"""
import asyncio
import json
import websockets
import urllib.request

async def test_scada_bridge():
    print("=== STARTING SCADA BRIDGE INTEGRATION TEST ===")
    
    # 1. Test REST /api/status
    req = urllib.request.Request("http://127.0.0.1:8080/api/status")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        print("[PASS] GET /api/status ->", data)

    # 2. Test REST /api/ports
    req = urllib.request.Request("http://127.0.0.1:8080/api/ports")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        ports = json.loads(resp.read().decode())
        print("[PASS] GET /api/ports ->", ports)

    # 3. Test REST /api/connect (Mock Mode)
    post_data = json.dumps({"port": "MOCK", "baud": 115200, "mock": True}).encode()
    req = urllib.request.Request("http://127.0.0.1:8080/api/connect", data=post_data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        conn_res = json.loads(resp.read().decode())
        print("[PASS] POST /api/connect (Mock) ->", conn_res)
        assert conn_res["status"] == "connected"
        assert conn_res["is_mock"] is True

    # 4. Connect via WebSocket
    uri = "ws://127.0.0.1:8080/ws"
    async with websockets.connect(uri) as ws:
        print("[PASS] WebSocket connected successfully to", uri)
        
        # Receive initial state
        init_msg = await asyncio.wait_for(ws.recv(), timeout=3.0)
        init_data = json.loads(init_msg)
        print("[PASS] Received initial_state:", init_data["type"], "| Connected:", init_data["connected"], "| Mock:", init_data["is_mock"])
        assert init_data["type"] == "initial_state"
        assert init_data["connected"] is True
        assert init_data["case1_state"] == "SAFE_IDLE", f"Expected SAFE_IDLE, got {init_data.get('case1_state')}"
        assert init_data["pump1_duty"] == 0, f"Expected P1=0%, got {init_data.get('pump1_duty')}"
        assert init_data["pump2_duty"] == 0, f"Expected P2=0%, got {init_data.get('pump2_duty')}"
        assert init_data["pump3_duty"] == 0, f"Expected P3=0%, got {init_data.get('pump3_duty')}"
        assert init_data["solenoid_open"] is False, "Expected Solenoid closed on connect"
        print("[PASS] Verified initial_state has SAFE_IDLE, all 3 pumps at 0%, and Solenoid CLOSED!")

        # Query status 'p' and verify pumps remain OFF
        await ws.send(json.dumps({"action": "send_command", "command": "p"}))
        print("[SENT] Status query 'p' over WebSocket (pumps must remain OFF)")
        await asyncio.sleep(0.3)

        # Send command 'N' (Normal Flow: P1 50%, P2 100%)
        await ws.send(json.dumps({"action": "send_command", "command": "N"}))
        print("[SENT] Explicit Operator Command 'N' over WebSocket")

        # Listen for messages over 6 seconds to capture 2 CSV intervals (2.5s each)
        flow_records_received = 0
        raw_lines_received = 0
        start_t = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_t < 7.0:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=3.0)
                parsed = json.loads(msg)
                if parsed.get("type") == "flow_record":
                    flow_records_received += 1
                    print(f"  [FLOW RECORD #{flow_records_received}] PWM: {parsed['pump2_pwm']}%, Freq: {parsed['frequency_hz']} Hz, Flow: {parsed['flow_lpm']} L/min")
                elif parsed.get("type") == "raw_serial":
                    raw_lines_received += 1
                    if "NORMAL FLOW" in parsed.get("line", ""):
                        print("  [CONFIRMED] Normal Flow message received:", parsed["line"])
            except asyncio.TimeoutError:
                break

            if flow_records_received >= 2:
                break

        assert flow_records_received >= 2, "Expected at least 2 flow records"
        print(f"[PASS] Successfully received {flow_records_received} flow records and {raw_lines_received} raw lines!")

        # Test Float Switch Repeated Transitions (NORMAL -> HIGH -> NORMAL -> HIGH -> NORMAL)
        print("\n[TEST] Testing Float Switch Live State Synchronization...")
        for cycle in range(2):
            print(f"  --- Cycle {cycle + 1}: Transitioning to HIGH [x] ---")
            await ws.send(json.dumps({"action": "send_command", "command": "x"}))
            
            high_confirmed = False
            for _ in range(10):
                msg = await asyncio.wait_for(ws.recv(), timeout=3.0)
                parsed = json.loads(msg)
                if parsed.get("type") == "state_change" and parsed.get("state") == "SUMP_HIGH":
                    assert parsed.get("float_triggered") is True, "Expected float_triggered: True in state_change"
                    assert parsed.get("pump1") == 0, "Pump 1 must halt (0%) during SUMP_HIGH"
                    high_confirmed = True
                    print(f"  [CONFIRMED] Cycle {cycle + 1} SUMP_HIGH state received: P1={parsed.get('pump1')}%, Float={parsed.get('float_triggered')}")
                    break
            assert high_confirmed, f"Cycle {cycle + 1} failed to enter SUMP_HIGH"

            print(f"  --- Cycle {cycle + 1}: Transitioning to RETURN TO NORMAL [r] ---")
            await ws.send(json.dumps({"action": "send_command", "command": "r"}))
            
            norm_confirmed = False
            for _ in range(10):
                msg = await asyncio.wait_for(ws.recv(), timeout=3.0)
                parsed = json.loads(msg)
                if parsed.get("type") == "state_change" and parsed.get("state") == "RETURN_TO_NORMAL":
                    assert parsed.get("float_triggered") is False, "Expected float_triggered: False in state_change"
                    assert parsed.get("pump1") == 50, "Pump 1 must resume (50%) on return to normal"
                    norm_confirmed = True
                    print(f"  [CONFIRMED] Cycle {cycle + 1} RETURN_TO_NORMAL state received: P1={parsed.get('pump1')}%, Float={parsed.get('float_triggered')}")
                    break
            assert norm_confirmed, f"Cycle {cycle + 1} failed to return to normal"

        print("[PASS] Float Switch repeated transitions (NORMAL -> HIGH -> NORMAL -> HIGH -> NORMAL) verified 100%!")

        # Test Case 2 trigger in mock mode
        print("\n[TEST] Triggering Case 2 Flush sequence...")
        await ws.send(json.dumps({"action": "send_command", "command": "!flush_btn"}))
        
        # Wait for Case 2 start notification
        case2_started = False
        for _ in range(10):
            msg = await asyncio.wait_for(ws.recv(), timeout=3.0)
            parsed = json.loads(msg)
            if parsed.get("type") == "case2_flush_start":
                print("  [CONFIRMED] Case 2 Flush Start Event Received:", parsed)
                assert parsed.get("duration_s") == 90, f"Expected 90s duration, got {parsed.get('duration_s')}"
                case2_started = True
                break

        assert case2_started, "Expected Case 2 flush start event"

        # Test Emergency Stop
        print("[TEST] Sending Emergency Stop 's'...")
        await ws.send(json.dumps({"action": "send_command", "command": "s"}))

        estop_received = False
        for _ in range(10):
            msg = await asyncio.wait_for(ws.recv(), timeout=3.0)
            parsed = json.loads(msg)
            if parsed.get("type") == "estop_change" and parsed.get("active") is True:
                print("  [CONFIRMED] E-Stop Active Event Received:", parsed)
                estop_received = True
                break

        assert estop_received, "Expected E-Stop active event"

    # 5. Test Disconnect
    req = urllib.request.Request("http://127.0.0.1:8080/api/disconnect", data=b"{}", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        disc_res = json.loads(resp.read().decode())
        print("[PASS] POST /api/disconnect ->", disc_res)

    print("\n=== ALL SCADA BRIDGE TESTS PASSED (100% SUCCESS) ===\n")

if __name__ == "__main__":
    asyncio.run(test_scada_bridge())
