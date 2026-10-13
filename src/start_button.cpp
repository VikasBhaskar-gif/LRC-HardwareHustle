#include "start_button.h"

static int s_debouncedReading = HIGH;
static int s_lastRawReading = HIGH;
static unsigned long s_lastDebounceTime = 0;
static bool s_pressDetected = false;

void initStartButton() {
    if (IS_PIN_VALID(START_BUTTON_PIN)) {
        // Physical momentary push button wired to PCB connector labelled ON/OFF SWITCH (GPIO 34).
        // ESP32 GPIO 34 is input-only (GPI) and does NOT have internal pull-ups in silicon.
        // MUST configure as INPUT (never INPUT_PULLUP). The PCB schematic provides an
        // external 10 kΩ pull-up to 3.3V (R10) and 100 nF RC filter capacitor (C9) to GND.
        pinMode(START_BUTTON_PIN, INPUT);

        int raw = digitalRead(START_BUTTON_PIN);
        s_debouncedReading = raw;
        s_lastRawReading = raw;
        s_lastDebounceTime = millis();
        s_pressDetected = false;

        Serial.println("[START_BUTTON] Initialized (GPIO 34, external 10k pull-up). Starts full auto sequence.");
    }
}

void updateStartButton() {
    if (!IS_PIN_VALID(START_BUTTON_PIN)) return;

    int currentRaw = digitalRead(START_BUTTON_PIN);

    if (currentRaw != s_lastRawReading) {
        s_lastDebounceTime = millis();
        s_lastRawReading = currentRaw;
    }

    if ((millis() - s_lastDebounceTime) >= START_BUTTON_DEBOUNCE_MS) {
        if (currentRaw != s_debouncedReading) {
            // State has stabilized to a new value
            if (currentRaw == START_BUTTON_ACTIVE_LEVEL && s_debouncedReading != START_BUTTON_ACTIVE_LEVEL) {
                // Falling edge: Transition from RELEASED (HIGH) to PRESSED (LOW)
                s_pressDetected = true;
            }
            s_debouncedReading = currentRaw;
        }
    }
}

bool wasStartButtonPressed() {
    if (s_pressDetected) {
        s_pressDetected = false; // Clear one-shot trigger
        return true;
    }
    return false;
}

bool isStartButtonPhysicallyPressed() {
    return (s_debouncedReading == START_BUTTON_ACTIVE_LEVEL);
}

int getStartButtonRawState() {
    if (!IS_PIN_VALID(START_BUTTON_PIN)) return HIGH;
    return digitalRead(START_BUTTON_PIN);
}

void printStartButtonStatus() {
    int raw = getStartButtonRawState();
    bool pressed = isStartButtonPhysicallyPressed();

    Serial.println("--- Start Button (GPIO 34) ---");
    Serial.printf("  Raw:   %s (%d)\n", (raw == HIGH) ? "HIGH" : "LOW", raw);
    Serial.printf("  State: %s\n", pressed ? "PRESSED" : "RELEASED");
    Serial.println("  Role:  Starts complete Case 1 -> Case 2 automatic sequence");
}
