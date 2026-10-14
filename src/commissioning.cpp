#include "commissioning.h"
#include "hardware_config.h"
#include "pump_controller.h"
#include "pump2_controller.h"
#include "case1_controller.h"
#include "float_switch.h"
#include "flow_sensor.h"
#include "system_switch.h"
#include "flush_button.h"
#include "solenoid_valve.h"
#include "duty_parser.h"

// Sub-menu tracking within commissioning mode
typedef enum {
    COMM_SUB_MAIN = 0,
    COMM_SUB_PUMP1,
    COMM_SUB_PUMP2,
    COMM_SUB_SOLENOID
} CommSubMenu;

static bool s_commissioningModeActive = false;
static CommSubMenu s_currentSubMenu = COMM_SUB_MAIN;

bool isCommissioningModeActive() {
    return s_commissioningModeActive;
}

void printCommissioningMenu() {
    Serial.println("\n--- Hardware Commissioning Menu ---");
    Serial.printf("Hardware: %s\n",
                  isCase1HardwareOutputEnabled() ? "ACTIVE" : "DRY-RUN (Outputs Suppressed)");
    Serial.println("Tests:");
    Serial.println("  1 - Pump 1 (U2: Tank -> Sump)");
    Serial.println("  2 - Pump 2 (U3: Sump -> Tank)");
    Serial.println("  3 - Solenoid Valve (GPIO 27)");
    Serial.println("  4 - Float Switch (GPIO 35)");
    Serial.println("  5 - Flow Sensor (GPIO 14)");
    Serial.println("  6 - Flush Button (GPIO 34)");
    Serial.println("  7 - Full Case 1 Sequence");
    Serial.println("  8 - Status Screen");
    Serial.println("  0 - Exit commissioning");
    Serial.println("Controls: s=E-Stop, h=Menu");
    Serial.print("Select [0-8]: ");
}

static void printPumpSubMenu(int pumpNum, const char* driver) {
    Serial.printf("\n--- Pump %d Test (Driver %s) ---\n", pumpNum, driver);
    Serial.printf("  Hardware: %s\n", isCase1HardwareOutputEnabled() ? "ENABLED" : "DISABLED");
    Serial.println("  0=Stop, 1=25%, 2=50%, 3=75%, 4=100%");
    Serial.println("  d<0-100> in 5% steps (e.g. d50)");
    Serial.println("  s=E-Stop, b=Back");
    Serial.print("Command: ");
}

static void printPump1SubMenu() { printPumpSubMenu(1, "U2"); }
static void printPump2SubMenu() { printPumpSubMenu(2, "U3"); }

static void printSolenoidSubMenu() {
    Serial.println("\n--- Solenoid Test (GPIO 27) ---");
    Serial.printf("  State:    %s\n", isSolenoidOpen() ? "OPEN" : "CLOSED");
    Serial.printf("  Hardware: %s\n", isSolenoidHardwareOutputEnabled() ? "ENABLED" : "DISABLED");
    Serial.println("  o/1=Open, c/0=Close, t=Toggle, p=Status, b=Back");
    Serial.print("Command: ");
}

void enterCommissioningMode() {
    s_commissioningModeActive = true;
    s_currentSubMenu = COMM_SUB_MAIN;
    printCommissioningMenu();
}

void exitCommissioningMode() {
    // Put actuators into safe off state
    setPump1Duty(0);
    disablePump1();

    setPump2Duty(0);
    disablePump2();

    closeSolenoid();

    s_commissioningModeActive = false;
    s_currentSubMenu = COMM_SUB_MAIN;

    Serial.println("\n--- Exited Commissioning Mode ---");
    Serial.println("  Actuators safe (Pumps OFF, Solenoid CLOSED).");
    Serial.println("  Returning to normal control.\n");

    // Return control to normal Case 1 application state
    updateCase1WithInputs(isSystemOn(), isFloatSwitchTriggered());
}

// -----------------------------------------------------------------------------
// INDIVIDUAL COMMISSIONING TESTS
// -----------------------------------------------------------------------------

static void runPumpTest(int pumpNum, uint8_t duty) {
    if (duty > 100) duty = 100;

    if (isCase1EmergencyStopActive()) {
        Serial.println("\n[COMMISSIONING] Blocked: Emergency Stop active.");
        return;
    }
    if (!isSystemOn()) {
        Serial.println("\n[COMMISSIONING] Blocked: System Switch OFF.");
        return;
    }

    bool hwEnabled = isCase1HardwareOutputEnabled();
    const char* dirStr = "FORWARD";

    if (pumpNum == 1) {
        if (duty > 0 && hwEnabled) {
            setPump1Duty(duty);
            enablePump1();
        } else {
            if (duty == 0) setPump1Duty(0);
            disablePump1();
        }
        dirStr = (getPump1Direction() == PUMP_DIR_FORWARD) ? "FORWARD" : "REVERSE";
    } else {
        if (duty > 0 && hwEnabled) {
            setPump2Duty(duty);
            enablePump2();
        } else {
            if (duty == 0) setPump2Duty(0);
            disablePump2();
        }
        dirStr = (getPump2Direction() == PUMP_DIR_FORWARD) ? "FORWARD" : "REVERSE";
    }

    Serial.printf("\n--- Pump %d Test ---\n", pumpNum);
    Serial.printf("  Requested Duty:  %d%%\n", duty);
    Serial.printf("  Direction:       %s\n", dirStr);
    Serial.printf("  Hardware output: %s\n", hwEnabled ? "ENABLED" : "DISABLED");
    if (!hwEnabled) {
        Serial.println("  Dry-run: output suppressed.");
    }
}

void runPump1CommissioningTest(uint8_t duty) {
    runPumpTest(1, duty);
}

void runPump2CommissioningTest(uint8_t duty) {
    runPumpTest(2, duty);
}

void runSolenoidCommissioningTest(bool openValve) {
    if (openValve) {
        if (isCase1EmergencyStopActive()) {
            Serial.println("\n[COMMISSIONING] Blocked: Emergency Stop active.");
            return;
        }
        if (!isSystemOn()) {
            Serial.println("\n[COMMISSIONING] Blocked: System Switch OFF.");
            return;
        }
        openSolenoid();
    } else {
        closeSolenoid();
    }

    bool hwEnabled = isSolenoidHardwareOutputEnabled();

    Serial.println("\n--- Solenoid Test ---");
    Serial.printf("  State:    %s\n", openValve ? "OPEN" : "CLOSED");
    Serial.printf("  Hardware: %s\n", hwEnabled ? "ENABLED" : "DISABLED");
    if (!hwEnabled) {
        Serial.println("  Dry-run: output suppressed.");
    }
}

void runFloatSwitchCommissioningTest() {
    updateFloatSwitch();
    int raw = readFloatSwitchRaw();
    bool triggered = isFloatSwitchTriggered();

    Serial.println("\n--- Float Switch Test ---");
    Serial.printf("  Raw:   %s (%d)\n", (raw == HIGH) ? "HIGH" : "LOW", raw);
    Serial.printf("  State: %s\n", triggered ? "SUMP HIGH" : "NORMAL");
}

void runFlowSensorCommissioningTest() {
    updateFlowSensor();
    uint32_t totalPulses = getTotalPulseCount();
    float freqHz = getFlowFrequencyHz();
    float flowLPM = getFlowRateLPM();

    Serial.println("\n--- Flow Sensor Test ---");
    Serial.printf("  Pulses:    %lu\n", (unsigned long)totalPulses);
    Serial.printf("  Frequency: %.2f Hz\n", freqHz);
    Serial.printf("  Flow Rate: %.3f L/min\n", flowLPM);
    Serial.printf("  Status:    %s\n", getFlowRangeStatusStr());
}

void runFlushButtonCommissioningTest() {
    updateFlushButton();
    int raw = getFlushButtonRawState();
    bool pressed = isFlushButtonPhysicallyPressed();

    Serial.println("\n--- Flush Button Test (GPIO 34) ---");
    Serial.printf("  Raw:   %s (%d)\n", (raw == HIGH) ? "HIGH" : "LOW", raw);
    Serial.printf("  State: %s\n", pressed ? "PRESSED" : "RELEASED");
    Serial.println("  Circuit: External 10k pull-up to 3.3V, 100nF filter (Active-LOW)");
}

void runSystemSwitchCommissioningTest() {
    runFlushButtonCommissioningTest();
}

// -----------------------------------------------------------------------------
// FULL CASE 1 COMMISSIONING SEQUENCE
// -----------------------------------------------------------------------------

static void printSimulationStep(const char* stepName,
                                const char* floatDesc,
                                uint8_t p1Target,
                                uint8_t p2Target) {
    Serial.println("--------------------------------------------------");
    Serial.printf(" >>> %s <<<\n", stepName);
    Serial.println("--------------------------------------------------");
    Serial.printf("  Case 1 state:        %s\n", getCase1StateStr());
    Serial.printf("  Float state:         %s\n", floatDesc);
    Serial.printf("  Pump 1 target:       %d%% (%s)\n", p1Target, (p1Target > 0) ? "RUNNING" : "OFF");
    Serial.printf("  Pump 2 target:       %d%% (%s)\n", p2Target, (p2Target > 0) ? "RUNNING" : "OFF");
    Serial.printf("  Solenoid state:      %s\n", isSolenoidOpen() ? "OPEN" : "CLOSED");
    Serial.printf("  Flow reading:        %.2f L/min (%.1f Hz)\n", getFlowRateLPM(), getFlowFrequencyHz());
    Serial.printf("  System state:        %s\n", isSystemOn() ? "SYSTEM ON" : "SYSTEM OFF");
    Serial.printf("  Emergency-stop state:%s\n", isCase1EmergencyStopActive() ? "ACTIVE (TRIPPED)" : "CLEARED (NORMAL)");
    Serial.printf("  Hardware output:     %s\n",
                  isCase1HardwareOutputEnabled() ? "ENABLED (Physical Outputs Active)" : "DISABLED (Dry-Run Simulation)");
}

void runFullCase1SimulationSequence() {
    Serial.println("\n==================================================");
    Serial.println("         FULL CASE 1 COMMISSIONING SEQUENCE       ");
    Serial.println("==================================================");
    Serial.printf("Physical outputs: %s.\n",
                  isCase1HardwareOutputEnabled() ? "ENABLED (Active)" : "STRICTLY DISABLED (Dry-Run)");
    Serial.println("Starting automated Case 1 state machine sequence...\n");

    // Ensure E-Stop is cleared for simulation
    if (isCase1EmergencyStopActive()) {
        case1ClearEmergencyStop();
    }

    // Step 1: NORMAL
    case1TriggerSimulatedNormal();
    printSimulationStep("STEP 1: NORMAL",
                        "NORMAL (Float Open / HIGH)",
                        getCase1Pump1TargetDuty(),
                        getCase1Pump2TargetDuty());
    delay(400);

    // Step 2: SUMP HIGH
    case1TriggerSimulatedSumpHigh();
    printSimulationStep("STEP 2: SUMP HIGH",
                        "SUMP HIGH (Float Closed / LOW)",
                        getCase1Pump1TargetDuty(),
                        getCase1Pump2TargetDuty());
    delay(400);

    // Step 3: RETURN TO NORMAL
    case1TriggerSimulatedReturnToNormal();
    printSimulationStep("STEP 3: RETURN TO NORMAL",
                        "NORMAL (Float Open / HIGH)",
                        getCase1Pump1TargetDuty(),
                        getCase1Pump2TargetDuty());

    Serial.println("--------------------------------------------------");
    Serial.println("Case 1 sequence completed: Verified P1 controls sump level while P2 runs continuously.");
    Serial.println("==================================================\n");
}

// -----------------------------------------------------------------------------
// COMMISSIONING STATUS SCREEN
// -----------------------------------------------------------------------------

void printCommissioningDiagnosticScreen() {
    bool hwPump = isCase1HardwareOutputEnabled();
    bool hwValve = isSolenoidHardwareOutputEnabled();

    Serial.println("\n==================================================");
    Serial.println("         FULL COMMISSIONING STATUS REPORT         ");
    Serial.println("==================================================");
    Serial.println("System:");
    Serial.printf("    State:              %s (Software Control)\n", isSystemOn() ? "ON" : "OFF");
    Serial.printf("    Emergency stop:     %s\n", isCase1EmergencyStopActive() ? "ACTIVE (TRIPPED)" : "CLEARED (NORMAL)");
    Serial.printf("    Flush Button:       %s (GPIO 34)\n", isFlushButtonPhysicallyPressed() ? "PRESSED" : "RELEASED");
    Serial.println();
    Serial.println("Float:");
    Serial.printf("    State:              %s\n", isFloatSwitchTriggered() ? "HIGH (SUMP HIGH / Closed)" : "NORMAL (Open)");
    Serial.println();
    Serial.println("Flow:");
    Serial.printf("    Hz:                 %.2f Hz\n", getFlowFrequencyHz());
    Serial.printf("    L/min:              %.3f L/min\n", getFlowRateLPM());
    Serial.println();
    Serial.println("Pump 1 (ZQ-2201 #1 / U2 - Tank -> Sump):");
    Serial.printf("    Target:             %d%%\n", getCase1Pump1TargetDuty());
    Serial.printf("    Actual software:    %s (%d%%)\n", isPump1Enabled() ? "ENABLED" : "DISABLED", getPump1Duty());
    Serial.printf("    Direction:          %s\n", (getPump1Direction() == PUMP_DIR_FORWARD) ? "FORWARD" : "REVERSE");
    Serial.printf("    Hardware output:    %s\n", hwPump ? "ENABLED" : "DISABLED (Dry-Run)");
    Serial.println();
    Serial.println("Pump 2 (ZQ-2201 #2 / U3 - Sump -> Tank):");
    Serial.printf("    Target:             %d%%\n", getCase1Pump2TargetDuty());
    Serial.printf("    Actual software:    %s (%d%%)\n", isPump2Enabled() ? "ENABLED" : "DISABLED", getPump2Duty());
    Serial.printf("    Direction:          %s\n", (getPump2Direction() == PUMP_DIR_FORWARD) ? "FORWARD" : "REVERSE");
    Serial.printf("    Hardware output:    %s\n", hwPump ? "ENABLED" : "DISABLED (Dry-Run)");
    Serial.println();
    Serial.println("Pump 3 (Flushing / U4 - Reserved): NOT IN USE");
    Serial.println();
    Serial.println("Solenoid (Valve / GPIO 27):");
    Serial.printf("    Commanded state:    %s\n", isSolenoidOpen() ? "OPEN" : "CLOSED");
    Serial.printf("    Hardware output:    %s\n", hwValve ? "ENABLED" : "DISABLED (Dry-Run)");
    Serial.println("==================================================\n");
}

// -----------------------------------------------------------------------------
// COMMISSIONING SERIAL COMMAND DISPATCHER
// -----------------------------------------------------------------------------

static void handlePumpSubMenuCommand(int pumpNum, char cmd) {
    switch (cmd) {
        case '0': runPumpTest(pumpNum, 0); break;
        case '1': runPumpTest(pumpNum, 25); break;
        case '2': runPumpTest(pumpNum, 50); break;
        case '3': runPumpTest(pumpNum, 75); break;
        case '4': runPumpTest(pumpNum, 100); break;
        case 's':
        case 'S': runPumpTest(pumpNum, 0); break;
        case 'b':
        case 'B':
        case 'x':
        case 'X':
            s_currentSubMenu = COMM_SUB_MAIN;
            printCommissioningMenu();
            break;
        case '\r':
        case '\n':
            break;
        default:
            Serial.printf("[PUMP%d TEST] Unknown option: '%c'. Send 0-4, 'd<0-100>', 's', or 'b'.\n", pumpNum, cmd);
            break;
    }
}

bool handleCommissioningCommand(char cmd) {
    if (!s_commissioningModeActive) {
        return false;
    }

    // Universal Emergency Stop (Highest Priority)
    if (cmd == ' ' || cmd == 's' || cmd == 'S') {
        // If in sub-menu, 's' can mean stop actuator unless space is pressed.
        // But system emergency stop takes precedence.
        if (cmd == ' ' || s_currentSubMenu == COMM_SUB_MAIN) {
            case1TriggerEmergencyStop();
            return true;
        }
    }

    // Sub-menu specific handlers
    switch (s_currentSubMenu) {
        case COMM_SUB_PUMP1:
            handlePumpSubMenuCommand(1, cmd);
            return true;

        case COMM_SUB_PUMP2:
            handlePumpSubMenuCommand(2, cmd);
            return true;

        case COMM_SUB_SOLENOID:
            switch (cmd) {
                case '1':
                case 'o':
                case 'O':
                    runSolenoidCommissioningTest(true);
                    break;
                case '0':
                case 'c':
                case 'C':
                    runSolenoidCommissioningTest(false);
                    break;
                case 't':
                case 'T':
                    runSolenoidCommissioningTest(!isSolenoidOpen());
                    break;
                case 'p':
                case 'P':
                    printSolenoidStatus();
                    break;
                case 'b':
                case 'B':
                case 'x':
                case 'X':
                    s_currentSubMenu = COMM_SUB_MAIN;
                    printCommissioningMenu();
                    break;
                case '\r':
                case '\n':
                    break;
                default:
                    Serial.printf("[SOLENOID TEST] Unknown option: '%c'. Send 'o', 'c', 't', 'p', or 'b'.\n", cmd);
                    break;
            }
            return true;

        case COMM_SUB_MAIN:
        default:
            switch (cmd) {
                case '1':
                    s_currentSubMenu = COMM_SUB_PUMP1;
                    printPump1SubMenu();
                    break;

                case '2':
                    s_currentSubMenu = COMM_SUB_PUMP2;
                    printPump2SubMenu();
                    break;

                case '3':
                    s_currentSubMenu = COMM_SUB_SOLENOID;
                    printSolenoidSubMenu();
                    break;

                case '4':
                    runFloatSwitchCommissioningTest();
                    break;

                case '5':
                    runFlowSensorCommissioningTest();
                    break;

                case '6':
                    runFlushButtonCommissioningTest();
                    break;

                case '7':
                    runFullCase1SimulationSequence();
                    break;

                case '8':
                case 'p':
                case 'P':
                    printCommissioningDiagnosticScreen();
                    break;

                case '0':
                case 'x':
                case 'X':
                case 'q':
                case 'Q':
                    exitCommissioningMode();
                    break;

                case 'h':
                case 'H':
                case '?':
                    printCommissioningMenu();
                    break;

                case '\r':
                case '\n':
                    break;

                default:
                    Serial.printf("[COMMISSIONING] Unknown test command '%c'. Send 'h' for menu, '0' to exit.\n", cmd);
                    break;
            }
            return true;
    }
}

bool handleCommissioningCommandLine(const char* line) {
    if (!s_commissioningModeActive) {
        return false;
    }

    if (!line || !*line) return false;

    // Universal Emergency Stop (Highest Priority)
    if (strcmp(line, "s") == 0 || strcmp(line, "S") == 0) {
        if (s_currentSubMenu == COMM_SUB_MAIN) {
            case1TriggerEmergencyStop();
            return true;
        } else if (s_currentSubMenu == COMM_SUB_PUMP1) {
            runPump1CommissioningTest(0);
            return true;
        } else if (s_currentSubMenu == COMM_SUB_PUMP2) {
            runPump2CommissioningTest(0);
            return true;
        }
    }

    switch (s_currentSubMenu) {
        case COMM_SUB_PUMP1:
        case COMM_SUB_PUMP2: {
            int pump = (s_currentSubMenu == COMM_SUB_PUMP1) ? 1 : 2;
            DutyCommand cmd;
            DutyParseResult res = parseDuty5PercentCommand(line, pump, cmd);
            if (res == DUTY_PARSE_OK) {
                runPumpTest(pump, cmd.dutyPercent);
                return true;
            } else if (res != DUTY_PARSE_NOT_A_DUTY_CMD) {
                printDutyParseError(line, cmd);
                return true;
            }
            Serial.printf("[PUMP%d TEST] Unknown command: '%s'. Send 0-4, d<0-100>, 's', or 'b'.\n", pump, line);
            return true;
        }

        case COMM_SUB_SOLENOID:
            Serial.printf("[SOLENOID TEST] Unknown command: '%s'. Send 'o', 'c', 't', 'p', or 'b'.\n", line);
            return true;

        case COMM_SUB_MAIN:
        default: {
            DutyCommand cmd;
            DutyParseResult res = parseDuty5PercentCommand(line, 0, cmd);
            if (res == DUTY_PARSE_OK) {
                if (cmd.targetPump == 1) {
                    runPump1CommissioningTest(cmd.dutyPercent);
                    return true;
                } else if (cmd.targetPump == 2) {
                    runPump2CommissioningTest(cmd.dutyPercent);
                    return true;
                } else {
                    Serial.println("[COMMISSIONING] Please enter sub-menu 1 for Pump 1 or 2 for Pump 2, or specify 'd1 <%%>' / 'd2 <%%>'.");
                    return true;
                }
            } else if (res != DUTY_PARSE_NOT_A_DUTY_CMD) {
                printDutyParseError(line, cmd);
                return true;
            }
            Serial.printf("[COMMISSIONING] Unknown command: '%s'. Select test [0-8] or send 'h' for help.\n", line);
            return true;
        }
    }
}

