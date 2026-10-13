#include "pump3_controller.h"
#include "case1_controller.h"

static bool s_pump3Enabled = false;
static uint8_t s_pump3Duty = 0;
static PumpDirection s_pump3Dir = PUMP3_DEFAULT_DIRECTION;

static uint32_t calculateRawDuty(uint8_t percent) {
    if (percent > 100) percent = 100;
    const uint32_t maxCount = (1UL << PUMP3_PWM_RESOLUTION_BITS) - 1;
    uint32_t raw = (percent * maxCount) / 100;
    if (!PUMP3_PWM_ACTIVE_HIGH) {
        raw = maxCount - raw;
    }
    return raw;
}

static uint8_t getInactiveEnLevel() {
    return PUMP3_EN_ACTIVE_HIGH ? LOW : HIGH;
}

static uint8_t getActiveEnLevel() {
    return PUMP3_EN_ACTIVE_HIGH ? HIGH : LOW;
}

static uint32_t getSafeZeroDuty() {
    return PUMP3_PWM_ACTIVE_HIGH ? 0 : ((1UL << PUMP3_PWM_RESOLUTION_BITS) - 1);
}

static void applyHardwareOutputs() {
    const uint32_t safeZero = getSafeZeroDuty();

    // Strict dry-run protection: If hardware outputs are not enabled, force physical pins safe/inactive
    if (!isCase1HardwareOutputEnabled()) {
        if (IS_PIN_VALID(PUMP3_L_PWM_PIN)) {
            ledcWrite(PUMP3_L_PWM_CHANNEL, safeZero);
        }
        if (IS_PIN_VALID(PUMP3_R_PWM_PIN)) {
            ledcWrite(PUMP3_R_PWM_CHANNEL, safeZero);
        }
        if (IS_PIN_VALID(PUMP3_L_EN_PIN)) {
            digitalWrite(PUMP3_L_EN_PIN, getInactiveEnLevel());
        }
        if (IS_PIN_VALID(PUMP3_R_EN_PIN)) {
            digitalWrite(PUMP3_R_EN_PIN, getInactiveEnLevel());
        }
        return;
    }

    if (!s_pump3Enabled) {
        // Driver disabled: Zero both PWM channels first
        if (IS_PIN_VALID(PUMP3_L_PWM_PIN)) {
            ledcWrite(PUMP3_L_PWM_CHANNEL, safeZero);
        }
        if (IS_PIN_VALID(PUMP3_R_PWM_PIN)) {
            ledcWrite(PUMP3_R_PWM_CHANNEL, safeZero);
        }

        // De-assert Enable pins to driver inactive level
        if (IS_PIN_VALID(PUMP3_L_EN_PIN)) {
            digitalWrite(PUMP3_L_EN_PIN, getInactiveEnLevel());
        }
        if (IS_PIN_VALID(PUMP3_R_EN_PIN)) {
            digitalWrite(PUMP3_R_EN_PIN, getInactiveEnLevel());
        }
        return;
    }

    // Driver enabled: Assert Enable pins
    if (IS_PIN_VALID(PUMP3_L_EN_PIN)) {
        digitalWrite(PUMP3_L_EN_PIN, getActiveEnLevel());
    }
    if (IS_PIN_VALID(PUMP3_R_EN_PIN)) {
        digitalWrite(PUMP3_R_EN_PIN, getActiveEnLevel());
    }

    // Apply directional PWM
    if (s_pump3Duty == 0) {
        if (IS_PIN_VALID(PUMP3_L_PWM_PIN)) ledcWrite(PUMP3_L_PWM_CHANNEL, safeZero);
        if (IS_PIN_VALID(PUMP3_R_PWM_PIN)) ledcWrite(PUMP3_R_PWM_CHANNEL, safeZero);
    } else if (s_pump3Dir == PUMP_DIR_FORWARD) {
        // Forward: L_PWM3 gets active duty, R_PWM3 held at 0
        if (IS_PIN_VALID(PUMP3_L_PWM_PIN)) {
            ledcWrite(PUMP3_L_PWM_CHANNEL, calculateRawDuty(s_pump3Duty));
        }
        if (IS_PIN_VALID(PUMP3_R_PWM_PIN)) {
            ledcWrite(PUMP3_R_PWM_CHANNEL, safeZero);
        }
    } else {
        // Reverse: R_PWM3 gets active duty, L_PWM3 held at 0
        if (IS_PIN_VALID(PUMP3_L_PWM_PIN)) {
            ledcWrite(PUMP3_L_PWM_CHANNEL, safeZero);
        }
        if (IS_PIN_VALID(PUMP3_R_PWM_PIN)) {
            ledcWrite(PUMP3_R_PWM_CHANNEL, calculateRawDuty(s_pump3Duty));
        }
    }
}

void initPump3() {
    s_pump3Enabled = false;
    s_pump3Duty = 0;
    s_pump3Dir = PUMP3_DEFAULT_DIRECTION;

    // Set enable pins LOW before configuring as outputs
    if (IS_PIN_VALID(PUMP3_L_EN_PIN)) {
        digitalWrite(PUMP3_L_EN_PIN, getInactiveEnLevel());
        pinMode(PUMP3_L_EN_PIN, OUTPUT);
    }
    if (IS_PIN_VALID(PUMP3_R_EN_PIN)) {
        digitalWrite(PUMP3_R_EN_PIN, getInactiveEnLevel());
        pinMode(PUMP3_R_EN_PIN, OUTPUT);
    }

    // Configure PWM channels for forward and reverse
    if (IS_PIN_VALID(PUMP3_L_PWM_PIN)) {
        ledcSetup(PUMP3_L_PWM_CHANNEL, PUMP3_PWM_FREQ_HZ, PUMP3_PWM_RESOLUTION_BITS);
        ledcAttachPin(PUMP3_L_PWM_PIN, PUMP3_L_PWM_CHANNEL);
        ledcWrite(PUMP3_L_PWM_CHANNEL, getSafeZeroDuty());
    }

    if (IS_PIN_VALID(PUMP3_R_PWM_PIN)) {
        ledcSetup(PUMP3_R_PWM_CHANNEL, PUMP3_PWM_FREQ_HZ, PUMP3_PWM_RESOLUTION_BITS);
        ledcAttachPin(PUMP3_R_PWM_PIN, PUMP3_R_PWM_CHANNEL);
        ledcWrite(PUMP3_R_PWM_CHANNEL, getSafeZeroDuty());
    }

    Serial.println("[PUMP 3] Initialized (Driver U4, stopped).");
}

void enablePump3(bool printFeedback) {
    s_pump3Enabled = true;
    applyHardwareOutputs();
    if (printFeedback) {
        Serial.println("Pump 3 -> ENABLED");
    }
}

void disablePump3(bool printFeedback) {
    s_pump3Enabled = false;
    applyHardwareOutputs();
    if (printFeedback) {
        Serial.println("Pump 3 -> DISABLED");
    }
}

void emergencyStopPump3() {
    s_pump3Duty = 0;
    s_pump3Enabled = false;
    applyHardwareOutputs();
    Serial.println("Pump 3 -> STOP");
}

bool setPump3Duty(uint8_t percent, bool printFeedback) {
    if (percent > 100) {
        percent = 100;
    }

    s_pump3Duty = percent;

    if (percent > 0 && !s_pump3Enabled) {
        // Auto-enable when commanded to a positive duty
        s_pump3Enabled = true;
    }

    applyHardwareOutputs();

    if (printFeedback) {
        if (s_pump3Duty == 0) {
            Serial.println("Pump 3 -> STOP");
        } else {
            Serial.printf("Pump 3 -> %d%%\n", s_pump3Duty);
        }
    }
    return true;
}

void setPump3Direction(PumpDirection dir) {
    s_pump3Dir = dir;
    applyHardwareOutputs();
    Serial.printf("Pump 3 Direction -> %s\n", (dir == PUMP_DIR_FORWARD) ? "FORWARD" : "REVERSE");
}

PumpDirection getPump3Direction() {
    return s_pump3Dir;
}

const char* getPump3DirectionStr() {
    return (s_pump3Dir == PUMP_DIR_FORWARD) ? "FORWARD (L_PWM3 Active)" : "REVERSE (R_PWM3 Active)";
}

bool isPump3Enabled() {
    return s_pump3Enabled;
}

uint8_t getPump3Duty() {
    return s_pump3Duty;
}

void printPump3Status() {
    const uint32_t rawVal = calculateRawDuty(s_pump3Duty);
    Serial.println("--- Pump 3 (U4) ---");
    Serial.printf("  State:     %s\n", s_pump3Enabled ? "ENABLED" : "DISABLED");
    Serial.printf("  Direction: %s\n", (s_pump3Dir == PUMP_DIR_FORWARD) ? "FORWARD" : "REVERSE");
    Serial.printf("  Duty:      %d%% (PWM: %lu/255)\n", s_pump3Duty, (unsigned long)rawVal);
    Serial.printf("  Hardware:  %s\n", isCase1HardwareOutputEnabled() ? "ENABLED" : "DISABLED");
}
