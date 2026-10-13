#include "pump2_controller.h"
#include "case1_controller.h"

static bool s_pump2Enabled = false;
static uint8_t s_pump2Duty = 0;
static PumpDirection s_pump2Dir = PUMP2_DEFAULT_DIRECTION;

static uint32_t calculateRawDuty(uint8_t percent) {
    if (percent > 100) percent = 100;
    const uint32_t maxCount = (1UL << PUMP2_PWM_RESOLUTION_BITS) - 1;
    uint32_t raw = (percent * maxCount) / 100;
    if (!PUMP2_PWM_ACTIVE_HIGH) {
        raw = maxCount - raw;
    }
    return raw;
}

static uint8_t getInactiveEnLevel() {
    return PUMP2_EN_ACTIVE_HIGH ? LOW : HIGH;
}

static uint8_t getActiveEnLevel() {
    return PUMP2_EN_ACTIVE_HIGH ? HIGH : LOW;
}

static uint32_t getSafeZeroDuty() {
    return PUMP2_PWM_ACTIVE_HIGH ? 0 : ((1UL << PUMP2_PWM_RESOLUTION_BITS) - 1);
}

static void applyHardwareOutputs() {
    const uint32_t safeZero = getSafeZeroDuty();

    // Strict dry-run protection: If hardware outputs are not enabled, force physical pins safe/inactive
    if (!isCase1HardwareOutputEnabled()) {
        if (IS_PIN_VALID(PUMP2_L_PWM_PIN)) {
            ledcWrite(PUMP2_L_PWM_CHANNEL, safeZero);
        }
        if (IS_PIN_VALID(PUMP2_R_PWM_PIN)) {
            ledcWrite(PUMP2_R_PWM_CHANNEL, safeZero);
        }
        if (IS_PIN_VALID(PUMP2_L_EN_PIN)) {
            digitalWrite(PUMP2_L_EN_PIN, getInactiveEnLevel());
        }
        if (IS_PIN_VALID(PUMP2_R_EN_PIN)) {
            digitalWrite(PUMP2_R_EN_PIN, getInactiveEnLevel());
        }
        return;
    }

    if (!s_pump2Enabled) {
        // Driver disabled: Zero both PWM channels first
        if (IS_PIN_VALID(PUMP2_L_PWM_PIN)) {
            ledcWrite(PUMP2_L_PWM_CHANNEL, safeZero);
        }
        if (IS_PIN_VALID(PUMP2_R_PWM_PIN)) {
            ledcWrite(PUMP2_R_PWM_CHANNEL, safeZero);
        }

        // De-assert Enable pins to driver inactive level
        if (IS_PIN_VALID(PUMP2_L_EN_PIN)) {
            digitalWrite(PUMP2_L_EN_PIN, getInactiveEnLevel());
        }
        if (IS_PIN_VALID(PUMP2_R_EN_PIN)) {
            digitalWrite(PUMP2_R_EN_PIN, getInactiveEnLevel());
        }
        return;
    }

    // Driver enabled: Assert Enable pins
    if (IS_PIN_VALID(PUMP2_L_EN_PIN)) {
        digitalWrite(PUMP2_L_EN_PIN, getActiveEnLevel());
    }
    if (IS_PIN_VALID(PUMP2_R_EN_PIN)) {
        digitalWrite(PUMP2_R_EN_PIN, getActiveEnLevel());
    }

    // Apply directional PWM
    if (s_pump2Duty == 0) {
        if (IS_PIN_VALID(PUMP2_L_PWM_PIN)) ledcWrite(PUMP2_L_PWM_CHANNEL, safeZero);
        if (IS_PIN_VALID(PUMP2_R_PWM_PIN)) ledcWrite(PUMP2_R_PWM_CHANNEL, safeZero);
    } else if (s_pump2Dir == PUMP_DIR_FORWARD) {
        // Forward: L_PWM2 gets active duty, R_PWM2 held at 0
        if (IS_PIN_VALID(PUMP2_L_PWM_PIN)) {
            ledcWrite(PUMP2_L_PWM_CHANNEL, calculateRawDuty(s_pump2Duty));
        }
        if (IS_PIN_VALID(PUMP2_R_PWM_PIN)) {
            ledcWrite(PUMP2_R_PWM_CHANNEL, safeZero);
        }
    } else {
        // Reverse: R_PWM2 gets active duty, L_PWM2 held at 0
        if (IS_PIN_VALID(PUMP2_L_PWM_PIN)) {
            ledcWrite(PUMP2_L_PWM_CHANNEL, safeZero);
        }
        if (IS_PIN_VALID(PUMP2_R_PWM_PIN)) {
            ledcWrite(PUMP2_R_PWM_CHANNEL, calculateRawDuty(s_pump2Duty));
        }
    }
}

void initPump2() {
    s_pump2Enabled = false;
    s_pump2Duty = 0;
    s_pump2Dir = PUMP2_DEFAULT_DIRECTION;

    // Set enable pins LOW before configuring as outputs
    if (IS_PIN_VALID(PUMP2_L_EN_PIN)) {
        digitalWrite(PUMP2_L_EN_PIN, getInactiveEnLevel());
        pinMode(PUMP2_L_EN_PIN, OUTPUT);
    }
    if (IS_PIN_VALID(PUMP2_R_EN_PIN)) {
        digitalWrite(PUMP2_R_EN_PIN, getInactiveEnLevel());
        pinMode(PUMP2_R_EN_PIN, OUTPUT);
    }

    // Configure PWM channels for forward and reverse
    if (IS_PIN_VALID(PUMP2_L_PWM_PIN)) {
        ledcSetup(PUMP2_L_PWM_CHANNEL, PUMP2_PWM_FREQ_HZ, PUMP2_PWM_RESOLUTION_BITS);
        ledcAttachPin(PUMP2_L_PWM_PIN, PUMP2_L_PWM_CHANNEL);
        ledcWrite(PUMP2_L_PWM_CHANNEL, getSafeZeroDuty());
    }

    if (IS_PIN_VALID(PUMP2_R_PWM_PIN)) {
        ledcSetup(PUMP2_R_PWM_CHANNEL, PUMP2_PWM_FREQ_HZ, PUMP2_PWM_RESOLUTION_BITS);
        ledcAttachPin(PUMP2_R_PWM_PIN, PUMP2_R_PWM_CHANNEL);
        ledcWrite(PUMP2_R_PWM_CHANNEL, getSafeZeroDuty());
    }

    Serial.println("[PUMP 2] Initialized (Driver U3, stopped).");
}

void enablePump2(bool printFeedback) {
    s_pump2Enabled = true;
    applyHardwareOutputs();
    if (printFeedback) {
        Serial.println("Pump 2 -> ENABLED");
    }
}

void disablePump2(bool printFeedback) {
    s_pump2Enabled = false;
    applyHardwareOutputs();
    if (printFeedback) {
        Serial.println("Pump 2 -> DISABLED");
    }
}

void emergencyStopPump2() {
    s_pump2Duty = 0;
    s_pump2Enabled = false;
    applyHardwareOutputs();
    Serial.println("Pump 2 -> STOP");
}

bool setPump2Duty(uint8_t percent, bool printFeedback) {
    if (percent > 100) {
        percent = 100;
    }

    s_pump2Duty = percent;

    if (percent > 0 && !s_pump2Enabled) {
        // Auto-enable when commanded to a positive duty
        s_pump2Enabled = true;
    }

    applyHardwareOutputs();

    if (printFeedback) {
        if (s_pump2Duty == 0) {
            Serial.println("Pump 2 -> STOP");
        } else {
            Serial.printf("Pump 2 -> %d%%\n", s_pump2Duty);
        }
    }
    return true;
}

void setPump2Direction(PumpDirection dir) {
    s_pump2Dir = dir;
    applyHardwareOutputs();
    Serial.printf("Pump 2 Direction -> %s\n", (dir == PUMP_DIR_FORWARD) ? "FORWARD" : "REVERSE");
}

PumpDirection getPump2Direction() {
    return s_pump2Dir;
}

const char* getPump2DirectionStr() {
    return (s_pump2Dir == PUMP_DIR_FORWARD) ? "FORWARD (L_PWM2 Active)" : "REVERSE (R_PWM2 Active)";
}

bool isPump2Enabled() {
    return s_pump2Enabled;
}

uint8_t getPump2Duty() {
    return s_pump2Duty;
}

void printPump2Status() {
    const uint32_t rawVal = calculateRawDuty(s_pump2Duty);
    Serial.println("--- Pump 2 (U3) ---");
    Serial.printf("  State:     %s\n", s_pump2Enabled ? "ENABLED" : "DISABLED");
    Serial.printf("  Direction: %s\n", (s_pump2Dir == PUMP_DIR_FORWARD) ? "FORWARD" : "REVERSE");
    Serial.printf("  Duty:      %d%% (PWM: %lu/255)\n", s_pump2Duty, (unsigned long)rawVal);
    Serial.printf("  Hardware:  %s\n", isCase1HardwareOutputEnabled() ? "ENABLED" : "DISABLED");
}
