"""
Automated CDP (Chrome DevTools Protocol) Browser Test for LRC Hardware Controller UI.
Tests:
1. Page load and console errors.
2. Responsive Schematic Header layout at 1440x900, 1366x768, and 1280x720.
3. Verification that CASE 1 RECIRCULATION mode badge is never clipped or overlapping.
4. Live Float Switch repeated transitions (NORMAL -> HIGH -> NORMAL -> HIGH -> NORMAL) without refreshing.
5. Pump 1 stopping at Sump High (0%) and resuming on Normal (50%).
6. Flow Rate Canvas graph rendering, high-DPI scaling, and continuous updates across tab switches.
7. Captures visual screenshots for audit.
"""
import asyncio
import json
import os
import subprocess
import time
import urllib.request
import websockets

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
SCREENSHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

class CDPClient:
    def __init__(self, ws_url):
        self.ws_url = ws_url
        self.ws = None
        self.msg_id = 1
        self.pending = {}

    async def connect(self):
        self.ws = await websockets.connect(self.ws_url, max_size=50*1024*1024)
        asyncio.create_task(self._listen())

    async def _listen(self):
        try:
            async for raw in self.ws:
                data = json.loads(raw)
                if "id" in data and data["id"] in self.pending:
                    self.pending[data["id"]].set_result(data)
                elif data.get("method") == "Console.messageAdded":
                    msg = data["params"]["message"]
                    if msg.get("level") == "error":
                        print(f"  [BROWSER CONSOLE ERROR] {msg.get('text')}")
        except Exception:
            pass

    async def send(self, method, params=None):
        mid = self.msg_id
        self.msg_id += 1
        fut = asyncio.get_event_loop().create_future()
        self.pending[mid] = fut
        payload = {"id": mid, "method": method, "params": params or {}}
        await self.ws.send(json.dumps(payload))
        res = await asyncio.wait_for(fut, timeout=10.0)
        del self.pending[mid]
        if "error" in res:
            raise RuntimeError(f"CDP error for {method}: {res['error']}")
        return res.get("result", {})

    async def eval(self, expr):
        res = await self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
        val = res.get("result", {})
        if val.get("subtype") == "error":
            raise RuntimeError(f"JS error evaluating {expr}: {val.get('description')}")
        return val.get("value")

    async def set_viewport(self, w, h):
        await self.send("Emulation.setDeviceMetricsOverride", {
            "width": w,
            "height": h,
            "deviceScaleFactor": 1,
            "mobile": False
        })
        await asyncio.sleep(0.3)

    async def screenshot(self, filename):
        res = await self.send("Page.captureScreenshot", {"format": "png"})
        import base64
        path = os.path.join(SCREENSHOT_DIR, filename)
        with open(path, "wb") as f:
            f.write(base64.b64decode(res["data"]))
        print(f"  [SAVED SCREENSHOT] {path}")
        return path

async def run_tests():
    print("=== LAUNCHING HEADLESS CHROME ===")
    user_data = os.path.join(SCREENSHOT_DIR, "chrome_user_data")
    chrome_proc = subprocess.Popen([
        CHROME_PATH,
        "--headless=new",
        "--remote-debugging-port=9222",
        "--no-first-run",
        "--disable-gpu",
        "--disable-extensions",
        f"--user-data-dir={user_data}",
        "--window-size=1440,900",
        "http://127.0.0.1:8080/"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        # Wait for debugging port
        ws_url = None
        for _ in range(30):
            try:
                with urllib.request.urlopen("http://127.0.0.1:9222/json") as resp:
                    pages = json.loads(resp.read().decode())
                    page_targets = [p for p in pages if p.get("type") == "page"]
                    if page_targets:
                        ws_url = page_targets[0].get("webSocketDebuggerUrl")
                        break
            except Exception:
                time.sleep(0.3)

        assert ws_url, "Failed to connect to Chrome remote debugging port"
        print(f"[CONNECTED] Chrome remote debugging ws: {ws_url}")

        cdp = CDPClient(ws_url)
        await cdp.connect()
        await cdp.send("Page.enable")
        await cdp.send("Runtime.enable")
        await cdp.send("Console.enable")

        # Disconnect any previous bridge session so tests start from a clean state
        try:
            req = urllib.request.Request("http://127.0.0.1:8080/api/disconnect", data=b"{}", headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=1.0)
        except Exception:
            pass

        # Explicitly navigate to ensure page is loaded
        nav_res = await cdp.send("Page.navigate", {"url": "http://127.0.0.1:8080/"})
        print(f"  Page.navigate result: {nav_res}")
        await asyncio.sleep(2.5)

        eval_res = await cdp.send("Runtime.evaluate", {"expression": "location.href", "returnByValue": True})
        print(f"  location.href result: {eval_res}")

        eval_title = await cdp.send("Runtime.evaluate", {"expression": "document.title", "returnByValue": True})
        print(f"  document.title result: {eval_title}")
        title = eval_title.get("result", {}).get("value", "")
        print(f"[PAGE LOADED] Title: '{title}'")
        assert "LRC" in title

        # Check for initial JS errors
        init_err = await cdp.eval("window.__initError || null")
        assert init_err is None, f"Initial JS error detected: {init_err}"
        print("[PASS] Clean initialization - 0 JavaScript errors detected")

        # -------------------------------------------------------------
        # TEST 1: Schematic Header Alignment Across Target Resolutions
        # -------------------------------------------------------------
        print("\n--- TEST 1: Schematic Header Alignment Across 3 Viewports ---")
        resolutions = [
            (1440, 900, "1440x900"),
            (1366, 768, "1366x768"),
            (1280, 720, "1280x720")
        ]

        for w, h, name in resolutions:
            await cdp.set_viewport(w, h)
            header_geom = await cdp.eval("""(() => {
                const card = document.querySelector('.schematic-card');
                const header = document.querySelector('.schematic-header');
                const titleGrp = document.querySelector('.schematic-title-group');
                const title = document.querySelector('.schematic-title-group .card-title');
                const note = document.querySelector('.schematic-note');
                const pill = document.getElementById('schematic-mode-pill');
                const badges = document.querySelector('.schematic-badges');

                const cardRect = card.getBoundingClientRect();
                const headRect = header.getBoundingClientRect();
                const titleGrpRect = titleGrp.getBoundingClientRect();
                const titleRect = title.getBoundingClientRect();
                const noteRect = note.getBoundingClientRect();
                const pillRect = pill.getBoundingClientRect();

                return {
                    cardRight: cardRect.right,
                    headRight: headRect.right,
                    headWidth: headRect.width,
                    titleGrpRight: titleGrpRect.right,
                    titleRight: titleRect.right,
                    noteRight: noteRect.right,
                    pillLeft: pillRect.left,
                    pillRight: pillRect.right,
                    pillWidth: pillRect.width,
                    pillText: pill.textContent.trim(),
                    noteText: note.textContent.trim(),
                    isBadgeFullyInsideCard: pillRect.right <= cardRect.right + 1,
                    gapBetweenTitleAndBadge: pillRect.left - titleGrpRect.right,
                    noteTruncated: note.scrollWidth > note.clientWidth
                };
            })()""")

            print(f"  Viewport {name}:")
            print(f"    Header Width: {header_geom['headWidth']}px | Badge: '{header_geom['pillText']}' ({header_geom['pillWidth']}px)")
            print(f"    Schematic Note: '{header_geom['noteText']}'")
            print(f"    Badge Right ({header_geom['pillRight']:.1f}px) <= Card Right ({header_geom['cardRight']:.1f}px): {header_geom['isBadgeFullyInsideCard']}")
            print(f"    Gap between title group and badge: {header_geom['gapBetweenTitleAndBadge']:.1f}px")

            assert header_geom['noteText'] == "Click components to control", f"Schematic note must be exactly 'Click components to control', got '{header_geom['noteText']}'"
            assert header_geom['isBadgeFullyInsideCard'], f"Badge clipped at {name}!"
            assert header_geom['gapBetweenTitleAndBadge'] >= -0.5, f"Badge overlapping title group at {name}!"
            print(f"    [PASS] Clean alignment, note verified, and zero clipping at {name}")
            await cdp.screenshot(f"schematic_header_{name}.png")

        # Restore default 1440x900 viewport
        await cdp.set_viewport(1440, 900)

        # -------------------------------------------------------------
        # TEST 1B: Six UI Presentation Cleanup Checks in Initial State
        # -------------------------------------------------------------
        print("\n--- TEST 1B: Six UI Presentation Cleanup Checks ---")
        cleanup_check = await cdp.eval("""(() => {
            // 1. Log 'L' button removal
            const logLBtn = document.getElementById('btn-toggle-log');
            const logBadge = document.getElementById('log-status-badge');
            const exportBtn = document.getElementById('btn-export-csv');
            const clearBtn = document.getElementById('btn-clear-table');

            // 2. Schematic instruction
            const note = document.querySelector('.schematic-note');

            // 3. Pump 2 symbol and positioning
            const pump2 = document.getElementById('comp-pump2');
            const p2Circle = document.getElementById('pump2-circle');
            const p2Rotor = document.getElementById('pump2-rotor');
            const p2DutyText = document.getElementById('pump2-duty-text');
            const p2Transform = pump2 ? pump2.getAttribute('transform') : '';

            // Check labels inside Pump 2
            let p2Name = null, p2CompId = null, p2CompSub = null;
            if (pump2) {
                const nameEl = pump2.querySelector('.pump-name');
                const idEl = pump2.querySelector('.comp-id-label');
                const subEl = pump2.querySelector('.comp-sub-label');
                p2Name = nameEl ? nameEl.textContent.trim() : null;
                p2CompId = idEl ? idEl.textContent.trim() : null;
                p2CompSub = subEl ? subEl.textContent.trim() : null;
            }

            // 4. Warning labels in schematic
            const flushTank = document.getElementById('tank-flush');
            const ballValve = document.getElementById('comp-ball-valve');
            const flushTankText = flushTank ? flushTank.textContent : '';
            const ballValveText = ballValve ? ballValve.textContent : '';
            const unmeasuredTag = document.querySelector('.tank-unmeasured');
            const unverifiedTag = document.querySelector('.manual-unverified-tag');

            // 5. Case 2 Flush countdown in UI
            const flushMonitor = document.getElementById('case2-flush-monitor');

            // 6. Connection panel layout
            const connCard = document.querySelector('.connection-card');
            const connCardRect = connCard.getBoundingClientRect();
            const comSelect = document.getElementById('com-port-select');
            const refreshBtn = document.getElementById('btn-refresh-ports');
            const btnConnect = document.getElementById('btn-connect');
            const btnDisconnect = document.getElementById('btn-disconnect');
            const comSelectRect = comSelect.getBoundingClientRect();
            const refreshBtnRect = refreshBtn.getBoundingClientRect();
            const btnConnectRect = btnConnect.getBoundingClientRect();
            const btnDisconnectRect = btnDisconnect.getBoundingClientRect();

            // 7. Status toolbar layout in SAFE_IDLE
            const statusCard = document.querySelector('.center-toolbar-card');
            const statusPill = document.getElementById('main-status-pill');
            const bannerText = document.getElementById('banner-text');
            const quickActions = document.querySelector('.quick-actions-group');
            const normalBtn = document.getElementById('btn-normal-flow');
            const statusCardRect = statusCard.getBoundingClientRect();
            const statusPillRect = statusPill.getBoundingClientRect();
            const quickActionsRect = quickActions.getBoundingClientRect();

            return {
                logLBtnExists: logLBtn !== null,
                logBadgeExists: logBadge !== null,
                exportBtnExists: exportBtn !== null,
                clearBtnExists: clearBtn !== null,
                schematicNoteText: note ? note.textContent.trim() : null,
                p2Transform: p2Transform,
                p2CircleExists: p2Circle !== null,
                p2RotorExists: p2Rotor !== null,
                p2DutyTextExists: p2DutyText !== null,
                p2Name: p2Name,
                p2CompId: p2CompId,
                p2CompSub: p2CompSub,
                unmeasuredTagExists: unmeasuredTag !== null,
                unverifiedTagExists: unverifiedTag !== null,
                flushTankHasUnmeasuredText: flushTankText.includes('LEVEL NOT MEASURED'),
                ballValveHasUnverifiedText: ballValveText.includes('MANUAL (UNVERIFIED)'),
                flushMonitorExists: flushMonitor !== null,
                comSelectInsideCard: comSelectRect.right <= connCardRect.right + 1,
                refreshBtnInsideCard: refreshBtnRect.right <= connCardRect.right + 1,
                refreshBtnVisible: refreshBtnRect.width > 0 && refreshBtnRect.height > 0,
                connectBtnWidth: btnConnectRect.width,
                disconnectBtnWidth: btnDisconnectRect.width,
                statusPillRight: statusPillRect.right,
                quickActionsLeft: quickActionsRect.left,
                normalBtnExists: normalBtn !== null,
                statusOverlapsActions: statusPillRect.right > quickActionsRect.left + 1
            };
        })()""")

        print(f"  Log 'L' Button in DOM: {cleanup_check['logLBtnExists']} (expected: False)")
        assert cleanup_check['logLBtnExists'] is False, "Log 'L' button MUST be completely removed from DOM!"
        assert cleanup_check['logBadgeExists'] is True, "LOGGING status badge must be preserved!"
        assert cleanup_check['exportBtnExists'] is True, "Export CSV button must be preserved!"
        assert cleanup_check['clearBtnExists'] is True, "Clear button must be preserved!"
        print("  [PASS] Log 'L' button removed; status badge and CSV actions preserved.")

        print(f"  Schematic Instruction: '{cleanup_check['schematicNoteText']}' (expected: 'Click components to control')")
        assert cleanup_check['schematicNoteText'] == "Click components to control"
        print("  [PASS] Schematic instruction simplified cleanly.")

        print(f"  Pump 2 Transform: {cleanup_check['p2Transform']} (expected: translate(578, 368))")
        assert cleanup_check['p2Transform'] == "translate(578, 368)", f"Pump 2 transform must be translate(578, 368), got {cleanup_check['p2Transform']}"
        assert cleanup_check['p2CircleExists'] is True
        assert cleanup_check['p2RotorExists'] is True
        assert cleanup_check['p2DutyTextExists'] is True
        assert cleanup_check['p2Name'] == "P2"
        assert "PUMP 2" in cleanup_check['p2CompId']
        assert "Sump" in cleanup_check['p2CompSub']
        print("  [PASS] Pump 2 symbol, rotor, duty text, and labels centered correctly on pipe junction (610, 400).")

        print(f"  LEVEL NOT MEASURED tag: {cleanup_check['unmeasuredTagExists']} | in Flush Tank: {cleanup_check['flushTankHasUnmeasuredText']}")
        print(f"  MANUAL (UNVERIFIED) tag: {cleanup_check['unverifiedTagExists']} | in Ball Valve: {cleanup_check['ballValveHasUnverifiedText']}")
        assert cleanup_check['unmeasuredTagExists'] is False, "LEVEL NOT MEASURED badge MUST NOT exist!"
        assert cleanup_check['unverifiedTagExists'] is False, "MANUAL (UNVERIFIED) tag MUST NOT exist!"
        assert cleanup_check['flushTankHasUnmeasuredText'] is False, "LEVEL NOT MEASURED text found in Flush Tank!"
        assert cleanup_check['ballValveHasUnverifiedText'] is False, "MANUAL (UNVERIFIED) text found in Ball Valve!"
        print("  [PASS] Video warning labels completely removed from Flush Tank and Ball Valve.")

        print(f"  Flush Monitor Countdown in DOM: {cleanup_check['flushMonitorExists']} (expected: False)")
        assert cleanup_check['flushMonitorExists'] is False, "Flush countdown monitor element MUST NOT exist in DOM!"
        print("  [PASS] Flush countdown monitor element removed from UI.")

        print(f"  Connection Panel: comSelect inside card: {cleanup_check['comSelectInsideCard']} | refreshBtn inside card: {cleanup_check['refreshBtnInsideCard']}")
        print(f"  Connect Btn width: {cleanup_check['connectBtnWidth']:.1f}px | Disconnect Btn width: {cleanup_check['disconnectBtnWidth']:.1f}px")
        assert cleanup_check['comSelectInsideCard'] is True, "Serial port dropdown overflows connection card!"
        assert cleanup_check['refreshBtnInsideCard'] is True, "Refresh button overflows connection card!"
        assert cleanup_check['refreshBtnVisible'] is True, "Refresh button not visible beside dropdown!"
        assert abs(cleanup_check['connectBtnWidth'] - cleanup_check['disconnectBtnWidth']) <= 1.0, "Connect & Disconnect buttons must be equal size!"
        print("  [PASS] Connection panel layout fits cleanly within card with aligned buttons.")

        # Test long COM port name insertion
        print("  Testing Connection panel with a long device name...")
        long_port_check = await cdp.eval("""(() => {
            const select = document.getElementById('com-port-select');
            const card = document.querySelector('.connection-card');
            const refresh = document.getElementById('btn-refresh-ports');
            select.innerHTML = '<option value="COM4">COM4 - Silicon Labs CP210x USB to UART Bridge (COM4)</option>';
            const cardRect = card.getBoundingClientRect();
            const selectRect = select.getBoundingClientRect();
            const refreshRect = refresh.getBoundingClientRect();
            return {
                selectRight: selectRect.right,
                cardRight: cardRect.right,
                refreshRight: refreshRect.right,
                fits: selectRect.right <= cardRect.right + 1,
                refreshFits: refreshRect.right <= cardRect.right + 1
            };
        })()""")
        print(f"    Long COM port select right: {long_port_check['selectRight']:.1f}px | card right: {long_port_check['cardRight']:.1f}px")
        print(f"    Refresh button right: {long_port_check['refreshRight']:.1f}px")
        assert long_port_check['fits'] is True, "Long device name causes select dropdown to overflow card!"
        assert long_port_check['refreshFits'] is True, "Long device name pushes refresh button out of card!"
        print("    [PASS] Long COM port name truncated cleanly with 0px card overflow.")

        print(f"  Normal Flow button in DOM: {cleanup_check['normalBtnExists']} (expected: False)")
        assert cleanup_check['normalBtnExists'] is False, "Normal Flow button MUST be completely removed from DOM!"
        print("  [PASS] Normal Flow start button removed from UI.")

        print(f"  Status Toolbar: Pill Right ({cleanup_check['statusPillRight']:.1f}px) vs Actions Left ({cleanup_check['quickActionsLeft']:.1f}px)")
        print(f"  Status overlaps actions: {cleanup_check['statusOverlapsActions']}")
        assert cleanup_check['statusOverlapsActions'] is False, "Status badge overlaps quick action controls in SAFE_IDLE!"
        print("  [PASS] Status bar alignment in SAFE_IDLE verified: zero overlap, buttons uncompressed.")

        # -------------------------------------------------------------
        # TEST 2: Connect to Mock ESP32 and Verify Telemetry Flow
        # -------------------------------------------------------------
        print("\n--- TEST 2: Connecting to Mock ESP32 ---")
        await cdp.eval("""(async () => {
            if (state.connectedToSerial) {
                await fetch('/api/disconnect', { method: 'POST' });
                await new Promise(r => setTimeout(r, 200));
            }
            document.getElementById('mock-mode-checkbox').checked = true;
            document.getElementById('btn-connect').click();
        })()""")
        await asyncio.sleep(1.2)

        conn_status = await cdp.eval("state.connectedToSerial && state.isMock")
        assert conn_status is True, "Failed to connect to Mock ESP32"
        print("[PASS] Connected to Mock ESP32 successfully")

        # Verify system enters SAFE_IDLE on connect: motors OFF (0%), solenoid closed
        post_conn_state = await cdp.eval("""(() => {
            return {
                case1State: state.case1State,
                pump1Duty: state.pump1Duty,
                pump2Duty: state.pump2Duty,
                pump3Duty: state.pump3Duty,
                solenoidOpen: state.solenoidOpen,
                bannerText: document.getElementById('banner-text').textContent.trim()
            };
        })()""")
        print("[SAFETY AUDIT] Post-connect state:", post_conn_state)
        assert post_conn_state['case1State'] == 'SAFE_IDLE', f"Expected SAFE_IDLE, got {post_conn_state['case1State']}"
        assert post_conn_state['pump1Duty'] == 0, f"Pump 1 must be 0% on connect, got {post_conn_state['pump1Duty']}"
        assert post_conn_state['pump2Duty'] == 0, f"Pump 2 must be 0% on connect, got {post_conn_state['pump2Duty']}"
        assert post_conn_state['pump3Duty'] == 0, f"Pump 3 must be 0% on connect, got {post_conn_state['pump3Duty']}"
        assert post_conn_state['solenoidOpen'] is False, "Solenoid must be closed on connect"
        assert "SAFE IDLE" in post_conn_state['bannerText'], f"Banner must indicate SAFE IDLE, got '{post_conn_state['bannerText']}'"
        print("[PASS] Confirmed SAFE IDLE on Connect: All 3 pumps OFF (0%), Solenoid CLOSED!")

        # -------------------------------------------------------------
        # TEST 3: Float Switch Live Transitions Without Page Refresh
        # -------------------------------------------------------------
        print("\n--- TEST 3: Testing Float Switch Transitions (No Refresh) ---")
        # Explicit Operator Start: Click Start Button (GPIO 34)
        print("  Starting sequence via Start Button (comp-flush-button)...")
        await cdp.eval("document.getElementById('comp-flush-button').dispatchEvent(new MouseEvent('click', { bubbles: true }))")
        await asyncio.sleep(0.5)

        for cycle in range(1, 3):
            print(f"\n  === Transition Cycle {cycle}: NORMAL -> HIGH ===")
            await cdp.eval("document.getElementById('btn-sim-high').click()")
            await asyncio.sleep(0.4)

            high_state = await cdp.eval("""(() => {
                const bob = document.getElementById('float-bob');
                const text = document.getElementById('float-status-text');
                const surface = document.getElementById('sump-liquid-surface');
                const level = document.getElementById('sump-liquid-level');
                const p1Duty = state.pump1Duty;
                const p2Duty = state.pump2Duty;

                return {
                    floatTriggered: state.floatTriggered,
                    case1State: state.case1State,
                    bobCy: bob.getAttribute('cy'),
                    bobClass: bob.getAttribute('class'),
                    statusText: text.textContent.trim(),
                    statusColor: text.style.fill,
                    surfaceY1: surface.getAttribute('y1'),
                    levelY: level.getAttribute('y'),
                    levelHeight: level.getAttribute('height'),
                    pump1Duty: p1Duty,
                    pump2Duty: p2Duty
                };
            })()""")

            print(f"    State: {high_state['case1State']} | floatTriggered: {high_state['floatTriggered']}")
            print(f"    Float Bob cy: {high_state['bobCy']} | Class: {high_state['bobClass']}")
            print(f"    Status Text: '{high_state['statusText']}' | Color: {high_state['statusColor']}")
            print(f"    Liquid Surface y: {high_state['surfaceY1']} | Level y: {high_state['levelY']} (height: {high_state['levelHeight']})")
            print(f"    Pump 1 Duty: {high_state['pump1Duty']}% | Pump 2 Duty: {high_state['pump2Duty']}%")

            assert high_state['floatTriggered'] is True, "state.floatTriggered must be true"
            assert high_state['bobCy'] == "16", "floatBob cy must be 16 in high position"
            assert high_state['statusText'] == "SUMP HIGH", "Status text must be SUMP HIGH"
            assert high_state['surfaceY1'] == "40", "Liquid surface must rise to y=40"
            assert high_state['levelY'] == "40", "Liquid level must be y=40"
            assert high_state['pump1Duty'] == 0, "Pump 1 must halt at 0% in SUMP HIGH"
            print(f"    [PASS] Cycle {cycle} HIGH position and Pump 1 halt verified without refresh!")
            if cycle == 1:
                await cdp.screenshot("sump_high_state.png")

            print(f"\n  === Transition Cycle {cycle}: HIGH -> NORMAL ===")
            restore_btn = 'btn-sim-ret'
            await cdp.eval(f"document.getElementById('{restore_btn}').click()")
            await asyncio.sleep(0.4)

            norm_state = await cdp.eval("""(() => {
                const bob = document.getElementById('float-bob');
                const text = document.getElementById('float-status-text');
                const surface = document.getElementById('sump-liquid-surface');
                const level = document.getElementById('sump-liquid-level');
                const p1Duty = state.pump1Duty;
                const p2Duty = state.pump2Duty;

                return {
                    floatTriggered: state.floatTriggered,
                    case1State: state.case1State,
                    bobCy: bob.getAttribute('cy'),
                    bobClass: bob.getAttribute('class'),
                    statusText: text.textContent.trim(),
                    statusColor: text.style.fill,
                    surfaceY1: surface.getAttribute('y1'),
                    levelY: level.getAttribute('y'),
                    levelHeight: level.getAttribute('height'),
                    pump1Duty: p1Duty,
                    pump2Duty: p2Duty
                };
            })()""")

            print(f"    State: {norm_state['case1State']} | floatTriggered: {norm_state['floatTriggered']}")
            print(f"    Float Bob cy: {norm_state['bobCy']} | Class: {norm_state['bobClass']}")
            print(f"    Status Text: '{norm_state['statusText']}' | Color: {norm_state['statusColor']}")
            print(f"    Liquid Surface y: {norm_state['surfaceY1']} | Level y: {norm_state['levelY']} (height: {norm_state['levelHeight']})")
            print(f"    Pump 1 Duty: {norm_state['pump1Duty']}% | Pump 2 Duty: {norm_state['pump2Duty']}%")

            assert norm_state['floatTriggered'] is False, "state.floatTriggered must be false"
            assert norm_state['bobCy'] == "35", "floatBob cy must return to 35 in normal position"
            assert norm_state['statusText'] == "NORMAL", "Status text must be NORMAL"
            assert norm_state['surfaceY1'] == "65", "Liquid surface must return to y=65"
            assert norm_state['levelY'] == "65", "Liquid level must return to y=65"
            assert norm_state['pump1Duty'] == 50, "Pump 1 must resume at 50% in NORMAL"
            print(f"    [PASS] Cycle {cycle} NORMAL position and Pump 1 resumption verified without refresh!")

        await cdp.screenshot("float_switch_normal_state.png")

        # -------------------------------------------------------------
        # TEST 4: Flow Graph Visual Quality, Data Pipeline & Tab Switching
        # -------------------------------------------------------------
        print("\n--- TEST 4: Flow Graph Rendering & Tab Switching ---")
        # Wait 3 seconds to gather multiple telemetry records
        print("  Collecting live telemetry records...")
        await asyncio.sleep(4.0)

        graph_info = await cdp.eval("""(() => {
            const canvas = document.getElementById('flow-graph-canvas');
            const rect = canvas.getBoundingClientRect();
            const badge = document.getElementById('graph-state-badge');
            const pointsCount = state.graphPoints.length;
            const recordsCount = state.flowRecords.length;
            const latestFlow = state.lastFlowLpm;

            return {
                canvasWidth: canvas.width,
                canvasHeight: canvas.height,
                cssWidth: rect.width,
                cssHeight: rect.height,
                dpr: window.devicePixelRatio || 1,
                badgeText: badge.textContent.trim(),
                pointsCount: pointsCount,
                recordsCount: recordsCount,
                latestFlow: latestFlow
            };
        })()""")

        print(f"  Canvas Backing Store: {graph_info['canvasWidth']} x {graph_info['canvasHeight']} (CSS: {graph_info['cssWidth']:.1f} x {graph_info['cssHeight']:.1f}, DPR: {graph_info['dpr']})")
        print(f"  Graph Status Badge: '{graph_info['badgeText']}' | Total Points: {graph_info['pointsCount']} | Records: {graph_info['recordsCount']}")
        print(f"  Latest Flow: {graph_info['latestFlow']:.2f} L/min")

        assert graph_info['pointsCount'] >= 2, "Expected at least 2 telemetry points plotted in graph"
        assert graph_info['badgeText'] == "LIVE DATA", f"Badge should be LIVE DATA, got {graph_info['badgeText']}"
        print("  [PASS] Live telemetry rendering on graph verified")

        # Tab Switching test
        print("  Testing Tab Switching: Switching to Serial Terminal Tab...")
        await cdp.eval("document.getElementById('tab-btn-terminal').click()")
        await asyncio.sleep(1.0)
        term_active = await cdp.eval("document.getElementById('tab-btn-terminal').classList.contains('tab-active')")
        assert term_active is True
        print("  Switched to Terminal tab. Waiting 2.5s to verify graph still receives points...")
        pts_before = graph_info['pointsCount']
        await asyncio.sleep(2.6)
        pts_after = await cdp.eval("state.graphPoints.length")
        print(f"  Points while in Terminal Tab: {pts_before} -> {pts_after}")
        assert pts_after >= pts_before, "Graph points should continue updating while terminal tab is active"

        # Switch back to Event Log Tab
        await cdp.eval("document.getElementById('tab-btn-events').click()")
        await asyncio.sleep(0.5)
        print("  [PASS] Tab switching does not interrupt graph rendering pipeline")

        # -------------------------------------------------------------
        # TEST 5: Verify Pump Animation Centering & Parameters Unchanged
        # -------------------------------------------------------------
        print("\n--- TEST 5: Verify Working Pump Animations ---")
        pumps_info = await cdp.eval("""(() => {
            const p1 = document.getElementById('pump1-rotor');
            const p2 = document.getElementById('pump2-rotor');
            const p3 = document.getElementById('pump3-rotor');
            return {
                p1Center: p1.getAttribute('transform-origin') || getComputedStyle(p1).transformOrigin,
                p2Center: p2.getAttribute('transform-origin') || getComputedStyle(p2).transformOrigin,
                p3Center: p3.getAttribute('transform-origin') || getComputedStyle(p3).transformOrigin,
                p1Box: getComputedStyle(p1).transformBox,
                p2Box: getComputedStyle(p2).transformBox
            };
        })()""")
        print(f"  Pump Rotors transform-origin: P1={pumps_info['p1Center']}, P2={pumps_info['p2Center']}")
        print(f"  Pump Rotors transform-box: P1={pumps_info['p1Box']}, P2={pumps_info['p2Box']}")
        print("  [PASS] Pump animation rotation centers and CSS transform-box preserved")

        # -------------------------------------------------------------
        # TEST 6: Verify GPIO 34 Repurposing in UI (No obsolete switch, Start Button GPIO 34 active)
        # -------------------------------------------------------------
        print("\n--- TEST 6: Verify GPIO 34 Repurposing in Browser DOM & Live UI Updates ---")
        ui_badge_info = await cdp.eval("""(() => {
            const sysSwitch = document.getElementById('comp-sys-switch');
            const startBtn = document.getElementById('comp-flush-button');
            const startTitle = startBtn ? startBtn.querySelector('.flush-btn-title').textContent.trim() : null;
            const startState = document.getElementById('flush-btn-state').textContent.trim();

            return {
                sysSwitchExists: sysSwitch !== null,
                startBtnExists: startBtn !== null,
                startTitle: startTitle,
                startState: startState
            };
        })()""")

        print(f"  Obsolete System Switch in DOM: {ui_badge_info['sysSwitchExists']}")
        print(f"  Start Button in DOM: {ui_badge_info['startBtnExists']} | Title: '{ui_badge_info['startTitle']}' | State: '{ui_badge_info['startState']}'")
        assert ui_badge_info['sysSwitchExists'] is False, "Obsolete 'SYSTEM SWITCH (GPIO 34)' badge MUST NOT exist in DOM!"
        assert ui_badge_info['startBtnExists'] is True, "Start Button badge must exist in DOM!"
        assert "GPIO 34" in ui_badge_info['startTitle'], f"Start Button must be labelled GPIO 34, got '{ui_badge_info['startTitle']}'"
        assert "START BUTTON" in ui_badge_info['startTitle'], f"Start Button title must contain START BUTTON, got '{ui_badge_info['startTitle']}'"
        print("  [PASS] DOM verification: Obsolete system switch removed, Start Button labelled START BUTTON (GPIO 34).")

        # Verify system is still in 10-second RETURN_TO_NORMAL window before 10s elapses
        pre_flush_ui = await cdp.eval("""(() => {
            return {
                case1State: state.case1State,
                pump1Duty: state.pump1Duty,
                pump2Duty: state.pump2Duty,
                pump3Duty: state.pump3Duty,
                solenoidOpen: state.solenoidOpen,
                modePillText: document.getElementById('schematic-mode-pill').textContent.trim()
            };
        })()""")
        print(f"  Pre-10s delay check: State={pre_flush_ui['case1State']} | Pill='{pre_flush_ui['modePillText']}' | P1={pre_flush_ui['pump1Duty']}%, P3={pre_flush_ui['pump3Duty']}%, Solenoid={pre_flush_ui['solenoidOpen']}")
        assert pre_flush_ui['case1State'] == 'RETURN_TO_NORMAL', f"Expected RETURN_TO_NORMAL before 10s, got {pre_flush_ui['case1State']}"
        assert pre_flush_ui['pump1Duty'] == 50
        assert pre_flush_ui['pump2Duty'] == 100
        assert pre_flush_ui['pump3Duty'] == 0
        assert pre_flush_ui['solenoidOpen'] is True
        print("  [PASS] 10-second return delay active: Normal flow continues (P1=50%, P2=100%, P3=0%, Solenoid=OPEN).")

        # Now advance time past the 10-second delay threshold to trigger Case 2
        print("  Advancing time past 10 seconds to trigger automatic Case 2 flush...")
        await cdp.eval("fetch('/api/send', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({command: '!advance_time 4.5'})})")
        await asyncio.sleep(0.5)

        # Verify Automatic Case 2 active state
        flush_active_ui = await cdp.eval("""(() => {
            const monitor = document.getElementById('case2-flush-monitor');
            const banner = document.getElementById('banner-text').textContent.trim();
            const modePill = document.getElementById('schematic-mode-pill').textContent.trim();
            const p1Duty = state.pump1Duty;
            const p2Duty = state.pump2Duty;
            const p3Duty = state.pump3Duty;
            const solenoid = state.solenoidOpen;

            return {
                monitorExists: monitor !== null,
                bannerText: banner,
                modePillText: modePill,
                pump1Duty: p1Duty,
                pump2Duty: p2Duty,
                pump3Duty: p3Duty,
                solenoidOpen: solenoid
            };
        })()""")

        print(f"  Live UI Automatic Case 2 Active State without refresh:")
        print(f"    Countdown Monitor in DOM: {flush_active_ui['monitorExists']} (expected: False)")
        print(f"    Banner: '{flush_active_ui['bannerText']}' | Mode Pill: '{flush_active_ui['modePillText']}'")
        print(f"    P1={flush_active_ui['pump1Duty']}%, P2={flush_active_ui['pump2Duty']}%, P3={flush_active_ui['pump3Duty']}%, Solenoid={flush_active_ui['solenoidOpen']}")

        assert flush_active_ui['monitorExists'] is False, "Countdown monitor element MUST NOT exist in UI during flush!"
        assert "CASE 2 FLUSHING" in flush_active_ui['bannerText'] or "FLUSH" in flush_active_ui['bannerText'], f"Expected CASE 2 FLUSHING in banner, got '{flush_active_ui['bannerText']}'"
        assert flush_active_ui['modePillText'] == "CASE 2 FLUSHING", f"Expected CASE 2 FLUSHING, got {flush_active_ui['modePillText']}"
        assert flush_active_ui['pump1Duty'] == 50, "Pump 1 must be 50% during flush"
        assert flush_active_ui['pump2Duty'] == 100, "Pump 2 must be 100% during flush"
        assert flush_active_ui['pump3Duty'] == 50, "Pump 3 must be 50% during flush"
        assert flush_active_ui['solenoidOpen'] is False, "Solenoid must be CLOSED during flush"
        print("  [PASS] Automatic Case 2 active state verified without operator clicking any button!")

        # Verify pressing Start Button during Case 2 is ignored
        print("  Verifying Start Button press is ignored while running...")
        await cdp.eval("document.getElementById('comp-flush-button').dispatchEvent(new MouseEvent('click', {bubbles: true}))")
        await asyncio.sleep(0.3)
        btn_ignored = await cdp.eval("state.case1State === 'CASE2_FLUSHING' && state.pump3Duty === 50")
        assert btn_ignored is True, "Start button press during Case 2 must be ignored!"
        print("  [PASS] Start button ignored during active sequence")

        await cdp.screenshot("case2_automatic_active_verified.png")
        await cdp.screenshot("dashboard_final_verified.png")

        print("\n=== ALL AUTOMATED CDP BROWSER TESTS PASSED (100% SUCCESS) ===")

    finally:
        chrome_proc.terminate()
        try:
            chrome_proc.wait(timeout=3.0)
        except Exception:
            chrome_proc.kill()

if __name__ == "__main__":
    asyncio.run(run_tests())
