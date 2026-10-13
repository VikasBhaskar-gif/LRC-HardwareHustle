#include "solenoid_valve.h"
#include "case1_controller.h"
#include "system_switch.h"

static bool s_solenoidOpen = false;
static bool s_hardwareOutputEnabled = true; // Default ENABLED: Physical hardware output active

static uint8_t getOpenLevel() {
    return SOLENOID_ACTIVE_HIGH ? HIGH : LOW;
}

static uint8_t getClosedLevel() {
    return SOLENOID_ACTIVE_HIGH ? LOW : HIGH;
}

static void applyHardwareOutputs() {
    if (s_hardwareOutputEnabled) {
        if (IS_PIN_VALID(SOLENOID_VALVE_PIN)) {
            digitalWrite(SOLENOID_VALVE_PIN, s_solenoidOpen ? getOpenLevel() : getClosedLevel());
        }
    } else {
        // Keep pin LOW during dry-run simulation
        if (IS_PIN_VALID(SOLENOID_VALVE_PIN)) {
            digitalWrite(SOLENOID_VALVE_PIN, getClosedLevel());
        }
        Serial.println("[SOLENOID] Dry-run: output suppressed.");
    }
}

void initSolenoidValve() {
    s_solenoidOpen = false;
    s_hardwareOutputEnabled = true;

    if (IS_PIN_VALID(SOLENOID_VALVE_PIN)) {
        // Set safe closed state (LOW) before enabling output
        digitalWrite(SOLENOID_VALVE_PIN, getClosedLevel());
        pinMode(SOLENOID_VALVE_PIN, OUTPUT);
        digitalWrite(SOLENOID_VALVE_PIN, getClosedLevel());
    }

    Serial.println("[SOLENOID] Initialized (GPIO 27, CLOSED).");
}

void openSolenoid() {
    // Defense-in-depth: Enforce system safety hierarchy
    if (isCase1EmergencyStopActive()) {
        Serial.println("[SAFETY] Blocked: Cannot open solenoid while Emergency Stop is active.");
        return;
    }
    if (!isSystemOn()) {
        Serial.println("[SAFETY] Blocked: Cannot open solenoid while System Switch is OFF.");
        return;
    }

    s_solenoidOpen = true;
    applyHardwareOutputs();
    Serial.println("SOLENOID -> OPEN");
}

void closeSolenoid() {
    s_solenoidOpen = false;
    applyHardwareOutputs();
    Serial.println("SOLENOID -> CLOSED");
}

void toggleSolenoid() {
    if (s_solenoidOpen) {
        closeSolenoid();
    } else {
        openSolenoid();
    }
}

bool isSolenoidOpen() {
    return s_solenoidOpen;
}

void setSolenoidHardwareOutputEnabled(bool enabled) {
    s_hardwareOutputEnabled = enabled;
    Serial.printf("[SOLENOID] Hardware output: %s\n", enabled ? "ENABLED" : "DISABLED");
    applyHardwareOutputs();
}

bool isSolenoidHardwareOutputEnabled() {
    return s_hardwareOutputEnabled;
}

void printSolenoidStatus() {
    Serial.println("--- Solenoid Valve (GPIO 27) ---");
    Serial.printf("  State:    %s\n", s_solenoidOpen ? "OPEN" : "CLOSED");
    Serial.printf("  Hardware: %s\n", s_hardwareOutputEnabled ? "ENABLED" : "DISABLED");
}
