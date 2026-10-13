#include "system_switch.h"

// System ON/OFF is controlled via Serial Monitor (software state).
// Physical connector labelled ON/OFF SWITCH on PCB is wired to GPIO 34 and serves
// as the physical Flush Button, completely decoupled from this system switch logic.
static bool s_systemOn = true;

void initSystemSwitch() {
    s_systemOn = true;
    Serial.println("[SYSTEM] Initialized (Software control).");
    Serial.printf("[SYSTEM] State: %s\n", s_systemOn ? "SYSTEM ON" : "SYSTEM OFF");
}

void updateSystemSwitch() {
    // Software state controlled via serial commands - no hardware GPIO reading
}

bool isSystemOn() {
    return s_systemOn;
}

void setSystemOn(bool enabled) {
    s_systemOn = enabled;
}

void toggleSystemOn() {
    s_systemOn = !s_systemOn;
}

int getSystemSwitchRawState() {
    return s_systemOn ? HIGH : LOW;
}

void printSystemSwitchStatus() {
    Serial.println("--- System Enable (Software Control) ---");
    Serial.printf("  State: %s\n", s_systemOn ? "SYSTEM ON" : "SYSTEM OFF");
}
