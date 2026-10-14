#include <Arduino.h>
#include "pump_controller.h"
#include "pump2_controller.h"
#include "pump3_controller.h"
#include "case1_controller.h"
#include "float_switch.h"
#include "flow_sensor.h"
#include "system_switch.h"
#include "start_button.h"
#include "solenoid_valve.h"
#include "commissioning.h"
#include "duty_parser.h"

// Continuous CSV flow logging state
static bool s_csvLoggingActive = false;
static unsigned long s_lastCsvLogTime = 0;

static bool checkPumpSafety(int pump) {
    if (isCase1EmergencyStopActive()) {
        Serial.printf("[SAFETY] Blocked: Emergency Stop is active! Press '%s' or 'n' to clear.\n",
                      (pump == 1) ? "e" : "q");
        return false;
    }
    if (!isSystemOn()) {
        Serial.println("[SAFETY] Blocked: Cannot run pump while System Switch is OFF.");
        return false;
    }
    return true;
}

static void printHelpMenu() {
    Serial.println("\n----------------- COMMAND MENU -----------------");
    Serial.println("Auto Sequence: Start Button (GPIO 34) starts Case 1 -> Case 2");
    Serial.println("               Case 1: Normal recirculation (P1 50%, P2 100%, Solenoid OPEN)");
    Serial.println("               Sump High: P1 halts (0%), P2 continues 100%");
    Serial.println("               Return Normal: 10s delay then Case 2 auto-starts");
    Serial.println("               Case 2: 90s flush (P1 50%, P2 100%, P3 50%, Solenoid CLOSED)");
    Serial.println("               Final: 90s timeout -> latched shutdown (all motors OFF)");
    Serial.println("System:        s/[Space]=E-Stop | p=Status | h=Help");
    Serial.println("               y=Query System State | Y=Toggle System Enable (On/Off)");
    Serial.println("               Commands: sys on / sys off");
    Serial.println("P1 (U2):       1=25% 2=50% 3=75% 4=100% 0=Stop | e=Enable d=Disable");
    Serial.println("               d1 <0-100> in 5% steps (e.g. d1 50)");
    Serial.println("P2 (U3):       5=25% 6=50% 7=75% 8=100% 9=Stop | q=Enable w=Disable");
    Serial.println("               d<0-100> in 5% steps (e.g. d5, d10, d50, d100) | d2 <0-100>");
    Serial.println("               f=Fwd v=Rev o=P2 Status");
    Serial.println("P3 (U4):       u=Start Req (Rejected: Unsafe) | i=Stop");
    Serial.println("Solenoid:      a=Open c=Close k=Toggle");
    Serial.println("Sensors:       t=Float Switch | l=Flow Rate | L=CSV Log");
    Serial.println("Manual Flow:   N=Manual Start Case 1 (Commissioning)");
    Serial.println("Case 1 Sim:    n=Normal x=Sump High r=Return to Normal (Auto Case 2 in 10s)");
    Serial.println("Commission:    T/m=Enter Commissioning Mode");
    Serial.println("------------------------------------------------\n");
}

static void handleSerialCommand(char cmd) {
    switch (cmd) {
        // --- 1. System Commands (Highest Priority) ---
        case 's':
        case 'S':
        case ' ': // Spacebar - System Emergency Stop
            case1TriggerEmergencyStop();
            break;

        case 'p':
        case 'P':
            printCase1Status();
            printSystemSwitchStatus();
            printFloatSwitchStatus();
            printFlowSensorStatus();
            printSolenoidStatus();
            printPump1Status();
            printPump2Status();
            printPump3Status();
            printStartButtonStatus();
            break;

        case 'h':
        case 'H':
        case '?':
            printHelpMenu();
            break;

        // --- 2. Sensor & Auxiliary Inspection Commands ---
        case 'y':
            Serial.printf("SYSTEM -> %s\n", isSystemOn() ? "ON" : "OFF");
            break;

        case 'Y':
            toggleSystemOn();
            updateCase1WithInputs(isSystemOn(), isFloatSwitchTriggered());
            break;

        case 't':
            Serial.printf("FLOAT -> %s\n", isFloatSwitchTriggered() ? "SUMP HIGH" : "NORMAL");
            break;

        case 'T':
        case 'm':
        case 'M':
            enterCommissioningMode();
            break;

        case 'l':
            Serial.printf("FLOW -> %.2f L/min | %.0f Hz\n", getFlowRateLPM(), getFlowFrequencyHz());
            break;

        case 'L':
            s_csvLoggingActive = !s_csvLoggingActive;
            if (s_csvLoggingActive) {
                s_lastCsvLogTime = millis();
                Serial.println("\n[LOG] Flow logging started");
                Serial.println("timestamp_ms,pump2_pwm,frequency_hz,estimated_flow_lpm");
            } else {
                Serial.println("[LOG] Flow logging stopped\n");
            }
            break;

        case 'a':
        case 'A':
            if (isCase1EmergencyStopActive()) {
                Serial.println("[SAFETY] Blocked: Cannot open solenoid while Emergency Stop is active.");
                break;
            }
            if (!isSystemOn()) {
                Serial.println("[SAFETY] Blocked: Cannot open solenoid while System Switch is OFF.");
                break;
            }
            openSolenoid();
            break;

        case 'c':
        case 'C':
            closeSolenoid();
            break;

        case 'k':
        case 'K':
            if (!isSolenoidOpen()) {
                if (isCase1EmergencyStopActive()) {
                    Serial.println("[SAFETY] Blocked: Cannot open solenoid while Emergency Stop is active.");
                    break;
                }
                if (!isSystemOn()) {
                    Serial.println("[SAFETY] Blocked: Cannot open solenoid while System Switch is OFF.");
                    break;
                }
            }
            toggleSolenoid();
            break;

        // --- 3. Case 1 Simulation Commands ---
        case 'n':
            if (isCase1EmergencyStopActive()) {
                case1ClearEmergencyStop();
            }
            case1TriggerSimulatedNormal();
            break;

        case 'N':
            case1StartNormalFlow();
            break;

        case 'x':
        case 'X':
            case1TriggerSimulatedSumpHigh();
            break;

        case 'r':
        case 'R':
            case1TriggerSimulatedReturnToNormal();
            break;

        // --- 4. Pump 1 Direct Manual Overrides (Single-Motor ZQ-2201 / U2 - Tank -> Sump) ---
        case '0':
            setPump1Duty(0);
            break;
        case '1':
        case '2':
        case '3':
        case '4': {
            if (!checkPumpSafety(1)) break;
            uint8_t duty = (cmd == '1') ? 25 : (cmd == '2') ? 50 : (cmd == '3') ? 75 : 100;
            setPump1Duty(duty);
            break;
        }
        case 'e':
        case 'E':
            if (isCase1EmergencyStopActive()) {
                case1ClearEmergencyStop();
            }
            if (!isSystemOn()) {
                Serial.println("[SAFETY] Blocked: Cannot enable driver while System Switch is OFF.");
                break;
            }
            enablePump1();
            break;
        case 'd':
        case 'D':
            disablePump1();
            break;

        // --- 5. Pump 2 Direct Manual Overrides (Single-Motor ZQ-2201 / U3 - Sump -> Tank) ---
        case '5':
        case '6':
        case '7':
        case '8': {
            if (!checkPumpSafety(2)) break;
            uint8_t duty = (cmd == '5') ? 25 : (cmd == '6') ? 50 : (cmd == '7') ? 75 : 100;
            setPump2Duty(duty);
            break;
        }
        case '9':
            setPump2Duty(0);
            break;
        case 'q':
        case 'Q':
            if (isCase1EmergencyStopActive()) {
                case1ClearEmergencyStop();
            }
            if (!isSystemOn()) {
                Serial.println("[SAFETY] Blocked: Cannot enable driver while System Switch is OFF.");
                break;
            }
            enablePump2();
            break;
        case 'w':
        case 'W':
            disablePump2();
            break;
        case 'z':
        case 'Z':
            emergencyStopPump2();
            break;
        case 'f':
        case 'F':
            setPump2Direction(PUMP_DIR_FORWARD);
            break;
        case 'v':
        case 'V':
            setPump2Direction(PUMP_DIR_REVERSE);
            break;
        case 'o':
        case 'O':
            printPump2Status();
            break;

        // --- 6. Pump 3 Manual Serial Commands (U4) ---
        case 'u':
        case 'U':
            Serial.println("\n[PUMP 3] Manual start requested.");
            if (isCase1EmergencyStopActive()) {
                Serial.println("[PUMP 3] Start rejected: Emergency Stop is active.");
            } else if (!isSystemOn()) {
                Serial.println("[PUMP 3] Start rejected: System switch is OFF.");
            } else if (isCase2ShutdownActive()) {
                Serial.println("[PUMP 3] Start rejected: System latched in SHUTDOWN.");
            } else if (isCase2FlushingActive()) {
                Serial.println("[PUMP 3] Start rejected: Case 2 flush already active.");
            } else {
                Serial.println("[PUMP 3] Start rejected: flush line valve has no sensor.");
                Serial.println("[PUMP 3] Use physical start button (GPIO 34) to start automatic sequence.");
            }
            break;

        case 'i':
        case 'I':
            if (isCase2FlushingActive()) {
                Serial.println("\n[PUMP 3] Stop rejected: Case 2 flush active (use E-Stop to halt).");
            } else if (!isSystemOn()) {
                Serial.println("\n[PUMP 3] Stop rejected: System switch is OFF.");
            } else if (isCase2ShutdownActive()) {
                Serial.println("\n[PUMP 3] Stop rejected: System latched in SHUTDOWN.");
            } else {
                disablePump3(false);
                setPump3Duty(0, false);
                Serial.println("\n[PUMP 3] Stopped by serial command.");
            }
            break;

        case '\r':
        case '\n':
            // Ignore carriage return / newline
            break;
        default:
            Serial.printf("[CMD] Unknown command: '%c'. Send 'h' for help.\n", cmd);
            break;
    }
}

static void handleMainCommandLine(const char* line) {
    if (!line || !*line) return;

    if (strcasecmp(line, "!sys_off") == 0 || strcasecmp(line, "sys_off") == 0 ||
        strcasecmp(line, "sys off") == 0 || strcasecmp(line, "system off") == 0) {
        setSystemOn(false);
        updateCase1WithInputs(isSystemOn(), isFloatSwitchTriggered());
        return;
    }

    if (strcasecmp(line, "!sys_on") == 0 || strcasecmp(line, "sys_on") == 0 ||
        strcasecmp(line, "sys on") == 0 || strcasecmp(line, "system on") == 0) {
        setSystemOn(true);
        updateCase1WithInputs(isSystemOn(), isFloatSwitchTriggered());
        return;
    }

    DutyCommand cmd;
    DutyParseResult res = parseDuty5PercentCommand(line, 2, cmd);

    if (res == DUTY_PARSE_OK) {
        if (!checkPumpSafety(cmd.targetPump)) return;
        if (cmd.targetPump == 1) {
            setPump1Duty(cmd.dutyPercent);
        } else {
            setPump2Duty(cmd.dutyPercent);
        }
    } else if (res != DUTY_PARSE_NOT_A_DUTY_CMD) {
        printDutyParseError(line, cmd);
    } else {
        Serial.printf("[CMD] Unknown command: '%s'. Send 'h' for help.\n", line);
    }
}

static char* trimWhitespace(char* str) {
    if (!str) return nullptr;
    while (*str && isspace((unsigned char)*str)) str++;
    if (!*str) return str;
    char* end = str + strlen(str) - 1;
    while (end > str && isspace((unsigned char)*end)) end--;
    *(end + 1) = '\0';
    return str;
}

static void processIncomingLine(const char* rawLine) {
    char buf[32];
    strncpy(buf, rawLine, sizeof(buf) - 1);
    buf[sizeof(buf) - 1] = '\0';

    char* trimmed = trimWhitespace(buf);
    if (!trimmed || *trimmed == '\0') {
        return;
    }

    size_t len = strlen(trimmed);
    if (len == 1) {
        char c = trimmed[0];
        if (isCommissioningModeActive()) {
            handleCommissioningCommand(c);
        } else {
            handleSerialCommand(c);
        }
    } else {
        if (isCommissioningModeActive()) {
            handleCommissioningCommandLine(trimmed);
        } else {
            handleMainCommandLine(trimmed);
        }
    }
}

void setup() {
    Serial.begin(115200);

    // CRITICAL SAFETY INITIALIZATION:
    // Configure all motor driver enable pins (GPIO 13, 26, 16, 17, 21, 22) to inactive (LOW),
    // PWM pins to 0% duty, and solenoid (GPIO 27) to CLOSED immediately at boot.
    // Executed before any delays or serial printing to eliminate driver floating window.
    initPump1();
    initPump2();
    initPump3();
    initSolenoidValve();

    delay(500);

    Serial.println("\n--- LRC ESP32 Hardware Controller ---");
    Serial.println("Outputs: Active");

    // Initialize sensor & switch interfaces
    initSystemSwitch();
    initFloatSwitch();
    initFlowSensor();
    initStartButton();

    // Initialize Case 1 State Machine in SAFE_IDLE (Pumps OFF, Solenoid CLOSED)
    initCase1Controller();

    // Seed Case 1 with initial inputs (Enters SAFE_IDLE, does NOT start Case 1)
    updateCase1WithInputs(isSystemOn(), isFloatSwitchTriggered());

    // Display compact help menu and status line
    printHelpMenu();
    Serial.printf("Initial State: SYSTEM -> %s | FLOAT -> %s | SOLENOID -> %s | CASE 1 -> %s\n\n",
                  isSystemOn() ? "ON" : "OFF",
                  isFloatSwitchTriggered() ? "SUMP HIGH" : "NORMAL",
                  isSolenoidOpen() ? "OPEN" : "CLOSED",
                  getCase1StateStr());
}

void loop() {
    // Continuously update/debounce sensor & button inputs
    updateSystemSwitch();
    updateFloatSwitch();
    updateFlowSensor();
    updateStartButton();

    // Check dedicated physical start button (debounced, active-LOW falling edge)
    // Starts the full automatic Case 1 -> Case 2 sequence
    if (wasStartButtonPressed()) {
        case1StartSequence();
    }

    // Feed debounced inputs into the top-level safety & Case controller state machine
    if (!isCommissioningModeActive()) {
        updateCase1WithInputs(isSystemOn(), isFloatSwitchTriggered());
    }

    // Non-blocking serial command processor with line buffering
    static char s_serialBuffer[32];
    static size_t s_serialBufferLen = 0;
    static unsigned long s_lastCharTime = 0;

    while (Serial.available() > 0) {
        char c = (char)Serial.read();

        // Universal Emergency Stop via spacebar takes effect immediately
        if (c == ' ' && s_serialBufferLen == 0) {
            if (isCommissioningModeActive()) {
                handleCommissioningCommand(' ');
            } else {
                case1TriggerEmergencyStop();
            }
            continue;
        }

        if (c == '\r' || c == '\n') {
            if (s_serialBufferLen > 0) {
                s_serialBuffer[s_serialBufferLen] = '\0';
                processIncomingLine(s_serialBuffer);
                s_serialBufferLen = 0;
            }
        } else {
            if (s_serialBufferLen < sizeof(s_serialBuffer) - 1) {
                s_serialBuffer[s_serialBufferLen++] = c;
                s_lastCharTime = millis();
            } else {
                s_serialBuffer[s_serialBufferLen] = '\0';
                processIncomingLine(s_serialBuffer);
                s_serialBufferLen = 0;
            }
        }
    }

    // 50ms idle timeout for raw terminals that send keystrokes without newline
    if (s_serialBufferLen > 0 && (millis() - s_lastCharTime >= 50)) {
        s_serialBuffer[s_serialBufferLen] = '\0';
        processIncomingLine(s_serialBuffer);
        s_serialBufferLen = 0;
    }

    // Continuous CSV flow logging every 2.5 seconds (when active)
    if (s_csvLoggingActive) {
        if (millis() - s_lastCsvLogTime >= 2500) {
            s_lastCsvLogTime = millis();
            uint8_t pump2Pwm = isPump2Enabled() ? getPump2Duty() : 0;
            uint32_t freqHz = (uint32_t)(getFlowFrequencyHz() + 0.5f);
            Serial.printf("%lu,%u,%lu,%.2f\n",
                          (unsigned long)millis(),
                          (unsigned int)pump2Pwm,
                          (unsigned long)freqHz,
                          getFlowRateLPM());
        }
    }

    // Periodic heartbeat every 15 seconds (suppressed while CSV flow logging is active)
    static unsigned long lastHeartbeat = 0;
    if (!s_csvLoggingActive && (millis() - lastHeartbeat >= 15000)) {
        lastHeartbeat = millis();
        if (isCommissioningModeActive()) {
            Serial.printf("[HEARTBEAT] ESP32 Alive | MODE: COMMISSIONING | Sys: %s | Solenoid: %s | Flow: %.2f L/min | Float: %s\n",
                          isSystemOn() ? "ON" : "OFF",
                          isSolenoidOpen() ? "OPEN" : "CLOSED",
                          getFlowRateLPM(),
                          isFloatSwitchTriggered() ? "TRIGGERED" : "NORMAL");
        } else {
            Serial.printf("[HEARTBEAT] ESP32 Alive | Sys: %s | Solenoid: %s | Flow: %.2f L/min | Float: %s | State: %s | P1: %d%% | P2: %d%% | P3: %d%%\n",
                          isSystemOn() ? "ON" : "OFF",
                          isSolenoidOpen() ? "OPEN" : "CLOSED",
                          getFlowRateLPM(),
                          isFloatSwitchTriggered() ? "TRIGGERED" : "NORMAL",
                          getCase1StateStr(),
                          getCase1Pump1TargetDuty(),
                          getCase1Pump2TargetDuty(),
                          getCase1Pump3TargetDuty());
        }
    }

    delay(10);
}