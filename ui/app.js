/**
 * LRC Hardware Controller - Light Industrial SCADA Dashboard Frontend
 * Real-time monitoring, direct hydraulic schematic control, live flow graph, and CSV telemetry.
 */

(function () {
  'use strict';

  // Application State
  const state = {
    ws: null,
    connectedToBridge: false,
    connectedToSerial: false,
    isMock: false,
    port: null,
    baud: 115200,

    // Hardware Subsystem States (Strict SAFE_IDLE startup default)
    systemOn: true,
    floatTriggered: false,
    solenoidOpen: false,
    pump1Duty: 0,
    pump2Duty: 0,
    pump3Duty: 0,
    case1State: 'SAFE_IDLE',
    estopActive: false,
    csvLogging: false,

    // Telemetry
    lastFlowLpm: 0.0,
    lastFlowHz: 0.0,
    lastPwm: 100,
    lastReadingTime: 0,

    // Case 2 Flush Sequence
    case2Flushing: false,
    case2FlushStartTime: 0,
    case2FlushDuration: 90.0,
    case2Shutdown: false,
    countdownTimerId: null,

    // Data Storage
    flowRecords: [],     // All records in session for CSV export
    latest10Records: [], // Exactly latest 10 for table
    graphPoints: [],     // Rolling 60s points for canvas graph

    // Active Tab
    activeTab: 'events'
  };
  window.state = state;

  // DOM Elements
  const el = {
    bridgePill: document.getElementById('bridge-pill'),
    bridgePillText: document.getElementById('bridge-pill-text'),
    serialPill: document.getElementById('serial-pill'),
    serialPillText: document.getElementById('serial-pill-text'),
    mainStatusPill: document.getElementById('main-status-pill'),
    bannerText: document.getElementById('banner-text'),
    topEstopBtn: document.getElementById('btn-top-estop'),
    activityLed: document.getElementById('activity-led'),

    // Connection
    comPortSelect: document.getElementById('com-port-select'),
    btnRefreshPorts: document.getElementById('btn-refresh-ports'),
    mockCheckbox: document.getElementById('mock-mode-checkbox'),
    btnConnect: document.getElementById('btn-connect'),
    btnDisconnect: document.getElementById('btn-disconnect'),
    connStateDetail: document.getElementById('conn-state-detail'),

    // Table
    flowTableBody: document.getElementById('flow-table-body'),
    logStatusBadge: document.getElementById('log-status-badge'),
    btnExportCsv: document.getElementById('btn-export-csv'),
    btnClearTable: document.getElementById('btn-clear-table'),

    // Center Action Bar & Flush Monitor
    case2FlushMonitor: document.getElementById('case2-flush-monitor'),
    flushSeconds: document.getElementById('flush-seconds'),
    flushProgressFill: document.getElementById('flush-progress-fill'),
    btnSimNorm: document.getElementById('btn-sim-norm'),
    btnSimHigh: document.getElementById('btn-sim-high'),
    btnSimRet: document.getElementById('btn-sim-ret'),
    btnQueryAll: document.getElementById('btn-query-all'),

    // Schematic Elements
    pump1Group: document.getElementById('comp-pump1'),
    pump1DutyText: document.getElementById('pump1-duty-text'),
    pump1Rotor: document.getElementById('pump1-rotor'),
    pump2Group: document.getElementById('comp-pump2'),
    pump2DutyText: document.getElementById('pump2-duty-text'),
    pump2Rotor: document.getElementById('pump2-rotor'),
    pump3Group: document.getElementById('comp-pump3'),
    pump3DutyText: document.getElementById('pump3-duty-text'),
    pump3Rotor: document.getElementById('pump3-rotor'),
    flowP1: document.getElementById('flow-p1'),
    flowP2: document.getElementById('flow-p2'),
    flowP2Tank: document.getElementById('flow-p2-tank'),
    flowP3: document.getElementById('flow-p3'),
    solenoidComp: document.getElementById('comp-solenoid'),
    solenoidSymbol: document.getElementById('solenoid-symbol'),
    solenoidStatusText: document.getElementById('solenoid-status-text'),
    flowSensorComp: document.getElementById('comp-flow-sensor'),
    flowSensorCircle: document.getElementById('flow-sensor-circle'),
    schematicFlowVal: document.getElementById('schematic-flow-val'),
    floatBob: document.getElementById('float-bob'),
    floatStatusText: document.getElementById('float-status-text'),
    sumpLiquidSurface: document.getElementById('sump-liquid-surface'),
    sumpLiquidLevel: document.getElementById('sump-liquid-level'),
    sysSwitchLed: document.getElementById('sys-switch-led'),
    sysSwitchState: document.getElementById('sys-switch-state'),
    flushBtnComp: document.getElementById('comp-flush-button'),
    flushBtnLed: document.getElementById('flush-btn-led'),
    flushBtnState: document.getElementById('flush-btn-state'),
    schematicModePill: document.getElementById('schematic-mode-pill'),
    popover: document.getElementById('comp-popover'),
    popoverTitle: document.getElementById('popover-title'),
    popoverBody: document.getElementById('popover-body'),
    popoverClose: document.getElementById('popover-close'),

    // Graph
    graphCanvas: document.getElementById('flow-graph-canvas'),
    graphStateBadge: document.getElementById('graph-state-badge'),
    metricFlowVal: document.getElementById('metric-flow-val'),
    metricFreqVal: document.getElementById('metric-freq-val'),
    metricPwmVal: document.getElementById('metric-pwm-val'),

    // Terminal / Events
    tabBtnEvents: document.getElementById('tab-btn-events'),
    tabBtnTerminal: document.getElementById('tab-btn-terminal'),
    tabContentEvents: document.getElementById('tab-content-events'),
    tabContentTerminal: document.getElementById('tab-content-terminal'),
    eventLogContainer: document.getElementById('event-log-container'),
    rawTerminalOutput: document.getElementById('raw-terminal-output'),
    termInput: document.getElementById('term-input'),
    btnTermSend: document.getElementById('btn-term-send'),
    btnClearTerm: document.getElementById('btn-clear-term')
  };

  let canvasCtx = null;

  // Initialize Application
  function init() {
    window.__scada = { state, el, renderFlowGraph };
    try {
      initCanvas();
      setupEventListeners();
      connectWebSocket();
      refreshComPorts();
      renderSchematic();
      updateMainStatusBanner();
      startCanvasLoop();
    } catch (err) {
      console.error('Init error:', err);
      window.__initError = String(err);
    }
  }


  // WebSocket Connection
  function connectWebSocket() {
    const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProto}//${location.host}/ws`;

    try {
      state.ws = new WebSocket(wsUrl);

      state.ws.onopen = () => {
        state.connectedToBridge = true;
        updateBridgePill(true);
        addEventLog('Connected to Local Serial Bridge.', 'success');
      };

      state.ws.onmessage = (event) => {
        flashActivityLed();
        try {
          const msg = JSON.parse(event.data);
          handleBridgeMessage(msg);
        } catch (e) {
          console.error('Invalid JSON from bridge:', e);
        }
      };

      state.ws.onclose = () => {
        state.connectedToBridge = false;
        state.connectedToSerial = false;
        updateBridgePill(false);
        updateSerialPill(false);
        addEventLog('Bridge WebSocket disconnected. Retrying in 2s...', 'warn');
        setTimeout(connectWebSocket, 2000);
      };

      state.ws.onerror = () => {
        state.connectedToBridge = false;
        updateBridgePill(false);
      };
    } catch (err) {
      console.warn('WebSocket init error:', err);
      setTimeout(connectWebSocket, 2000);
    }
  }

  // Bridge Message Dispatcher
  function handleBridgeMessage(msg) {
    switch (msg.type) {
      case 'initial_state':
        syncState(msg);
        break;

      case 'connection_status':
        state.connectedToSerial = msg.connected;
        state.port = msg.port;
        state.isMock = msg.is_mock;
        updateSerialPill(msg.connected, msg.port, msg.is_mock);
        if (msg.connected) {
          sendCommand('p');
        } else {
          state.flowRecords = [];
          state.latest10Records = [];
          state.graphPoints = [];
        }
        renderSchematic();
        updateMainStatusBanner();
        renderFlowGraph();
        break;

      case 'flow_record':
        handleFlowRecord(msg);
        break;

      case 'raw_serial':
        handleRawSerial(msg.line, msg.is_mock);
        break;

      case 'heartbeat':
        syncState(msg.data);
        break;

      case 'state_change':
        state.case1State = msg.state;
        if (msg.pump1 !== undefined) state.pump1Duty = msg.pump1;
        if (msg.pump2 !== undefined) state.pump2Duty = msg.pump2;
        if (msg.pump3 !== undefined) state.pump3Duty = msg.pump3;
        if (msg.solenoid !== undefined) state.solenoidOpen = msg.solenoid;
        if (msg.float_triggered !== undefined) {
          state.floatTriggered = msg.float_triggered;
        } else if (msg.state === 'SUMP_HIGH') {
          state.floatTriggered = true;
        } else if (msg.state === 'NORMAL' || msg.state === 'RETURN_TO_NORMAL') {
          state.floatTriggered = false;
        }
        addEventLog(`Case 1 State: ${msg.state}`, 'info');
        renderSchematic();
        updateMainStatusBanner();
        break;

      case 'pump_update':
        if (msg.pump === 1) state.pump1Duty = msg.duty;
        if (msg.pump === 2) state.pump2Duty = msg.duty;
        if (msg.pump === 3) state.pump3Duty = msg.duty;
        addEventLog(`[PUMP ${msg.pump}] Duty set to ${msg.duty}%.`, 'info');
        renderSchematic();
        break;

      case 'case2_flush_start':
        state.case2Flushing = true;
        state.case2Shutdown = false;
        state.case1State = 'CASE2_FLUSHING';
        if (msg.pump1_duty !== undefined) state.pump1Duty = msg.pump1_duty;
        if (msg.pump2_duty !== undefined) state.pump2Duty = msg.pump2_duty;
        if (msg.pump3_duty !== undefined) state.pump3Duty = msg.pump3_duty;
        if (msg.solenoid_open !== undefined) state.solenoidOpen = msg.solenoid_open;
        startCase2Countdown(msg.duration_s || 90);
        addEventLog(`Case 2 ${msg.duration_s || 90}-second flush sequence started!`, 'warn');
        renderSchematic();
        updateMainStatusBanner();
        break;

      case 'case2_flush_complete':
        state.case2Flushing = false;
        state.case2Shutdown = true;
        state.case1State = 'CASE2_SHUTDOWN';
        state.pump1Duty = 0;
        state.pump2Duty = 0;
        state.pump3Duty = 0;
        state.solenoidOpen = false;
        endCase2Countdown();
        renderSchematic();
        updateMainStatusBanner();
        addEventLog('Case 2 flush complete. System in shutdown.', 'error');
        break;

      case 'estop_change':
        state.estopActive = msg.active;
        if (msg.active) {
          state.case1State = 'EMERGENCY_STOP';
          state.pump1Duty = 0;
          state.pump2Duty = 0;
          state.pump3Duty = 0;
          state.solenoidOpen = false;
          addEventLog('EMERGENCY STOP TRIPPED: All pumps halted, Solenoid closed.', 'error');
        } else {
          addEventLog('Emergency stop cleared.', 'info');
        }
        renderSchematic();
        updateMainStatusBanner();
        break;

      case 'solenoid_change':
        state.solenoidOpen = msg.open;
        addEventLog(`Solenoid: ${msg.open ? 'OPEN' : 'CLOSED'}.`, 'info');
        renderSchematic();
        break;

      case 'system_switch':
        state.systemOn = msg.system_on;
        addEventLog(`System switch: ${msg.system_on ? 'ON' : 'OFF'}.`, 'info');
        renderSchematic();
        updateMainStatusBanner();
        break;

      case 'float_switch':
        state.floatTriggered = msg.triggered;
        addEventLog(`Float switch: ${msg.triggered ? 'SUMP HIGH' : 'NORMAL'}.`, msg.triggered ? 'warn' : 'info');
        renderSchematic();
        updateMainStatusBanner();
        break;

      case 'csv_logging':
        state.csvLogging = msg.active;
        updateLoggingBadge(msg.active);
        addEventLog(`CSV flow logging ${msg.active ? 'STARTED' : 'STOPPED'}.`, 'info');
        break;

      case 'flow_oneshot':
        state.lastFlowLpm = msg.flow_lpm;
        state.lastFlowHz = msg.frequency_hz;
        state.lastReadingTime = Date.now();
        renderSchematic();
        updateGraphMetrics(msg.flow_lpm, msg.frequency_hz, state.lastPwm);
        break;

      case 'error':
        addEventLog(`Error: ${msg.message}`, 'error');
        break;
    }
  }

  // State Synchronizer
  function syncState(s) {
    if (s.connected !== undefined) state.connectedToSerial = s.connected;
    if (s.port !== undefined) state.port = s.port;
    if (s.is_mock !== undefined) state.isMock = s.is_mock;
    if (s.system_on !== undefined) state.systemOn = s.system_on;
    if (s.float_triggered !== undefined) state.floatTriggered = s.float_triggered;
    if (s.solenoid_open !== undefined) state.solenoidOpen = s.solenoid_open;
    if (s.pump1_duty !== undefined) state.pump1Duty = s.pump1_duty;
    if (s.pump2_duty !== undefined) state.pump2Duty = s.pump2_duty;
    if (s.pump3_duty !== undefined) state.pump3Duty = s.pump3_duty;
    if (s.case1_state !== undefined) state.case1State = s.case1_state;
    if (s.estop_active !== undefined) state.estopActive = s.estop_active;
    if (s.case2_flushing !== undefined) state.case2Flushing = s.case2_flushing;
    if (s.case2_shutdown !== undefined) state.case2Shutdown = s.case2_shutdown;
    if (s.csv_logging !== undefined) {
      state.csvLogging = s.csv_logging;
      updateLoggingBadge(s.csv_logging);
    }
    if (s.last_flow_lpm !== undefined) state.lastFlowLpm = s.last_flow_lpm;
    if (s.last_flow_hz !== undefined) state.lastFlowHz = s.last_flow_hz;

    updateSerialPill(state.connectedToSerial, state.port, state.isMock);
    renderSchematic();
    updateMainStatusBanner();
    renderFlowGraph();
  }

  // Handle incoming CSV flow record
  function handleFlowRecord(rec) {
    const nowSec = Date.now() / 1000;
    const record = {
      timestamp_ms: rec.timestamp_ms,
      pump2_pwm: rec.pump2_pwm,
      frequency_hz: rec.frequency_hz,
      flow_lpm: rec.flow_lpm,
      arrival: nowSec
    };

    state.lastFlowLpm = rec.flow_lpm;
    state.lastFlowHz = rec.frequency_hz;
    state.lastPwm = rec.pump2_pwm;
    state.lastReadingTime = Date.now();

    state.flowRecords.push(record);

    // Keep exactly latest 10 records (newest at top)
    state.latest10Records.unshift(record);
    if (state.latest10Records.length > 10) {
      state.latest10Records.pop();
    }

    // Add to rolling graph points
    state.graphPoints.push({
      time: record.arrival,
      flow: record.flow_lpm
    });

    // Prune points older than 60s
    const cutoff = nowSec - 60;
    while (state.graphPoints.length > 0 && state.graphPoints[0].time < cutoff) {
      state.graphPoints.shift();
    }

    renderFlowTable(true);
    renderSchematic();
    renderFlowGraph();
    updateGraphMetrics(record.flow_lpm, record.frequency_hz, record.pump2_pwm);
  }

  // Render Table with exactly 10 visible rows
  function renderFlowTable(flashFirst = false) {
    if (state.latest10Records.length === 0) {
      el.flowTableBody.innerHTML = '<tr class="empty-row"><td colspan="4">Waiting for CSV stream (Send \'L\' to log)</td></tr>';
      return;
    }

    let html = '';
    state.latest10Records.forEach((r, idx) => {
      const flashClass = (flashFirst && idx === 0) ? ' class="new-record-flash"' : '';
      html += `<tr${flashClass}>
        <td>${r.timestamp_ms}</td>
        <td>${r.pump2_pwm}%</td>
        <td>${r.frequency_hz.toFixed(1)}</td>
        <td><strong>${r.flow_lpm.toFixed(2)}</strong></td>
      </tr>`;
    });

    el.flowTableBody.innerHTML = html;
  }

  // Raw serial terminal stream
  function handleRawSerial(line, isMock) {
    const pre = el.rawTerminalOutput;
    const prefix = isMock ? '[MOCK] ' : '';
    pre.textContent += prefix + line + '\n';
    if (pre.textContent.length > 20000) {
      pre.textContent = pre.textContent.substring(pre.textContent.length - 15000);
    }
    pre.scrollTop = pre.scrollHeight;

    // Direct fallback parsing for CSV telemetry line
    const csvMatch = line.trim().match(/^(\d+),(\d+),([\d\.]+),([\d\.]+)$/);
    if (csvMatch) {
      const ts = parseInt(csvMatch[1]);
      if (state.latest10Records.length === 0 || state.latest10Records[0].timestamp_ms !== ts) {
        handleFlowRecord({
          timestamp_ms: ts,
          pump2_pwm: parseInt(csvMatch[2]),
          frequency_hz: parseFloat(csvMatch[3]),
          flow_lpm: parseFloat(csvMatch[4])
        });
      }
    }

    // Direct serial line parsing for telemetry & pump duty changes
    const p1m = line.match(/\[PUMP 1\] Duty set to (\d+)%/i);
    if (p1m) { state.pump1Duty = parseInt(p1m[1]); renderSchematic(); }
    if (/\[PUMP 1\] Driver DISABLED/i.test(line)) { state.pump1Duty = 0; renderSchematic(); }

    const p2m = line.match(/\[PUMP 2\] Duty set to (\d+)%/i);
    if (p2m) { state.pump2Duty = parseInt(p2m[1]); renderSchematic(); }
    if (/\[PUMP 2\] Driver DISABLED/i.test(line)) { state.pump2Duty = 0; renderSchematic(); }

    if (/\[PUMP 3\] (?:Stopped|STOPPED)/i.test(line)) { state.pump3Duty = 0; renderSchematic(); }
    const p3start = line.match(/\[CASE 2\] PUMP 3 STARTED at (\d+)%/i);
    if (p3start) {
      state.pump3Duty = parseInt(p3start[1]);
      state.case2Flushing = true;
      state.case1State = 'CASE2_FLUSHING';
      state.solenoidOpen = false;
      renderSchematic();
      updateMainStatusBanner();
    }
    if (/\[CASE 2\] All pumps STOPPED/i.test(line)) {
      state.pump1Duty = 0;
      state.pump2Duty = 0;
      state.pump3Duty = 0;
      state.case2Flushing = false;
      state.case2Shutdown = true;
      state.case1State = 'CASE2_SHUTDOWN';
      renderSchematic();
      updateMainStatusBanner();
    }

    const nfm = line.match(/NORMAL FLOW -> Pump 1:\s*(\d+)%\s*\|\s*Pump 2:\s*(\d+)%/i);
    if (nfm) {
      state.pump1Duty = parseInt(nfm[1]);
      state.pump2Duty = parseInt(nfm[2]);
      state.case1State = 'NORMAL';
      state.floatTriggered = false;
      state.case2Shutdown = false;
      state.case2Flushing = false;
      state.solenoidOpen = true;
      renderSchematic();
      updateMainStatusBanner();
    }

    if (/FLOAT -> SUMP HIGH/i.test(line)) {
      state.floatTriggered = true;
      renderSchematic();
      updateMainStatusBanner();
    } else if (/FLOAT -> NORMAL/i.test(line)) {
      state.floatTriggered = false;
      renderSchematic();
      updateMainStatusBanner();
    }

    if (/CASE 1 -> SAFE IDLE/i.test(line) || /State:\s*SAFE_IDLE/i.test(line)) {
      state.case1State = 'SAFE_IDLE';
      state.pump1Duty = 0;
      state.pump2Duty = 0;
      state.pump3Duty = 0;
      state.solenoidOpen = false;
      renderSchematic();
      updateMainStatusBanner();
    } else if (/CASE 1 -> SUMP HIGH/i.test(line)) {
      state.case1State = 'SUMP_HIGH';
      state.floatTriggered = true;
      state.pump1Duty = 0;
      renderSchematic();
      updateMainStatusBanner();
    } else if (/CASE 1 -> RETURN TO NORMAL/i.test(line)) {
      state.case1State = 'RETURN_TO_NORMAL';
      state.floatTriggered = false;
      state.pump1Duty = 50;
      state.pump2Duty = 100;
      state.pump3Duty = 0;
      state.solenoidOpen = true;
      renderSchematic();
      updateMainStatusBanner();
    } else if (/CASE 1 -> NORMAL/i.test(line)) {
      state.case1State = 'NORMAL';
      state.floatTriggered = false;
      renderSchematic();
      updateMainStatusBanner();
    }

    // Status query dump lines
    const p1Status = line.match(/Pump 1 \(U2\)[\s\S]*?Duty:\s*(\d+)%/i) || line.match(/Pump 1:\s*(\d+)%/i);
    if (p1Status) { state.pump1Duty = parseInt(p1Status[1]); renderSchematic(); }
    const p2Status = line.match(/Pump 2 \(U3\)[\s\S]*?Duty:\s*(\d+)%/i) || line.match(/Pump 2:\s*(\d+)%/i);
    if (p2Status) { state.pump2Duty = parseInt(p2Status[1]); renderSchematic(); }
    const p3Status = line.match(/Pump 3 \(U4\)[\s\S]*?Duty:\s*(\d+)%/i) || line.match(/Pump 3:\s*(\d+)%/i);
    if (p3Status) { state.pump3Duty = parseInt(p3Status[1]); renderSchematic(); }
  }

  // Event log list
  function addEventLog(msg, type = 'info') {
    const timeStr = new Date().toTimeString().split(' ')[0];
    const item = document.createElement('div');
    item.className = `log-item log-${type}`;
    item.innerHTML = `<span class="log-time">[${timeStr}]</span> <span class="log-msg">${escapeHtml(msg)}</span>`;

    el.eventLogContainer.appendChild(item);
    while (el.eventLogContainer.children.length > 100) {
      el.eventLogContainer.removeChild(el.eventLogContainer.firstChild);
    }
    el.eventLogContainer.scrollTop = el.eventLogContainer.scrollHeight;
  }

  function flashActivityLed() {
    el.activityLed.classList.add('active');
    setTimeout(() => el.activityLed.classList.remove('active'), 80);
  }

  // Update Status Pills
  function updateBridgePill(online) {
    if (online) {
      el.bridgePill.className = 'pill pill-online';
      el.bridgePillText.textContent = 'BRIDGE: ONLINE';
    } else {
      el.bridgePill.className = 'pill pill-offline';
      el.bridgePillText.textContent = 'BRIDGE: OFFLINE';
    }
  }

  function updateSerialPill(connected, port, isMock) {
    if (connected) {
      if (isMock) {
        el.serialPill.className = 'pill pill-mock';
        el.serialPillText.textContent = 'MOCK ESP32 (SIMULATION)';
        el.connStateDetail.textContent = 'Connected to Simulated ESP32 Firmware.';
        if (el.mockCheckbox) el.mockCheckbox.checked = true;
      } else {
        el.serialPill.className = 'pill pill-online';
        el.serialPillText.textContent = `ESP32: ${port || 'CONNECTED'}`;
        el.connStateDetail.textContent = `Live USB connection on ${port} (115200 baud).`;
        if (el.mockCheckbox) el.mockCheckbox.checked = false;
      }
      el.btnConnect.disabled = true;
      el.btnDisconnect.disabled = false;
    } else {
      el.serialPill.className = 'pill pill-offline';
      el.serialPillText.textContent = 'ESP32: DISCONNECTED';
      el.connStateDetail.textContent = 'Serial port released. Available for Arduino IDE.';
      el.btnConnect.disabled = false;
      el.btnDisconnect.disabled = true;
    }
    updateMainStatusBanner();
  }

  function updateLoggingBadge(active) {
    if (active) {
      el.logStatusBadge.className = 'badge-tag badge-active';
      el.logStatusBadge.textContent = 'LOGGING';
    } else {
      el.logStatusBadge.className = 'badge-tag badge-idle';
      el.logStatusBadge.textContent = 'IDLE';
    }
  }

  // Update Status Display above Schematic
  function updateMainStatusBanner() {
    if (state.estopActive) {
      el.mainStatusPill.className = 'status-pill status-estop';
      el.bannerText.textContent = 'EMERGENCY STOP (HALTED)';
      return;
    }

    if (!state.systemOn) {
      el.mainStatusPill.className = 'status-pill status-shutdown';
      el.bannerText.textContent = 'SYSTEM SWITCH: OFF';
      return;
    }

    if (!state.connectedToSerial) {
      el.mainStatusPill.className = 'status-pill status-shutdown';
      el.bannerText.textContent = 'ESP32 DISCONNECTED';
      return;
    }

    if (state.case2Flushing) {
      el.mainStatusPill.className = 'status-pill status-flushing';
      el.bannerText.textContent = 'CASE 2 FLUSHING';
      return;
    }

    if (state.case2Shutdown) {
      el.mainStatusPill.className = 'status-pill status-shutdown';
      el.bannerText.textContent = 'SEQUENCE COMPLETE · SHUTDOWN LATCHED';
      return;
    }

    if (state.case1State === 'SAFE_IDLE' || state.case1State === 'INIT') {
      el.mainStatusPill.className = 'status-pill status-idle';
      el.bannerText.textContent = 'READY / SAFE IDLE · WAITING FOR START BUTTON';
      return;
    }

    if (state.case1State === 'RETURN_TO_NORMAL') {
      el.mainStatusPill.className = 'status-pill status-normal';
      el.bannerText.textContent = 'RETURNING TO NORMAL — FLUSH STARTS AUTOMATICALLY';
      return;
    }

    if (state.floatTriggered || state.case1State === 'SUMP_HIGH') {
      el.mainStatusPill.className = 'status-pill status-sump-high';
      el.bannerText.textContent = 'CASE 1 · SUMP HIGH (P1 Halted)';
      return;
    }

    if (state.case1State === 'NORMAL') {
      el.mainStatusPill.className = 'status-pill status-normal';
      el.bannerText.textContent = 'CASE 1 · NORMAL RECIRCULATION';
      return;
    }

    el.mainStatusPill.className = 'status-pill status-shutdown';
    el.bannerText.textContent = `STATUS: ${state.case1State || 'STANDBY'}`;
  }

  // Render Large SVG Hydraulic Schematic
  function renderSchematic() {
    const isConfirmedRunning = state.connectedToSerial && state.systemOn && !state.estopActive && !state.case2Shutdown;
    const isUnconfirmed = !state.connectedToSerial;

    // Proportional rotor speed formula:
    // 100% duty -> 0.45s (fastest)
    //  75% duty -> 0.98s (fast)
    //  50% duty -> 1.50s (moderate)
    //  25% duty -> 2.03s (slow)
    const getRotorDuration = (duty) => {
      const d = Math.max(0, Math.min(100, duty));
      if (d <= 0) return '0s';
      return `${(0.45 + (100 - d) * 0.021).toFixed(2)}s`;
    };

    function updatePumpVisual(groupEl, rotorEl, dutyTextEl, flowEl, duty, isRunning, isUnconf) {
      if (!groupEl) return;
      groupEl.classList.toggle('pump-running', isRunning);
      groupEl.classList.toggle('pump-stopped', !isRunning && !isUnconf);
      groupEl.classList.toggle('pump-unconfirmed', isUnconf);

      if (dutyTextEl) {
        dutyTextEl.textContent = isUnconf ? '--' : `${duty}%`;
        dutyTextEl.setAttribute('class', `pump-duty-badge ${isRunning ? 'duty-running' : (isUnconf ? 'duty-unconfirmed' : 'duty-stopped')}`);
      }

      if (flowEl) {
        flowEl.classList.toggle('active', isRunning);
      }

      if (rotorEl) {
        if (isRunning && duty > 0) {
          const dur = getRotorDuration(duty);
          rotorEl.style.setProperty('--rotor-speed', dur);
          rotorEl.style.animation = `rotateRotor ${dur} linear infinite`;
        } else {
          rotorEl.style.animation = 'none';
        }
      }
    }

    // 1. Pump 1
    const p1Running = isConfirmedRunning && (state.pump1Duty > 0);
    updatePumpVisual(el.pump1Group, el.pump1Rotor, el.pump1DutyText, el.flowP1, state.pump1Duty, p1Running, isUnconfirmed);

    // 2. Pump 2
    const p2Running = isConfirmedRunning && (state.pump2Duty > 0);
    updatePumpVisual(el.pump2Group, el.pump2Rotor, el.pump2DutyText, el.flowP2, state.pump2Duty, p2Running, isUnconfirmed);
    if (el.flowP2Tank) el.flowP2Tank.classList.toggle('active', p2Running);

    // 3. Pump 3
    const p3Running = isConfirmedRunning && (state.pump3Duty > 0);
    updatePumpVisual(el.pump3Group, el.pump3Rotor, el.pump3DutyText, el.flowP3, state.pump3Duty, p3Running, isUnconfirmed);

    // 4. Solenoid Valve
    if (state.solenoidOpen) {
      el.solenoidSymbol.className.baseVal = 'valve-symbol valve-open';
      el.solenoidStatusText.textContent = 'OPEN';
      el.solenoidStatusText.style.fill = '#16a34a';
    } else {
      el.solenoidSymbol.className.baseVal = 'valve-symbol valve-closed';
      el.solenoidStatusText.textContent = 'CLOSED';
      el.solenoidStatusText.style.fill = '#dc2626';
    }

    // 5. FT-01 Live Flow Readout
    el.schematicFlowVal.textContent = `${state.lastFlowLpm.toFixed(2)} L/min`;

    // 6. Sump Float Switch
    if (!el.sumpLiquidLevel) {
      el.sumpLiquidLevel = document.getElementById('sump-liquid-level');
    }

    if (state.floatTriggered) {
      if (el.floatBob) {
        el.floatBob.className.baseVal = 'float-bob float-bob-high';
        el.floatBob.setAttribute('cy', '16');
      }
      if (el.floatStatusText) {
        el.floatStatusText.textContent = 'SUMP HIGH';
        el.floatStatusText.style.fill = '#dc2626';
      }
      if (el.sumpLiquidSurface) {
        el.sumpLiquidSurface.setAttribute('y1', '40');
        el.sumpLiquidSurface.setAttribute('y2', '40');
      }
      if (el.sumpLiquidLevel) {
        el.sumpLiquidLevel.setAttribute('y', '40');
        el.sumpLiquidLevel.setAttribute('height', '96');
      }
    } else {
      if (el.floatBob) {
        el.floatBob.className.baseVal = 'float-bob float-bob-normal';
        el.floatBob.setAttribute('cy', '35');
      }
      if (el.floatStatusText) {
        el.floatStatusText.textContent = 'NORMAL';
        el.floatStatusText.style.fill = '#0284c7';
      }
      if (el.sumpLiquidSurface) {
        el.sumpLiquidSurface.setAttribute('y1', '65');
        el.sumpLiquidSurface.setAttribute('y2', '65');
      }
      if (el.sumpLiquidLevel) {
        el.sumpLiquidLevel.setAttribute('y', '65');
        el.sumpLiquidLevel.setAttribute('height', '71');
      }
    }

    // 7. Physical Start Button Indicator (GPIO 34)
    if (el.flushBtnComp && el.flushBtnState) {
      if (state.case2Flushing) {
        el.flushBtnComp.classList.add('flush-btn-active');
        el.flushBtnState.textContent = 'RUNNING: FLUSH ACTIVE';
        el.flushBtnState.style.fill = '#dc2626';
      } else if (state.case2Shutdown) {
        el.flushBtnComp.classList.remove('flush-btn-active');
        el.flushBtnState.textContent = 'SHUTDOWN LATCHED';
        el.flushBtnState.style.fill = '#94a3b8';
      } else if (state.case1State === 'NORMAL' || state.case1State === 'SUMP_HIGH' || state.case1State === 'RETURN_TO_NORMAL') {
        el.flushBtnComp.classList.add('flush-btn-active');
        el.flushBtnState.textContent = 'RUNNING: CASE 1 ACTIVE';
        el.flushBtnState.style.fill = '#16a34a';
      } else {
        el.flushBtnComp.classList.remove('flush-btn-active');
        el.flushBtnState.textContent = 'READY: PRESS TO START';
        el.flushBtnState.style.fill = '#64748b';
      }
    }

    // Mode Pill
    if (state.case2Flushing) {
      el.schematicModePill.textContent = 'CASE 2 FLUSHING';
      el.schematicModePill.className = 'badge-tag badge-warning';
    } else if (state.case2Shutdown) {
      el.schematicModePill.textContent = 'SEQUENCE COMPLETE (LATCHED)';
      el.schematicModePill.className = 'badge-tag badge-idle';
    } else if (state.case1State === 'RETURN_TO_NORMAL') {
      el.schematicModePill.textContent = 'RETURNING TO NORMAL (10s)';
      el.schematicModePill.className = 'badge-tag badge-info';
    } else if (state.case1State === 'SUMP_HIGH' || state.floatTriggered) {
      el.schematicModePill.textContent = 'CASE 1 SUMP HIGH';
      el.schematicModePill.className = 'badge-tag badge-warning';
    } else if (state.case1State === 'NORMAL') {
      el.schematicModePill.textContent = 'CASE 1 RECIRCULATION';
      el.schematicModePill.className = 'badge-tag badge-info';
    } else {
      el.schematicModePill.textContent = 'READY / SAFE IDLE';
      el.schematicModePill.className = 'badge-tag badge-idle';
    }
  }

  // Case 2 Flush Sequence Internal Tracking
  // Note: Per requirement, no visible countdown or progress bar is displayed anywhere in the UI.
  function startCase2Countdown(durationSec = 90) {
    state.case2Flushing = true;
    state.case2Shutdown = false;
    state.case2FlushStartTime = Date.now();
    state.case2FlushDuration = durationSec;

    if (el.case2FlushMonitor) el.case2FlushMonitor.classList.add('hidden');

    if (state.countdownTimerId) clearInterval(state.countdownTimerId);

    state.countdownTimerId = setInterval(() => {
      const elapsed = (Date.now() - state.case2FlushStartTime) / 1000;
      const remain = Math.max(0, state.case2FlushDuration - elapsed);

      if (remain <= 0) {
        clearInterval(state.countdownTimerId);
        state.countdownTimerId = null;
      }
    }, 500);

    renderSchematic();
    updateMainStatusBanner();
  }

  function endCase2Countdown() {
    if (state.countdownTimerId) {
      clearInterval(state.countdownTimerId);
      state.countdownTimerId = null;
    }
    state.case2Flushing = false;
    state.case2Shutdown = true;

    if (el.case2FlushMonitor) el.case2FlushMonitor.classList.add('hidden');

    renderSchematic();
    updateMainStatusBanner();
  }

  // Live Flow Graph (Light Industrial Canvas)
  function initCanvas() {
    canvasCtx = el.graphCanvas.getContext('2d');
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);
    if (window.ResizeObserver && el.graphCanvas.parentElement) {
      const ro = new ResizeObserver(() => {
        resizeCanvas();
      });
      ro.observe(el.graphCanvas.parentElement);
    }
  }

  function resizeCanvas() {
    if (!el.graphCanvas || !el.graphCanvas.parentElement) return;
    const rect = el.graphCanvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const targetW = Math.max(1, Math.floor(rect.width * dpr));
    const targetH = Math.max(1, Math.floor(rect.height * dpr));
    if (el.graphCanvas.width !== targetW || el.graphCanvas.height !== targetH) {
      el.graphCanvas.width = targetW;
      el.graphCanvas.height = targetH;
    }
  }

  function startCanvasLoop() {
    function draw() {
      renderFlowGraph();
      requestAnimationFrame(draw);
    }
    requestAnimationFrame(draw);
    setInterval(renderFlowGraph, 250);
  }

  function renderFlowGraph() {
    if (!el.graphStateBadge) {
      el.graphStateBadge = document.getElementById('graph-state-badge');
    }

    // Data status badge: ALWAYS update based on live system state
    const nowMs = Date.now();
    const timeSinceLast = (nowMs - state.lastReadingTime) / 1000;

    if (el.graphStateBadge) {
      if (!state.connectedToSerial) {
        el.graphStateBadge.className = 'badge-tag badge-idle';
        el.graphStateBadge.textContent = 'DISCONNECTED';
      } else if (state.flowRecords.length === 0) {
        el.graphStateBadge.className = 'badge-tag badge-waiting';
        el.graphStateBadge.textContent = 'WAITING';
      } else if (timeSinceLast > 5.0) {
        el.graphStateBadge.className = 'badge-tag badge-stale';
        el.graphStateBadge.textContent = 'STALE';
      } else {
        el.graphStateBadge.className = 'badge-tag badge-active';
        el.graphStateBadge.textContent = 'LIVE DATA';
      }
    }

    if (!canvasCtx && el.graphCanvas) {
      canvasCtx = el.graphCanvas.getContext('2d');
    }
    if (!canvasCtx) return;

    // Verify canvas size matches container
    resizeCanvas();

    const ctx = canvasCtx;
    const rect = el.graphCanvas.parentElement ? el.graphCanvas.parentElement.getBoundingClientRect() : { width: el.graphCanvas.width, height: el.graphCanvas.height };
    const dpr = window.devicePixelRatio || 1;
    const w = rect.width;
    const h = rect.height;

    if (w <= 0 || h <= 0) return;

    ctx.save();
    ctx.scale(dpr, dpr);

    // Clear background (Clean pure white)
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, w, h);

    const padLeft = 40;
    const padRight = 14;
    const padTop = 16;
    const padBottom = 24;
    const graphW = w - padLeft - padRight;
    const graphH = h - padTop - padBottom;

    if (graphW <= 0 || graphH <= 0) {
      ctx.restore();
      return;
    }

    const maxFlow = 6.0;
    const windowSec = 30.0;
    const nowSec = nowMs / 1000;
    const startSec = nowSec - windowSec;

    // 1. Shaded Rated Range (0.3 to 6.0 L/min)
    const yRatedLow = padTop + graphH * (1 - (0.3 / maxFlow));
    const yRatedHigh = padTop;
    ctx.fillStyle = 'rgba(2, 132, 199, 0.035)';
    ctx.fillRect(padLeft, yRatedHigh, graphW, yRatedLow - yRatedHigh);

    ctx.fillStyle = 'rgba(100, 116, 139, 0.45)';
    ctx.font = '8px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
    ctx.textAlign = 'right';
    ctx.fillText('RATED 0.3 - 6.0 L/min', padLeft + graphW - 4, padTop + 9);

    // 2. Light Gridlines & Y-Axis Labels
    ctx.fillStyle = '#64748b';
    ctx.font = '9px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
    ctx.textAlign = 'right';

    for (let f = 0; f <= maxFlow + 0.01; f += 1.5) {
      const y = Math.round(padTop + graphH * (1 - (f / maxFlow))) + 0.5;
      ctx.beginPath();
      ctx.moveTo(padLeft, y);
      ctx.lineTo(padLeft + graphW, y);
      ctx.strokeStyle = f === 0 ? '#cbd5e1' : '#f1f5f9';
      ctx.lineWidth = 1;
      ctx.stroke();

      // Tick mark
      ctx.beginPath();
      ctx.moveTo(padLeft - 3, y);
      ctx.lineTo(padLeft, y);
      ctx.strokeStyle = '#94a3b8';
      ctx.stroke();

      ctx.fillText(f.toFixed(1), padLeft - 6, y + 3);
    }

    // Y-Axis Unit Header
    ctx.fillStyle = '#475569';
    ctx.font = 'bold 8.5px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
    ctx.textAlign = 'right';
    ctx.fillText('L/min', padLeft - 6, padTop - 5);

    // 3. Vertical Gridlines & Time Axis (Older to Newer: -30s -> Now)
    ctx.textAlign = 'center';
    ctx.fillStyle = '#64748b';
    ctx.font = '9px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';

    for (let s = Math.ceil(startSec / 5) * 5; s <= nowSec + 0.001; s += 5) {
      const x = Math.round(padLeft + ((s - startSec) / windowSec) * graphW) + 0.5;
      if (x >= padLeft && x <= padLeft + graphW) {
        ctx.beginPath();
        ctx.moveTo(x, padTop);
        ctx.lineTo(x, padTop + graphH);
        ctx.strokeStyle = '#f1f5f9';
        ctx.lineWidth = 1;
        ctx.stroke();

        const secAgo = Math.round(nowSec - s);
        const label = secAgo <= 0 ? 'Now' : `-${secAgo}s`;
        ctx.fillText(label, x, padTop + graphH + 15);
      }
    }

    // X-Axis Baseline
    ctx.beginPath();
    ctx.moveTo(padLeft, padTop + graphH + 0.5);
    ctx.lineTo(padLeft + graphW, padTop + graphH + 0.5);
    ctx.strokeStyle = '#cbd5e1';
    ctx.lineWidth = 1;
    ctx.stroke();

    // 4. Plot Flow Rate Curve
    if (state.graphPoints.length >= 1) {
      ctx.save();
      ctx.beginPath();
      ctx.rect(padLeft, padTop, graphW, graphH);
      ctx.clip();

      ctx.beginPath();
      let firstX = padLeft;
      let lastX = padLeft;

      if (state.graphPoints.length === 1) {
        const pt = state.graphPoints[0];
        const normFlow = Math.max(0, Math.min(maxFlow, pt.flow));
        const y = padTop + graphH * (1 - (normFlow / maxFlow));
        lastX = padLeft + ((pt.time - startSec) / windowSec) * graphW;
        firstX = Math.max(padLeft, lastX - 12);
        ctx.moveTo(firstX, y);
        ctx.lineTo(lastX, y);
      } else {
        let first = true;
        for (let i = 0; i < state.graphPoints.length; i++) {
          const pt = state.graphPoints[i];
          const x = padLeft + ((pt.time - startSec) / windowSec) * graphW;
          const normFlow = Math.max(0, Math.min(maxFlow, pt.flow));
          const y = padTop + graphH * (1 - (normFlow / maxFlow));

          if (first) {
            ctx.moveTo(x, y);
            firstX = x;
            first = false;
          } else {
            ctx.lineTo(x, y);
          }
          lastX = x;
        }
      }

      ctx.strokeStyle = '#0284c7';
      ctx.lineWidth = 2.0;
      ctx.lineJoin = 'round';
      ctx.lineCap = 'round';
      ctx.stroke();

      // Translucent Gradient Fill under curve
      const lastPt = state.graphPoints[state.graphPoints.length - 1];
      ctx.lineTo(lastX, padTop + graphH);
      ctx.lineTo(firstX, padTop + graphH);
      ctx.closePath();

      const grad = ctx.createLinearGradient(0, padTop, 0, padTop + graphH);
      grad.addColorStop(0, 'rgba(2, 132, 199, 0.20)');
      grad.addColorStop(0.7, 'rgba(2, 132, 199, 0.05)');
      grad.addColorStop(1, 'rgba(2, 132, 199, 0.00)');
      ctx.fillStyle = grad;
      ctx.fill();

      // Latest Point Marker with Subtle Glow
      const currNormFlow = Math.max(0, Math.min(maxFlow, lastPt.flow));
      const currY = padTop + graphH * (1 - (currNormFlow / maxFlow));

      // Outer Halo Ring
      ctx.beginPath();
      ctx.arc(lastX, currY, 6, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(2, 132, 199, 0.22)';
      ctx.fill();

      // Inner Crisp Point
      ctx.beginPath();
      ctx.arc(lastX, currY, 3.5, 0, Math.PI * 2);
      ctx.fillStyle = '#0284c7';
      ctx.fill();
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1.5;
      ctx.stroke();

      ctx.restore();
    } else {
      // Empty watermark
      ctx.fillStyle = '#94a3b8';
      ctx.font = '10px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
      ctx.textAlign = 'center';
      const emptyMsg = !state.connectedToSerial ? 'NO TELEMETRY (DISCONNECTED)' : 'WAITING FOR FLOW DATA (SEND \'L\')';
      ctx.fillText(emptyMsg, padLeft + graphW / 2, padTop + graphH / 2);
    }

    ctx.restore();
  }

  function updateGraphMetrics(flow, freq, pwm) {
    el.metricFlowVal.textContent = flow.toFixed(2);
    el.metricFreqVal.textContent = Math.round(freq);
    el.metricPwmVal.textContent = pwm !== undefined ? pwm : '--';
  }

  // Serial Command Transmitter
  function sendCommand(cmd) {
    if (!cmd) return;
    const clean = String(cmd).trim().replace(/^['"]+|['"]+$/g, '');
    if (!clean) return;

    // Display submitted command in raw terminal so user can compare input with bridge response
    const pre = el.rawTerminalOutput;
    pre.textContent += `> ${clean}\n`;
    if (pre.textContent.length > 20000) {
      pre.textContent = pre.textContent.substring(pre.textContent.length - 15000);
    }
    pre.scrollTop = pre.scrollHeight;

    // Optimistic pump & actuator updates for immediate UI responsiveness
    const c = clean;
    if (c === '0') {
      state.pump1Duty = 0;
      renderSchematic();
    } else if (c === '1') {
      state.pump1Duty = 25;
      renderSchematic();
    } else if (c === '2') {
      state.pump1Duty = 50;
      renderSchematic();
    } else if (c === '3') {
      state.pump1Duty = 75;
      renderSchematic();
    } else if (c === '4') {
      state.pump1Duty = 100;
      renderSchematic();
    } else if (c === 'd' || c === 'D') {
      state.pump1Duty = 0;
      renderSchematic();
    } else if (c === '9') {
      state.pump2Duty = 0;
      renderSchematic();
    } else if (c === '5') {
      state.pump2Duty = 25;
      renderSchematic();
    } else if (c === '6') {
      state.pump2Duty = 50;
      renderSchematic();
    } else if (c === '7') {
      state.pump2Duty = 75;
      renderSchematic();
    } else if (c === '8') {
      state.pump2Duty = 100;
      renderSchematic();
    } else if (c === 'w' || c === 'W') {
      state.pump2Duty = 0;
      renderSchematic();
    } else if (c === 'i' || c === 'I') {
      if (!state.case2Flushing) {
        state.pump3Duty = 0;
        renderSchematic();
      }
    } else if (c === 'N') {
      if (state.isMock) {
        state.pump1Duty = 50;
        state.pump2Duty = 100;
        state.pump3Duty = 0;
        state.case1State = 'NORMAL';
        state.floatTriggered = false;
        state.case2Shutdown = false;
        state.case2Flushing = false;
        state.solenoidOpen = true;
        renderSchematic();
        updateMainStatusBanner();
      }
    } else if (c === 'n') {
      if (state.isMock) {
        state.pump1Duty = 50;
        state.pump2Duty = 100;
        state.pump3Duty = 0;
        state.case1State = 'NORMAL';
        state.floatTriggered = false;
        renderSchematic();
        updateMainStatusBanner();
      }
    } else if (c === 'x' || c === 'X') {
      if (state.isMock) {
        state.pump1Duty = 0;
        state.pump2Duty = 100;
        state.pump3Duty = 0;
        state.case1State = 'SUMP_HIGH';
        state.floatTriggered = true;
        renderSchematic();
        updateMainStatusBanner();
      }
    } else if (c === 'r' || c === 'R') {
      if (state.isMock) {
        state.pump1Duty = 50;
        state.pump2Duty = 100;
        state.pump3Duty = 0;
        state.case1State = 'RETURN_TO_NORMAL';
        state.floatTriggered = false;
        renderSchematic();
        updateMainStatusBanner();
      }
    } else if (c === 's' || c === 'S' || c === ' ') {
      state.estopActive = true;
      state.pump1Duty = 0;
      state.pump2Duty = 0;
      state.pump3Duty = 0;
      state.solenoidOpen = false;
      state.case1State = 'EMERGENCY_STOP';
      renderSchematic();
      updateMainStatusBanner();
    } else if (/^(?:d|u)1\s*(\d+)$/i.test(c)) {
      const m = c.match(/^(?:d|u)1\s*(\d+)$/i);
      const val = parseInt(m[1]);
      if (val >= 0 && val <= 100 && val % 5 === 0) {
        state.pump1Duty = val;
        renderSchematic();
      }
    } else if (/^(?:d|u)2\s*(\d+)$/i.test(c)) {
      const m = c.match(/^(?:d|u)2\s*(\d+)$/i);
      const val = parseInt(m[1]);
      if (val >= 0 && val <= 100 && val % 5 === 0) {
        state.pump2Duty = val;
        renderSchematic();
      }
    } else if (/^(?:d|u)(\d+)$/i.test(c)) {
      const m = c.match(/^(?:d|u)(\d+)$/i);
      const val = parseInt(m[1]);
      if (val >= 0 && val <= 100 && val % 5 === 0) {
        state.pump2Duty = val;
        renderSchematic();
      }
    } else if (c === 'a' || c === 'A') {
      if (!state.estopActive && state.systemOn) {
        state.solenoidOpen = true;
        renderSchematic();
      }
    } else if (c === 'c' || c === 'C') {
      state.solenoidOpen = false;
      renderSchematic();
    } else if (c === 'k' || c === 'K') {
      if (!state.solenoidOpen) {
        if (!state.estopActive && state.systemOn) {
          state.solenoidOpen = true;
          renderSchematic();
        }
      } else {
        state.solenoidOpen = false;
        renderSchematic();
      }
    }

    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
      state.ws.send(JSON.stringify({
        action: 'send_command',
        command: clean
      }));
    } else {
      fetch('/api/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: clean })
      }).catch(err => console.error('Send error:', err));
    }

    addEventLog(`Sent command: '${clean}'`, 'info');
  }

  // Refresh Ports
  function refreshComPorts() {
    fetch('/api/ports')
      .then(r => r.json())
      .then(data => {
        el.comPortSelect.innerHTML = '';
        if (data.ports && data.ports.length > 0) {
          data.ports.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.device;
            opt.textContent = `${p.device} (${p.description || 'USB Serial'})`;
            el.comPortSelect.appendChild(opt);
          });
          const mockOpt = document.createElement('option');
          mockOpt.value = 'MOCK';
          mockOpt.textContent = 'MOCK ESP32 (Simulation Mode)';
          el.comPortSelect.appendChild(mockOpt);
          if (el.mockCheckbox.checked) {
            el.comPortSelect.value = 'MOCK';
          } else {
            el.comPortSelect.selectedIndex = 0;
          }
        } else {
          const opt = document.createElement('option');
          opt.value = 'MOCK';
          opt.textContent = 'MOCK ESP32 (Simulation Mode)';
          el.comPortSelect.appendChild(opt);
          el.comPortSelect.value = 'MOCK';
          el.mockCheckbox.checked = true;
        }
      })
      .catch(e => console.warn('Port scan error:', e));
  }

  // Direct Component Control Popovers
  function showComponentPopover(title, contentHtml, anchorEl) {
    el.popoverTitle.textContent = title;
    el.popoverBody.innerHTML = contentHtml;
    el.popover.classList.remove('hidden');

    const wrapperRect = document.getElementById('schematic-wrapper').getBoundingClientRect();
    const anchorRect = anchorEl.getBoundingClientRect();

    let left = anchorRect.left - wrapperRect.left + (anchorRect.width / 2);
    let top = anchorRect.top - wrapperRect.top + anchorRect.height + 6;

    if (left + 230 > wrapperRect.width) left = wrapperRect.width - 240;
    if (top + 160 > wrapperRect.height) top = anchorRect.top - wrapperRect.top - 150;

    el.popover.style.left = `${Math.max(10, left)}px`;
    el.popover.style.top = `${Math.max(10, top)}px`;
  }

  function hidePopover() {
    el.popover.classList.add('hidden');
  }

  // Event Listeners Setup
  function setupEventListeners() {
    // E-Stop Buttons
    el.topEstopBtn.addEventListener('click', () => sendCommand('s'));

    // Keyboard Spacebar for Emergency Stop
    window.addEventListener('keydown', (e) => {
      if (e.code === 'Space' && document.activeElement !== el.termInput) {
        e.preventDefault();
        sendCommand('s');
      }
    });

    // Connection Sync
    el.btnRefreshPorts.addEventListener('click', refreshComPorts);

    el.comPortSelect.addEventListener('change', () => {
      if (el.comPortSelect.value === 'MOCK') {
        el.mockCheckbox.checked = true;
      } else {
        el.mockCheckbox.checked = false;
      }
    });

    el.mockCheckbox.addEventListener('change', () => {
      if (el.mockCheckbox.checked) {
        let hasMock = false;
        for (let i = 0; i < el.comPortSelect.options.length; i++) {
          if (el.comPortSelect.options[i].value === 'MOCK') {
            el.comPortSelect.selectedIndex = i;
            hasMock = true;
            break;
          }
        }
        if (!hasMock) {
          const opt = document.createElement('option');
          opt.value = 'MOCK';
          opt.textContent = 'MOCK ESP32 (Simulation Mode)';
          el.comPortSelect.appendChild(opt);
          el.comPortSelect.value = 'MOCK';
        }
      } else {
        if (el.comPortSelect.options.length > 0 && el.comPortSelect.options[0].value !== 'MOCK') {
          el.comPortSelect.selectedIndex = 0;
        } else {
          addEventLog('No physical COM ports detected. Plug in ESP32 and click Refresh.', 'warn');
        }
      }
    });

    el.btnConnect.addEventListener('click', () => {
      const isMock = el.mockCheckbox.checked || el.comPortSelect.value === 'MOCK';
      const port = isMock ? 'MOCK' : el.comPortSelect.value;

      fetch('/api/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ port: port || 'MOCK', baud: 115200, mock: isMock })
      })
      .then(r => r.json())
      .then(res => {
        if (res.status === 'connected') {
          state.connectedToSerial = true;
          state.isMock = res.is_mock;
          state.port = res.port;
          updateSerialPill(true, res.port, res.is_mock);
          addEventLog(`Connected to ${res.port} (Mock: ${res.is_mock})`, 'success');
          sendCommand('p');
          renderSchematic();
          updateMainStatusBanner();
          renderFlowGraph();
        } else {
          addEventLog(`Connect failed: ${res.message || 'Unknown error'}`, 'error');
        }
      })
      .catch(e => addEventLog(`Connect error: ${e}`, 'error'));
    });

    el.btnDisconnect.addEventListener('click', () => {
      fetch('/api/disconnect', { method: 'POST' })
        .then(() => {
          state.connectedToSerial = false;
          updateSerialPill(false);
          state.flowRecords = [];
          state.latest10Records = [];
          state.graphPoints = [];
          renderSchematic();
          updateMainStatusBanner();
          renderFlowGraph();
          addEventLog('Disconnected serial port. Port released for Arduino IDE.', 'info');
        })
        .catch(e => console.error(e));
    });

    // Table & Data Controls
    el.btnExportCsv.addEventListener('click', () => {
      if (state.flowRecords.length === 0) {
        alert('No flow records captured yet in this session.');
        return;
      }
      let csv = 'timestamp_ms,pump2_pwm,frequency_hz,estimated_flow_lpm\n';
      state.flowRecords.forEach(r => {
        csv += `${r.timestamp_ms},${r.pump2_pwm},${r.frequency_hz.toFixed(1)},${r.flow_lpm.toFixed(2)}\n`;
      });
      const blob = new Blob([csv], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `flow_log_${new Date().toISOString().replace(/[:.]/g, '-')}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    });

    el.btnClearTable.addEventListener('click', () => {
      state.flowRecords = [];
      state.latest10Records = [];
      renderFlowTable();
      addEventLog('Session table history cleared.', 'info');
    });

    // Center Action Bar Buttons
    el.btnSimNorm.addEventListener('click', () => sendCommand('n'));
    el.btnSimHigh.addEventListener('click', () => sendCommand('x'));
    el.btnSimRet.addEventListener('click', () => sendCommand('r'));
    el.btnQueryAll.addEventListener('click', () => sendCommand('p'));

    // Console Tabs
    el.tabBtnEvents.addEventListener('click', () => {
      el.tabBtnEvents.classList.add('tab-active');
      el.tabBtnTerminal.classList.remove('tab-active');
      el.tabContentEvents.classList.remove('hidden');
      el.tabContentTerminal.classList.add('hidden');
    });

    el.tabBtnTerminal.addEventListener('click', () => {
      el.tabBtnTerminal.classList.add('tab-active');
      el.tabBtnEvents.classList.remove('tab-active');
      el.tabContentTerminal.classList.remove('hidden');
      el.tabContentEvents.classList.add('hidden');
      el.rawTerminalOutput.scrollTop = el.rawTerminalOutput.scrollHeight;
    });

    // Terminal Input with Deduplicated Enter & Click Handling
    let lastSubmitTime = 0;
    function handleTermSubmit(e) {
      if (e) e.preventDefault();
      const now = Date.now();
      if (now - lastSubmitTime < 100) return;
      const raw = el.termInput.value;
      const clean = raw.trim().replace(/^['"]+|['"]+$/g, '');
      if (!clean) return;
      lastSubmitTime = now;
      sendCommand(clean);
      el.termInput.value = '';
    }

    el.btnTermSend.addEventListener('click', handleTermSubmit);

    el.termInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        handleTermSubmit(e);
      }
    });

    el.btnClearTerm.addEventListener('click', () => {
      el.rawTerminalOutput.textContent = '';
      el.eventLogContainer.innerHTML = '';
    });

    el.popoverClose.addEventListener('click', hidePopover);

    // ================= DIRECT SCHEMATIC INTERACTIONS =================

    // 1. Direct Click on Pump 1 (U2)
    el.pump1Group.addEventListener('click', (e) => {
      e.stopPropagation();
      const html = `
        <div class="popover-row"><span>Driver:</span><strong>U2 (BTS7960)</strong></div>
        <div class="popover-row"><span>Purpose:</span><strong>Tank &rarr; Sump</strong></div>
        <div class="popover-row"><span>Current Duty:</span><strong>${state.pump1Duty}%</strong></div>
        <div class="popover-actions">
          <button class="btn btn-tiny btn-outline" onclick="window.sendCmd('1')">25% ['1']</button>
          <button class="btn btn-tiny btn-outline" onclick="window.sendCmd('2')">50% ['2']</button>
          <button class="btn btn-tiny btn-outline" onclick="window.sendCmd('3')">75% ['3']</button>
          <button class="btn btn-tiny btn-outline" onclick="window.sendCmd('4')">100% ['4']</button>
          <button class="btn btn-tiny btn-outline" onclick="window.sendCmd('0')">Stop ['0']</button>
          <button class="btn btn-tiny btn-outline" onclick="window.sendCmd('e')">Enable ['e']</button>
        </div>
      `;
      showComponentPopover('Pump 1 Control', html, el.pump1Group);
    });

    // 2. Direct Click on Pump 2 (U3)
    el.pump2Group.addEventListener('click', (e) => {
      e.stopPropagation();
      const html = `
        <div class="popover-row"><span>Driver:</span><strong>U3 (BTS7960)</strong></div>
        <div class="popover-row"><span>Purpose:</span><strong>Sump &rarr; Main Tank</strong></div>
        <div class="popover-row"><span>Current Duty:</span><strong>${state.pump2Duty}%</strong></div>
        <div class="popover-actions">
          <button class="btn btn-tiny btn-outline" onclick="window.sendCmd('5')">25% ['5']</button>
          <button class="btn btn-tiny btn-outline" onclick="window.sendCmd('6')">50% ['6']</button>
          <button class="btn btn-tiny btn-outline" onclick="window.sendCmd('7')">75% ['7']</button>
          <button class="btn btn-tiny btn-outline" onclick="window.sendCmd('8')">100% ['8']</button>
          <button class="btn btn-tiny btn-outline" onclick="window.sendCmd('9')">Stop ['9']</button>
          <button class="btn btn-tiny btn-outline" onclick="window.sendCmd('q')">Enable ['q']</button>
        </div>
      `;
      showComponentPopover('Pump 2 Control', html, el.pump2Group);
    });

    // 3. Direct Click on Pump 3 (U4)
    el.pump3Group.addEventListener('click', (e) => {
      e.stopPropagation();
      const html = `
        <div class="popover-row"><span>Driver:</span><strong>U4 (BTS7960)</strong></div>
        <div class="popover-row"><span>Purpose:</span><strong>Flush Supply</strong></div>
        <div class="popover-row"><span>Current Duty:</span><strong>${state.pump3Duty}%</strong></div>
        <div style="font-size:9.5px; color:#d97706; margin-top:4px;">
          &#x26A0; Manual start ('u') rejected by firmware (valve unverified). Trigger Case 2 via physical flush button.
        </div>
        <div class="popover-actions" style="margin-top:6px;">
          <button class="btn btn-tiny btn-outline" onclick="window.sendCmd('i')">Stop ['i']</button>
          <button class="btn btn-tiny btn-outline" onclick="window.sendCmd('p')">Status ['p']</button>
        </div>
      `;
      showComponentPopover('Pump 3 Control', html, el.pump3Group);
    });

    // 4. Direct Click on Solenoid Valve (Toggle or Open/Close)
    el.solenoidComp.addEventListener('click', (e) => {
      e.stopPropagation();
      const html = `
        <div class="popover-row"><span>Pin:</span><strong>GPIO 27</strong></div>
        <div class="popover-row"><span>Hardware:</span><strong>Flomaxx 2W (NC)</strong></div>
        <div class="popover-row"><span>State:</span><strong>${state.solenoidOpen ? 'OPEN (Energized)' : 'CLOSED (Isolated)'}</strong></div>
        <div class="popover-actions">
          <button class="btn btn-tiny btn-outline" onclick="window.sendCmd('k')">Toggle ['k']</button>
          <button class="btn btn-tiny btn-outline" onclick="window.sendCmd('a')">Open ['a']</button>
          <button class="btn btn-tiny btn-outline" onclick="window.sendCmd('c')">Close ['c']</button>
        </div>
      `;
      showComponentPopover('Solenoid Valve (GPIO 27)', html, el.solenoidComp);
    });

    // 5. Direct Hover/Click on FT-01 Flow Sensor
    el.flowSensorComp.addEventListener('click', (e) => {
      e.stopPropagation();
      const html = `
        <div class="popover-row"><span>Sensor:</span><strong>YF-S401 (FT-01)</strong></div>
        <div class="popover-row"><span>GPIO:</span><strong>GPIO 14 (Interrupt)</strong></div>
        <div class="popover-row"><span>Flow Rate:</span><strong>${state.lastFlowLpm.toFixed(3)} L/min</strong></div>
        <div class="popover-row"><span>Frequency:</span><strong>${state.lastFlowHz.toFixed(1)} Hz</strong></div>
        <div class="popover-actions" style="margin-top:6px;">
          <button class="btn btn-tiny btn-outline" onclick="window.sendCmd('l')">Query ['l']</button>
          <button class="btn btn-tiny btn-outline" onclick="window.sendCmd('L')">Toggle Log ['L']</button>
        </div>
      `;
      showComponentPopover('FT-01 Flow Sensor', html, el.flowSensorComp);
    });

    // 6. Direct Click on Physical Start Button (GPIO 34)
    if (el.flushBtnComp) {
      el.flushBtnComp.addEventListener('click', (e) => {
        e.stopPropagation();
        if (state.isMock) {
          sendCommand('!start_btn');
        } else {
          alert('Physical Start Button is mapped to hardware GPIO 34 (PCB ON/OFF connector with external 10k pull-up).\\nPress the physical button on the hardware to start the automatic Case 1 -> Case 2 sequence.');
        }
      });
    }

    document.addEventListener('click', hidePopover);
  }

  // Global Helper for popover onclick attributes
  window.sendCmd = function (c) {
    sendCommand(c);
  };

  // Expose SCADA controller interface and state for automated testing & monitoring
  window.__scada = {
    state,
    handleBridgeMessage,
    sendCommand,
    renderSchematic,
    updatePumpVisual: (g, r, t, f, d, run, unc) => {
      // helper alias if called externally
      renderSchematic();
    }
  };

  // Allow simulated WebSocket messages or parent-frame messages to be dispatched
  window.addEventListener('message', (event) => {
    if (event.data) {
      try {
        const msg = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
        handleBridgeMessage(msg);
      } catch (e) {
        console.error('Error handling dispatched message:', e);
      }
    }
  });

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
