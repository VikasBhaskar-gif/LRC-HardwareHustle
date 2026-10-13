#include "case1_controller.h"
#include "pump_controller.h"
#include "pump2_controller.h"
#include "pump3_controller.h"
#include "solenoid_valve.h"
#include "hardware_config.h"
#include "float_switch.h"
#include "system_switch.h"

static Case1State s_currentState = CASE1_STATE_SAFE_IDLE;
static Case1InputSource s_inputSource = CASE1_SRC_REAL_SENSOR;
static uint8_t s_pump1NormalDuty = CASE1_PUMP1_DEFAULT_NORMAL_DUTY;
static uint8_t s_pump2NormalDuty = CASE1_PUMP2_DEFAULT_NORMAL_DUTY;
static uint8_t s_pump1TargetDuty = 0;
static uint8_t s_pump2TargetDuty = 0;
static uint8_t s_pump3TargetDuty = 0;
static bool s_hardwareOutputEnabled = true; // Set to true: Master hardware outputs ENABLED for physical operation
static bool s_emergencyStopActive = false;   // Highest priority safety flag

static bool s_lastRealTriggered = false;
static bool s_hasInitialized = false;

// Return-to-normal 10-second transition delay variables
static unsigned long s_transitionStartTime = 0;
static bool s_transitionTimerActive = false;

// Case 2 Flush timing variables (Non-blocking millis)
static unsigned long s_flushStartTime = 0;
static uint32_t s_flushDurationMs = CASE2_FLUSH_DURATION_MS; // Default: 90000 ms

static void applyHardwareIfEnabled() {
    if (s_hardwareOutputEnabled) {
        // Pump 1 (U2)
        if (s_pump1TargetDuty > 0) {
            setPump1Duty(s_pump1TargetDuty, false);
        } else {
            disablePump1(false);
        }

        // Pump 2 (U3)
        if (s_pump2TargetDuty > 0) {
            setPump2Duty(s_pump2TargetDuty, false);
        } else {
            disablePump2(false);
        }

        // Pump 3 (U4)
        if (s_pump3TargetDuty > 0) {
            setPump3Duty(s_pump3TargetDuty, false);
        } else {
            disablePump3(false);
        }
    } else {
        Serial.println("[CASE1] Hardware outputs suppressed.");
    }
}

void initCase1Controller() {
    s_currentState = CASE1_STATE_SAFE_IDLE;
    s_inputSource = CASE1_SRC_REAL_SENSOR;
    s_pump1NormalDuty = CASE1_PUMP1_DEFAULT_NORMAL_DUTY;
    s_pump2NormalDuty = CASE1_PUMP2_DEFAULT_NORMAL_DUTY;
    s_pump1TargetDuty = 0;
    s_pump2TargetDuty = 0;
    s_pump3TargetDuty = 0;
    s_hardwareOutputEnabled = true;
    s_emergencyStopActive = false;
    s_hasInitialized = false;
    s_transitionStartTime = 0;
    s_transitionTimerActive = false;
    s_flushStartTime = 0;
    s_flushDurationMs = CASE2_FLUSH_DURATION_MS;

    closeSolenoid();
    applyHardwareIfEnabled();

    Serial.println("[CASE1] Initialized in SAFE_IDLE (Pumps: OFF, Solenoid: CLOSED).");
}

bool case1StartSequence() {
    if (s_emergencyStopActive) {
        Serial.println("\n[START] Blocked: Emergency Stop is active.");
        return false;
    }
    if (!isSystemOn() || s_currentState == CASE1_STATE_SYSTEM_OFF) {
        Serial.println("\n[START] Blocked: System is OFF.");
        return false;
    }
    if (s_currentState == CASE1_STATE_NORMAL ||
        s_currentState == CASE1_STATE_SUMP_HIGH ||
        s_currentState == CASE1_STATE_RETURN_TO_NORMAL) {
        Serial.println("\n[START] Ignored: Automatic sequence is already running.");
        return false;
    }
    if (s_currentState == CASE2_STATE_FLUSHING) {
        Serial.println("\n[START] Ignored: Case 2 flush is already active.");
        return false;
    }
    if (s_currentState == CASE2_STATE_SHUTDOWN) {
        Serial.println("\n[START] Ignored: System latched in final shutdown. Reset system to re-arm.");
        return false;
    }

    Serial.println("\n[START] Physical start button detected: Starting automatic Case 1 -> Case 2 sequence.");
    return case1StartNormalFlow();
}

void case1TriggerEmergencyStop() {
    s_emergencyStopActive = true;
    s_currentState = CASE1_STATE_EMERGENCY_STOP;
    s_pump1TargetDuty = 0;
    s_pump2TargetDuty = 0;
    s_pump3TargetDuty = 0;

    // Immediately command safe halt to all motor drivers and solenoid
    emergencyStopPump1();
    emergencyStopPump2();
    emergencyStopPump3();
    closeSolenoid();

    Serial.println("\nE-STOP -> ACTIVE (All 3 Pumps Halted, Solenoid Closed)");
}

void case1ClearEmergencyStop() {
    s_emergencyStopActive = false;
    s_currentState = CASE1_STATE_SAFE_IDLE;
    s_pump1TargetDuty = 0;
    s_pump2TargetDuty = 0;
    s_pump3TargetDuty = 0;
    closeSolenoid();
    applyHardwareIfEnabled();
    Serial.println("\nE-STOP -> CLEARED (System in SAFE_IDLE, Motors OFF)");
}

bool isCase1EmergencyStopActive() {
    return s_emergencyStopActive;
}

bool triggerCase2FlushSequence() {
    if (s_emergencyStopActive) {
        Serial.println("\n[CASE 2] Cannot start flush: Emergency Stop is active.");
        return false;
    }

    if (s_currentState == CASE1_STATE_SYSTEM_OFF) {
        Serial.println("\n[CASE 2] Cannot start flush: System switch is OFF.");
        return false;
    }

    if (s_currentState == CASE2_STATE_FLUSHING) {
        Serial.println("\n[CASE 2] Flush already in progress.");
        return false;
    }

    if (s_currentState == CASE2_STATE_SHUTDOWN) {
        Serial.println("\n[CASE 2] System in shutdown. Cycle switch to reset.");
        return false;
    }

    if (s_currentState != CASE1_STATE_NORMAL &&
        s_currentState != CASE1_STATE_SUMP_HIGH &&
        s_currentState != CASE1_STATE_RETURN_TO_NORMAL) {
        Serial.printf("\n[CASE 2] Cannot start flush in state: %s\n", getCase1StateStr());
        return false;
    }

    // --- STEP 1: ISOLATE 10L PROCESS TANK ---
    closeSolenoid();

    // --- STEP 2: CONFIGURE PUMP TARGETS (SIMULTANEOUS 3-PUMP OPERATION) ---
    s_pump1TargetDuty = s_pump1NormalDuty;     // Keep Pump 1 running at 50%
    s_pump2TargetDuty = s_pump2NormalDuty;     // Keep Pump 2 running at 100%
    s_pump3TargetDuty = CASE2_PUMP3_FLUSH_DUTY; // Start Pump 3 at 50%

    // --- STEP 3: START 90-SECOND NON-BLOCKING TIMER ---
    s_flushStartTime = millis();
    s_currentState = CASE2_STATE_FLUSHING;
    s_transitionTimerActive = false;

    // Apply hardware outputs immediately
    applyHardwareIfEnabled();

    Serial.println("\n[CASE 2] Automatic flush sequence started.");
    Serial.println("[CASE 2] Solenoid CLOSED (Isolating 10L process tank).");
    Serial.printf("[CASE 2] PUMP 3 STARTED at %d%% duty.\n", s_pump3TargetDuty);
    Serial.printf("[CASE 2] All three pumps running (P1: %d%%, P2: %d%%, P3: %d%%). Flush timer started: %lu seconds.\n",
                  s_pump1TargetDuty, s_pump2TargetDuty, s_pump3TargetDuty, (unsigned long)(s_flushDurationMs / 1000UL));

    return true;
}

bool isCase2FlushingActive() {
    return (s_currentState == CASE2_STATE_FLUSHING);
}

bool isCase2ShutdownActive() {
    return (s_currentState == CASE2_STATE_SHUTDOWN);
}

unsigned long getCase2FlushRemainingMs() {
    if (s_currentState == CASE2_STATE_FLUSHING) {
        unsigned long elapsed = millis() - s_flushStartTime;
        if (elapsed >= s_flushDurationMs) {
            return 0;
        }
        return (s_flushDurationMs - elapsed);
    }
    return 0;
}

uint32_t getCase2FlushDurationMs() {
    return s_flushDurationMs;
}

void setCase2FlushDurationMs(uint32_t ms) {
    s_flushDurationMs = ms;
    Serial.printf("[CASE 2] Flush duration updated to %lu ms\n", (unsigned long)s_flushDurationMs);
}

bool isCase1TransitionDelayActive() {
    return (s_currentState == CASE1_STATE_RETURN_TO_NORMAL && s_transitionTimerActive);
}

unsigned long getCase1TransitionRemainingMs() {
    if (s_currentState == CASE1_STATE_RETURN_TO_NORMAL && s_transitionTimerActive) {
        unsigned long elapsed = millis() - s_transitionStartTime;
        if (elapsed >= CASE1_RETURN_DELAY_MS) {
            return 0;
        }
        return (CASE1_RETURN_DELAY_MS - elapsed);
    }
    return 0;
}

void updateCase1WithInputs(bool isSystemSwitchOn, bool isFloatSwitchTriggered) {
    // 1. HIGHEST PRIORITY: Emergency Stop
    if (s_emergencyStopActive) {
        s_pump1TargetDuty = 0;
        s_pump2TargetDuty = 0;
        s_pump3TargetDuty = 0;
        s_transitionTimerActive = false;
        return;
    }

    // 2. NEXT PRIORITY: System ON/OFF Switch
    if (!isSystemSwitchOn) {
        if (s_currentState != CASE1_STATE_SYSTEM_OFF) {
            s_currentState = CASE1_STATE_SYSTEM_OFF;
            s_pump1TargetDuty = 0;
            s_pump2TargetDuty = 0;
            s_pump3TargetDuty = 0;
            s_transitionTimerActive = false;
            closeSolenoid();

            Serial.println("\nSYSTEM -> OFF");
            Serial.println("CASE 1 -> SYSTEM OFF");
            Serial.println("P1: 0% | P2: 0% | P3: 0% | Solenoid: CLOSED");
            applyHardwareIfEnabled();
        }
        return;
    }

    // 3. CASE 2 FLUSH TIMING MONITOR (Non-blocking millis)
    if (s_currentState == CASE2_STATE_FLUSHING) {
        unsigned long elapsed = millis() - s_flushStartTime;
        if (elapsed >= s_flushDurationMs) {
            // 90-second flush duration expired: execute complete shutdown
            s_currentState = CASE2_STATE_SHUTDOWN;
            s_pump1TargetDuty = 0;
            s_pump2TargetDuty = 0;
            s_pump3TargetDuty = 0;
            closeSolenoid();
            disablePump1(false);
            disablePump2(false);
            disablePump3(false);
            applyHardwareIfEnabled();

            Serial.printf("\n[CASE 2] %lu-second flush complete.\n", (unsigned long)(s_flushDurationMs / 1000UL));
            Serial.println("[CASE 2] All pumps STOPPED. Motor drivers disabled.");
            Serial.println("[CASE 2] Solenoid remains CLOSED. System latched in SHUTDOWN.");
        }
        // While flushing, all 3 pumps run continuously for the 90s duration
        return;
    }

    // 4. CASE 2 LATCHED FINAL SHUTDOWN STATE
    if (s_currentState == CASE2_STATE_SHUTDOWN) {
        // Enforce latched safe OFF: all pumps 0%, solenoid closed
        // Prevents automatic pump restart, float-switch reaction, or button restart.
        return;
    }

    // 5. SYSTEM SWITCH TRANSITION FROM OFF TO ON (OR INITIAL BOOT)
    // CRITICAL SAFETY FIX: Turning switch ON or booting must NEVER automatically start motors!
    // Rearms any previous shutdown latch and enters SAFE_IDLE with motors OFF and solenoid CLOSED.
    if (s_currentState == CASE1_STATE_SYSTEM_OFF || !s_hasInitialized) {
        s_hasInitialized = true;
        s_lastRealTriggered = isFloatSwitchTriggered;
        s_inputSource = CASE1_SRC_REAL_SENSOR;
        s_currentState = CASE1_STATE_SAFE_IDLE;
        s_pump1TargetDuty = 0;
        s_pump2TargetDuty = 0;
        s_pump3TargetDuty = 0;
        s_transitionTimerActive = false;
        closeSolenoid();
        applyHardwareIfEnabled();

        Serial.println("\nSYSTEM -> ON");
        Serial.println("CASE 1 -> SAFE IDLE");
        Serial.println("P1: 0% | P2: 0% | P3: 0% | Solenoid: CLOSED");
        Serial.println("[SAFETY] Motors idle. Press physical start button (GPIO 34) to start sequence.");
        return;
    }

    // 6. SAFE IDLE STATE: Motors remain OFF until operator presses Start button
    if (s_currentState == CASE1_STATE_SAFE_IDLE) {
        // Keep track of float switch passively so state is accurate when started
        s_lastRealTriggered = isFloatSwitchTriggered;
        return;
    }

    // 7. RETURN TO NORMAL 10-SECOND DELAY MONITOR
    // When returning from Sump High, Solenoid stays OPEN, P1=50%, P2=100%, P3=0% for 10 seconds.
    // If float switch becomes high again during this 10s window, cancel and return to SUMP_HIGH.
    // When 10 seconds elapse, automatically start Case 2 flush.
    if (s_currentState == CASE1_STATE_RETURN_TO_NORMAL) {
        // Check if float switch detected fluid high again
        if (isFloatSwitchTriggered) {
            s_transitionTimerActive = false;
            s_lastRealTriggered = true;
            s_currentState = CASE1_STATE_SUMP_HIGH;
            s_pump1TargetDuty = 0;
            s_pump2TargetDuty = s_pump2NormalDuty;
            s_pump3TargetDuty = 0;
            openSolenoid();
            applyHardwareIfEnabled();

            Serial.println("\nFLOAT -> SUMP HIGH (Return delay canceled: fluid high again)");
            Serial.println("CASE 1 -> SUMP HIGH");
            Serial.printf("P1: 0% | P2: %d%% | Solenoid: OPEN\n", s_pump2TargetDuty);
            return;
        }

        if (s_transitionTimerActive) {
            unsigned long elapsed = millis() - s_transitionStartTime;
            if (elapsed >= CASE1_RETURN_DELAY_MS) {
                s_transitionTimerActive = false;
                Serial.println("\n[AUTO-SEQUENCE] 10-second return delay completed.");
                Serial.println("[AUTO-SEQUENCE] Automatically transitioning to Case 2 flush sequence.");
                triggerCase2FlushSequence();
                return;
            }
        }
        return;
    }

    // 8. OPERATIONAL CASE 1: Float switch edge detection while actively circulating
    if (s_currentState == CASE1_STATE_NORMAL || s_currentState == CASE1_STATE_SUMP_HIGH) {
        if (s_inputSource == CASE1_SRC_REAL_SENSOR && (isFloatSwitchTriggered != s_lastRealTriggered)) {
            s_lastRealTriggered = isFloatSwitchTriggered;
            s_pump3TargetDuty = 0;

            if (isFloatSwitchTriggered) {
                // NORMAL -> SUMP HIGH (External fluid charged: stop Pump 1, keep Pump 2 running)
                s_transitionTimerActive = false;
                s_currentState = CASE1_STATE_SUMP_HIGH;
                s_pump1TargetDuty = 0;
                s_pump2TargetDuty = s_pump2NormalDuty;
                openSolenoid(); // solenoid OPEN during sump recovery
                applyHardwareIfEnabled();
                Serial.println("\nFLOAT -> SUMP HIGH");
                Serial.println("CASE 1 -> SUMP HIGH");
                Serial.printf("P1: 0% | P2: %d%% | Solenoid: OPEN\n", s_pump2TargetDuty);
            } else {
                // SUMP HIGH -> RETURN TO NORMAL (Fluid cleared: resume Pump 1 at 50%, start 1s transition timer)
                s_currentState = CASE1_STATE_RETURN_TO_NORMAL;
                s_pump1TargetDuty = s_pump1NormalDuty;
                s_pump2TargetDuty = s_pump2NormalDuty;
                openSolenoid();
                s_transitionStartTime = millis();
                s_transitionTimerActive = true;
                applyHardwareIfEnabled();
                Serial.println("\nFLOAT -> NORMAL");
                Serial.println("CASE 1 -> RETURN TO NORMAL");
                Serial.println("[AUTO-SEQUENCE] 10-second delay started. Solenoid OPEN. Case 2 starts automatically.");
                Serial.printf("P1: %d%% | P2: %d%% | Solenoid: OPEN\n", s_pump1TargetDuty, s_pump2TargetDuty);
            }
        }
    }
}

bool case1StartNormalFlow() {
    if (s_emergencyStopActive) {
        Serial.println("[SAFETY] Blocked: Cannot start Normal Flow while Emergency Stop is active.");
        return false;
    }
    if (!isSystemOn() || s_currentState == CASE1_STATE_SYSTEM_OFF) {
        Serial.println("[SAFETY] Blocked: Cannot start Normal Flow while System Switch is OFF.");
        return false;
    }
    if (s_currentState == CASE2_STATE_FLUSHING) {
        Serial.println("[SAFETY] Blocked: Cannot start Normal Flow while Case 2 Flush is running.");
        return false;
    }
    if (s_currentState == CASE2_STATE_SHUTDOWN) {
        Serial.println("[SAFETY] Blocked: System in shutdown. Cycle switch to reset.");
        return false;
    }

    s_inputSource = CASE1_SRC_REAL_SENSOR;
    s_pump3TargetDuty = 0;
    bool floatTrig = isFloatSwitchTriggered();
    s_lastRealTriggered = floatTrig;

    if (!floatTrig) {
        s_currentState = CASE1_STATE_NORMAL;
        s_pump1TargetDuty = s_pump1NormalDuty; // 50%
        s_pump2TargetDuty = s_pump2NormalDuty; // 100%
        openSolenoid();
        Serial.println("\nCASE 1 -> NORMAL");
        Serial.printf("NORMAL FLOW -> Pump 1: %d%% | Pump 2: %d%% | Solenoid: OPEN\n", s_pump1TargetDuty, s_pump2TargetDuty);
    } else {
        s_currentState = CASE1_STATE_SUMP_HIGH;
        s_pump1TargetDuty = 0;
        s_pump2TargetDuty = s_pump2NormalDuty; // 100%
        openSolenoid();
        Serial.println("\nCASE 1 -> SUMP HIGH");
        Serial.printf("NORMAL FLOW -> Pump 1: 0% | Pump 2: %d%% | Solenoid: OPEN (Sump High)\n", s_pump2TargetDuty);
    }

    applyHardwareIfEnabled();
    return true;
}

void case1TriggerSimulatedNormal() {
    if (s_emergencyStopActive) {
        Serial.println("[SAFETY] Blocked: Cannot simulate Case 1 while Emergency Stop is active.");
        return;
    }
    if (s_currentState == CASE1_STATE_SYSTEM_OFF) {
        Serial.println("[SAFETY] Blocked: Cannot simulate Case 1 while System Switch is OFF.");
        return;
    }
    if (s_currentState == CASE2_STATE_FLUSHING) {
        Serial.println("[SAFETY] Blocked: Cannot simulate Case 1 while Case 2 Flush is running.");
        return;
    }
    if (s_currentState == CASE2_STATE_SHUTDOWN) {
        Serial.println("[SAFETY] Blocked: Cannot simulate Case 1 while in Case 2 Shutdown.");
        return;
    }

    s_inputSource = CASE1_SRC_SIMULATION;
    s_currentState = CASE1_STATE_NORMAL;
    s_pump1TargetDuty = s_pump1NormalDuty;
    s_pump2TargetDuty = s_pump2NormalDuty;
    s_pump3TargetDuty = 0;
    openSolenoid();

    Serial.println("\nCASE 1 -> NORMAL");
    Serial.printf("P1: %d%% | P2: %d%% | P3: 0%% | Solenoid: OPEN\n", s_pump1TargetDuty, s_pump2TargetDuty);
    applyHardwareIfEnabled();
}

void case1TriggerSimulatedSumpHigh() {
    if (s_emergencyStopActive) {
        Serial.println("[SAFETY] Blocked: Cannot simulate Case 1 while Emergency Stop is active.");
        return;
    }
    if (s_currentState == CASE1_STATE_SYSTEM_OFF) {
        Serial.println("[SAFETY] Blocked: Cannot simulate Case 1 while System Switch is OFF.");
        return;
    }
    if (s_currentState == CASE2_STATE_FLUSHING) {
        Serial.println("[SAFETY] Blocked: Cannot simulate Case 1 while Case 2 Flush is running.");
        return;
    }
    if (s_currentState == CASE2_STATE_SHUTDOWN) {
        Serial.println("[SAFETY] Blocked: Cannot simulate Case 1 while in Case 2 Shutdown.");
        return;
    }

    s_inputSource = CASE1_SRC_SIMULATION;
    s_transitionTimerActive = false;
    s_currentState = CASE1_STATE_SUMP_HIGH;
    s_pump1TargetDuty = 0;
    s_pump2TargetDuty = s_pump2NormalDuty;
    s_pump3TargetDuty = 0;
    openSolenoid();

    Serial.println("\nCASE 1 -> SUMP HIGH (Simulated)");
    Serial.printf("P1: 0% | P2: %d%% | P3: 0%% | Solenoid: OPEN\n", s_pump2TargetDuty);
    applyHardwareIfEnabled();
}

void case1TriggerSimulatedReturnToNormal() {
    if (s_emergencyStopActive) {
        Serial.println("[SAFETY] Blocked: Cannot simulate Case 1 while Emergency Stop is active.");
        return;
    }
    if (s_currentState == CASE1_STATE_SYSTEM_OFF) {
        Serial.println("[SAFETY] Blocked: Cannot simulate Case 1 while System Switch is OFF.");
        return;
    }
    if (s_currentState == CASE2_STATE_FLUSHING) {
        Serial.println("[SAFETY] Blocked: Cannot simulate Case 1 while Case 2 Flush is running.");
        return;
    }
    if (s_currentState == CASE2_STATE_SHUTDOWN) {
        Serial.println("[SAFETY] Blocked: Cannot simulate Case 1 while in Case 2 Shutdown.");
        return;
    }

    s_inputSource = CASE1_SRC_SIMULATION;
    s_currentState = CASE1_STATE_RETURN_TO_NORMAL;
    s_pump1TargetDuty = s_pump1NormalDuty;
    s_pump2TargetDuty = s_pump2NormalDuty;
    s_pump3TargetDuty = 0;
    openSolenoid();
    s_transitionStartTime = millis();
    s_transitionTimerActive = true;

    Serial.println("\nCASE 1 -> RETURN TO NORMAL (Simulated)");
    Serial.println("[AUTO-SEQUENCE] 10-second delay started. Solenoid OPEN. Flush starts automatically.");
    Serial.printf("P1: %d%% | P2: %d%% | P3: 0%% | Solenoid: OPEN\n", s_pump1TargetDuty, s_pump2TargetDuty);
    applyHardwareIfEnabled();
}

Case1State getCase1State() {
    return s_currentState;
}

const char* getCase1StateStr() {
    switch (s_currentState) {
        case CASE1_STATE_SAFE_IDLE:        return "SAFE_IDLE";
        case CASE1_STATE_EMERGENCY_STOP:   return "EMERGENCY_STOP";
        case CASE1_STATE_SYSTEM_OFF:       return "SYSTEM_OFF";
        case CASE1_STATE_NORMAL:           return "NORMAL";
        case CASE1_STATE_SUMP_HIGH:        return "SUMP_HIGH";
        case CASE1_STATE_RETURN_TO_NORMAL: return "RETURN_TO_NORMAL";
        case CASE2_STATE_FLUSHING:         return "CASE2_FLUSHING";
        case CASE2_STATE_SHUTDOWN:         return "CASE2_SHUTDOWN";
        default:                           return "UNKNOWN";
    }
}

Case1InputSource getCase1InputSource() {
    return s_inputSource;
}

const char* getCase1InputSourceStr() {
    return (s_inputSource == CASE1_SRC_REAL_SENSOR) ? "REAL_SENSOR" : "SIMULATION";
}

uint8_t getCase1Pump1TargetDuty() {
    return s_pump1TargetDuty;
}

uint8_t getCase1Pump2TargetDuty() {
    return s_pump2TargetDuty;
}

uint8_t getCase1Pump3TargetDuty() {
    return s_pump3TargetDuty;
}

void setCase1Pump1NormalDuty(uint8_t duty) {
    if (duty > 100) duty = 100;
    s_pump1NormalDuty = duty;
    Serial.printf("[CASE1] Pump 1 normal duty set to %d%%\n", s_pump1NormalDuty);
}

void setCase1Pump2NormalDuty(uint8_t duty) {
    if (duty > 100) duty = 100;
    s_pump2NormalDuty = duty;
    Serial.printf("[CASE1] Pump 2 normal duty set to %d%%\n", s_pump2NormalDuty);
}

void setCase1HardwareOutputEnabled(bool enabled) {
    s_hardwareOutputEnabled = enabled;
    setSolenoidHardwareOutputEnabled(enabled);
    applyHardwareIfEnabled();
    Serial.printf("[CASE1] Hardware output: %s\n", enabled ? "ENABLED" : "DISABLED");
}

bool isCase1HardwareOutputEnabled() {
    return s_hardwareOutputEnabled;
}

void printCase1Status() {
    Serial.println("--- System Status ---");
    Serial.printf("  State:    %s\n", getCase1StateStr());
    Serial.printf("  E-Stop:   %s\n", s_emergencyStopActive ? "ACTIVE" : "CLEARED");
    Serial.printf("  Pump 1:   %d%%\n", s_pump1TargetDuty);
    Serial.printf("  Pump 2:   %d%%\n", s_pump2TargetDuty);
    Serial.printf("  Pump 3:   %d%%\n", s_pump3TargetDuty);
    Serial.printf("  Solenoid: %s\n", isSolenoidOpen() ? "OPEN" : "CLOSED");
    if (s_currentState == CASE1_STATE_RETURN_TO_NORMAL && s_transitionTimerActive) {
        Serial.printf("  Delay:    %lu ms until automatic Case 2 flush\n", getCase1TransitionRemainingMs());
    }
    if (s_currentState == CASE2_STATE_FLUSHING) {
        Serial.printf("  Flush:    %lu ms remaining\n", getCase2FlushRemainingMs());
    }
    Serial.printf("  Hardware: %s\n", s_hardwareOutputEnabled ? "ENABLED" : "DISABLED");
}
