#include "float_switch.h"

static int s_debouncedReading = HIGH;
static int s_lastRawReading = HIGH;
static unsigned long s_lastDebounceTime = 0;

void initFloatSwitch() {
    // GPIO 35 has an external 10k pull-up resistor on the PCB
    pinMode(FLOAT_SWITCH_PIN, INPUT);

    int raw = digitalRead(FLOAT_SWITCH_PIN);
    s_debouncedReading = raw;
    s_lastRawReading = raw;
    s_lastDebounceTime = millis();

    Serial.println("[FLOAT_SWITCH] Initialized (GPIO 35).");
    Serial.printf("[FLOAT_SWITCH] State: %s\n", isFloatSwitchTriggered() ? "SUMP HIGH" : "NORMAL");
}

void updateFloatSwitch() {
    int currentRaw = digitalRead(FLOAT_SWITCH_PIN);

    if (currentRaw != s_lastRawReading) {
        s_lastDebounceTime = millis();
        s_lastRawReading = currentRaw;
    }

    if ((millis() - s_lastDebounceTime) >= FLOAT_SWITCH_DEBOUNCE_MS) {
        s_debouncedReading = currentRaw;
    }
}

int readFloatSwitchRaw() {
    return digitalRead(FLOAT_SWITCH_PIN);
}

bool isFloatSwitchTriggered() {
    return (s_debouncedReading == FLOAT_SWITCH_TRIGGERED_LEVEL);
}

bool isFloatSwitchNormal() {
    return !isFloatSwitchTriggered();
}

void printFloatSwitchStatus() {
    int raw = digitalRead(FLOAT_SWITCH_PIN);
    bool triggered = isFloatSwitchTriggered();

    Serial.println("--- Float Switch (GPIO 35) ---");
    Serial.printf("  Raw:   %s (%d)\n", (raw == HIGH) ? "HIGH" : "LOW", raw);
    Serial.printf("  State: %s\n", triggered ? "TRIGGERED (SUMP HIGH)" : "NORMAL");
}
