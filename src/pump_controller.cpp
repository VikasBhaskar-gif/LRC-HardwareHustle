#include "pump_controller.h"
#include "case1_controller.h"

static bool s_pump1Enabled = false;
static uint8_t s_pump1Duty = 0;
static PumpDirection s_pump1Dir = PUMP1_DEFAULT_DIRECTION;

static uint32_t calculateRawDuty(uint8_t percent) {
    if (percent > 100) percent = 100;
    const uint32_t maxCount = (1UL << PUMP1_PWM_RESOLUTION_BITS) - 1;
    uint32_t raw = (percent * maxCount) / 100;
    if (!PUMP1_PWM_ACTIVE_HIGH) {
        raw = maxCount - raw;
    }
    return raw;
}

static uint8_t getInactiveEnLevel() {
    return PUMP1_EN_ACTIVE_HIGH ? LOW : HIGH;
}

static uint8_t getActiveEnLevel() {
    return PUMP1_EN_ACTIVE_HIGH ? HIGH : LOW;
}

static uint32_t getSafeZeroDuty() {
    return PUMP1_PWM_ACTIVE_HIGH ? 0 : ((1UL << PUMP1_PWM_RESOLUTION_BITS) - 1);
}

static void applyHardwareOutputs() {
    const uint32_t safeZero = getSafeZeroDuty();

    // Strict dry-run protection: If hardware outputs are not enabled, force physical pins safe/inactive
    if (!isCase1HardwareOutputEnabled()) {
        if (IS_PIN_VALID(PUMP1_L_PWM_PIN)) {
            ledcWrite(PUMP1_L_PWM_CHANNEL, safeZero);
        }
        if (IS_PIN_VALID(PUMP1_R_PWM_PIN)) {
            ledcWrite(PUMP1_R_PWM_CHANNEL, safeZero);
        }
        if (IS_PIN_VALID(PUMP1_L_EN_PIN)) {
            digitalWrite(PUMP1_L_EN_PIN, getInactiveEnLevel());
        }
        if (IS_PIN_VALID(PUMP1_R_EN_PIN)) {
            digitalWrite(PUMP1_R_EN_PIN, getInactiveEnLevel());
        }
        return;
    }

    if (!s_pump1Enabled) {
        // Driver disabled: Force zero duty on both PWM channels first
        if (IS_PIN_VALID(PUMP1_L_PWM_PIN)) {
            ledcWrite(PUMP1_L_PWM_CHANNEL, safeZero);
        }
        if (IS_PIN_VALID(PUMP1_R_PWM_PIN)) {
            ledcWrite(PUMP1_R_PWM_CHANNEL, safeZero);
        }

        // De-assert Enable pins to driver inactive level
        if (IS_PIN_VALID(PUMP1_L_EN_PIN)) {
            digitalWrite(PUMP1_L_EN_PIN, getInactiveEnLevel());
        }
        if (IS_PIN_VALID(PUMP1_R_EN_PIN)) {
            digitalWrite(PUMP1_R_EN_PIN, getInactiveEnLevel());
        }
        return;
    }

    // Driver enabled: Assert Enable pins
    if (IS_PIN_VALID(PUMP1_L_EN_PIN)) {
        digitalWrite(PUMP1_L_EN_PIN, getActiveEnLevel());
    }
    if (IS_PIN_VALID(PUMP1_R_EN_PIN)) {
        digitalWrite(PUMP1_R_EN_PIN, getActiveEnLevel());
    }

    // Apply directional PWM
    if (s_pump1Duty == 0) {
        if (IS_PIN_VALID(PUMP1_L_PWM_PIN)) ledcWrite(PUMP1_L_PWM_CHANNEL, safeZero);
        if (IS_PIN_VALID(PUMP1_R_PWM_PIN)) ledcWrite(PUMP1_R_PWM_CHANNEL, safeZero);
    } else if (s_pump1Dir == PUMP_DIR_FORWARD) {
        // Forward: L_PWM gets active duty, R_PWM is held at 0
        if (IS_PIN_VALID(PUMP1_L_PWM_PIN)) {
            ledcWrite(PUMP1_L_PWM_CHANNEL, calculateRawDuty(s_pump1Duty));
        }
        if (IS_PIN_VALID(PUMP1_R_PWM_PIN)) {
            ledcWrite(PUMP1_R_PWM_CHANNEL, safeZero);
        }
    } else {
        // Reverse: R_PWM gets active duty, L_PWM is held at 0
        if (IS_PIN_VALID(PUMP1_L_PWM_PIN)) {
            ledcWrite(PUMP1_L_PWM_CHANNEL, safeZero);
        }
        if (IS_PIN_VALID(PUMP1_R_PWM_PIN)) {
            ledcWrite(PUMP1_R_PWM_CHANNEL, calculateRawDuty(s_pump1Duty));
        }
    }
}

void initPump1() {
    s_pump1Enabled = false;
    s_pump1Duty = 0;
    s_pump1Dir = PUMP1_DEFAULT_DIRECTION;

    // Set enable pins LOW before configuring as outputs
    if (IS_PIN_VALID(PUMP1_L_EN_PIN)) {
        digitalWrite(PUMP1_L_EN_PIN, getInactiveEnLevel());
        pinMode(PUMP1_L_EN_PIN, OUTPUT);
    }
    if (IS_PIN_VALID(PUMP1_R_EN_PIN)) {
        digitalWrite(PUMP1_R_EN_PIN, getInactiveEnLevel());
        pinMode(PUMP1_R_EN_PIN, OUTPUT);
    }

    // Configure PWM channels for forward and reverse
    if (IS_PIN_VALID(PUMP1_L_PWM_PIN)) {
        ledcSetup(PUMP1_L_PWM_CHANNEL, PUMP1_PWM_FREQ_HZ, PUMP1_PWM_RESOLUTION_BITS);
        ledcAttachPin(PUMP1_L_PWM_PIN, PUMP1_L_PWM_CHANNEL);
        ledcWrite(PUMP1_L_PWM_CHANNEL, getSafeZeroDuty());
    }

    if (IS_PIN_VALID(PUMP1_R_PWM_PIN)) {
        ledcSetup(PUMP1_R_PWM_CHANNEL, PUMP1_PWM_FREQ_HZ, PUMP1_PWM_RESOLUTION_BITS);
        ledcAttachPin(PUMP1_R_PWM_PIN, PUMP1_R_PWM_CHANNEL);
        ledcWrite(PUMP1_R_PWM_CHANNEL, getSafeZeroDuty());
    }

    Serial.println("[PUMP 1] Initialized (Driver U2, stopped).");
}

void enablePump1(bool printFeedback) {
    s_pump1Enabled = true;
    applyHardwareOutputs();
    if (printFeedback) {
        Serial.println("Pump 1 -> ENABLED");
    }
}

void disablePump1(bool printFeedback) {
    s_pump1Enabled = false;
    applyHardwareOutputs();
    if (printFeedback) {
        Serial.println("Pump 1 -> DISABLED");
    }
}

void emergencyStopPump1() {
    s_pump1Duty = 0;
    s_pump1Enabled = false;
    applyHardwareOutputs();
    Serial.println("Pump 1 -> STOP");
}

bool setPump1Duty(uint8_t percent, bool printFeedback) {
    if (percent > 100) {
        percent = 100;
    }

    s_pump1Duty = percent;

    if (percent > 0 && !s_pump1Enabled) {
        // Auto-enable when commanded to a positive duty
        s_pump1Enabled = true;
    }

    applyHardwareOutputs();

    if (printFeedback) {
        if (s_pump1Duty == 0) {
            Serial.println("Pump 1 -> STOP");
        } else {
            Serial.printf("Pump 1 -> %d%%\n", s_pump1Duty);
        }
    }
    return true;
}

void setPump1Direction(PumpDirection dir) {
    s_pump1Dir = dir;
    applyHardwareOutputs();
    Serial.printf("Pump 1 Direction -> %s\n", (dir == PUMP_DIR_FORWARD) ? "FORWARD" : "REVERSE");
}

PumpDirection getPump1Direction() {
    return s_pump1Dir;
}

const char* getPump1DirectionStr() {
    return (s_pump1Dir == PUMP_DIR_FORWARD) ? "FORWARD (L_PWM Active)" : "REVERSE (R_PWM Active)";
}

bool isPump1Enabled() {
    return s_pump1Enabled;
}

uint8_t getPump1Duty() {
    return s_pump1Duty;
}

void printPump1Status() {
    const uint32_t rawVal = calculateRawDuty(s_pump1Duty);
    Serial.println("--- Pump 1 (U2) ---");
    Serial.printf("  State:     %s\n", s_pump1Enabled ? "ENABLED" : "DISABLED");
    Serial.printf("  Direction: %s\n", (s_pump1Dir == PUMP_DIR_FORWARD) ? "FORWARD" : "REVERSE");
    Serial.printf("  Duty:      %d%% (PWM: %lu/255)\n", s_pump1Duty, (unsigned long)rawVal);
    Serial.printf("  Hardware:  %s\n", isCase1HardwareOutputEnabled() ? "ENABLED" : "DISABLED");
}
