#include "pump_controller.h"
#include "bts7960_pump.h"
#include "case1_controller.h"

// -----------------------------------------------------------------------------
// BTS7960 Motor Driver Implementation
// -----------------------------------------------------------------------------

uint32_t Bts7960Pump::calculateRawDuty(uint8_t percent) const {
    if (percent > 100) percent = 100;
    const uint32_t maxCount = (1UL << resBits) - 1;
    return (percent * maxCount) / 100;
}

void Bts7960Pump::init() {
    enabled = false;
    duty = 0;
    direction = PUMP_DIR_FORWARD;

    if (IS_PIN_VALID(lEnPin)) {
        digitalWrite(lEnPin, LOW);
        pinMode(lEnPin, OUTPUT);
    }
    if (IS_PIN_VALID(rEnPin)) {
        digitalWrite(rEnPin, LOW);
        pinMode(rEnPin, OUTPUT);
    }

    if (IS_PIN_VALID(lPwmPin)) {
        ledcSetup(lChannel, pwmFreq, resBits);
        ledcAttachPin(lPwmPin, lChannel);
        ledcWrite(lChannel, 0);
    }
    if (IS_PIN_VALID(rPwmPin)) {
        ledcSetup(rChannel, pwmFreq, resBits);
        ledcAttachPin(rPwmPin, rChannel);
        ledcWrite(rChannel, 0);
    }

    Serial.println(initTag);
}

void Bts7960Pump::applyOutputs() {
    if (!isCase1HardwareOutputEnabled() || !enabled) {
        if (IS_PIN_VALID(lPwmPin)) ledcWrite(lChannel, 0);
        if (IS_PIN_VALID(rPwmPin)) ledcWrite(rChannel, 0);
        if (IS_PIN_VALID(lEnPin))  digitalWrite(lEnPin, LOW);
        if (IS_PIN_VALID(rEnPin))  digitalWrite(rEnPin, LOW);
        return;
    }

    if (IS_PIN_VALID(lEnPin)) digitalWrite(lEnPin, HIGH);
    if (IS_PIN_VALID(rEnPin)) digitalWrite(rEnPin, HIGH);

    if (duty == 0) {
        if (IS_PIN_VALID(lPwmPin)) ledcWrite(lChannel, 0);
        if (IS_PIN_VALID(rPwmPin)) ledcWrite(rChannel, 0);
    } else if (direction == PUMP_DIR_FORWARD) {
        if (IS_PIN_VALID(lPwmPin)) ledcWrite(lChannel, calculateRawDuty(duty));
        if (IS_PIN_VALID(rPwmPin)) ledcWrite(rChannel, 0);
    } else {
        if (IS_PIN_VALID(lPwmPin)) ledcWrite(lChannel, 0);
        if (IS_PIN_VALID(rPwmPin)) ledcWrite(rChannel, calculateRawDuty(duty));
    }
}

void Bts7960Pump::enable(bool printFeedback) {
    enabled = true;
    applyOutputs();
    if (printFeedback) Serial.printf("%s -> ENABLED\n", name);
}

void Bts7960Pump::disable(bool printFeedback) {
    enabled = false;
    applyOutputs();
    if (printFeedback) Serial.printf("%s -> DISABLED\n", name);
}

void Bts7960Pump::emergencyStop() {
    duty = 0;
    enabled = false;
    applyOutputs();
    Serial.printf("%s -> STOP\n", name);
}

bool Bts7960Pump::setDuty(uint8_t percent, bool printFeedback) {
    if (percent > 100) percent = 100;
    duty = percent;
    if (percent > 0 && !enabled) enabled = true;
    applyOutputs();

    if (printFeedback) {
        if (duty == 0) Serial.printf("%s -> STOP\n", name);
        else Serial.printf("%s -> %d%%\n", name, duty);
    }
    return true;
}

void Bts7960Pump::setDirection(PumpDirection dir) {
    direction = dir;
    applyOutputs();
    Serial.printf("%s Direction -> %s\n", name, (dir == PUMP_DIR_FORWARD) ? "FORWARD" : "REVERSE");
}

void Bts7960Pump::printStatus() const {
    Serial.println(statusTag);
    Serial.printf("  State:     %s\n", enabled ? "ENABLED" : "DISABLED");
    Serial.printf("  Direction: %s\n", (direction == PUMP_DIR_FORWARD) ? "FORWARD" : "REVERSE");
    Serial.printf("  Duty:      %d%% (PWM: %lu/255)\n", duty, (unsigned long)calculateRawDuty(duty));
    Serial.printf("  Hardware:  %s\n", isCase1HardwareOutputEnabled() ? "ENABLED" : "DISABLED");
}

// -----------------------------------------------------------------------------
// Pump Instances Configuration
// -----------------------------------------------------------------------------

Bts7960Pump g_pump1 = {
    "Pump 1",
    "[PUMP 1] Initialized (Driver U2, stopped).",
    "--- Pump 1 (U2) ---",
    PUMP1_L_PWM_PIN, PUMP1_R_PWM_PIN,
    PUMP1_L_EN_PIN, PUMP1_R_EN_PIN,
    PUMP1_L_PWM_CHANNEL, PUMP1_R_PWM_CHANNEL,
    PUMP1_PWM_FREQ_HZ, PUMP1_PWM_RESOLUTION_BITS,
    PUMP1_DEFAULT_DIRECTION, false, 0
};

Bts7960Pump g_pump2 = {
    "Pump 2",
    "[PUMP 2] Initialized (Driver U3, stopped).",
    "--- Pump 2 (U3) ---",
    PUMP2_L_PWM_PIN, PUMP2_R_PWM_PIN,
    PUMP2_L_EN_PIN, PUMP2_R_EN_PIN,
    PUMP2_L_PWM_CHANNEL, PUMP2_R_PWM_CHANNEL,
    PUMP2_PWM_FREQ_HZ, PUMP2_PWM_RESOLUTION_BITS,
    PUMP2_DEFAULT_DIRECTION, false, 0
};

Bts7960Pump g_pump3 = {
    "Pump 3",
    "[PUMP 3] Initialized (Driver U4, stopped).",
    "--- Pump 3 (U4) ---",
    PUMP3_L_PWM_PIN, PUMP3_R_PWM_PIN,
    PUMP3_L_EN_PIN, PUMP3_R_EN_PIN,
    PUMP3_L_PWM_CHANNEL, PUMP3_R_PWM_CHANNEL,
    PUMP3_PWM_FREQ_HZ, PUMP3_PWM_RESOLUTION_BITS,
    PUMP3_DEFAULT_DIRECTION, false, 0
};

// -----------------------------------------------------------------------------
// Pump 1 Public C Interface
// -----------------------------------------------------------------------------

void initPump1() { g_pump1.init(); }
void enablePump1(bool printFeedback) { g_pump1.enable(printFeedback); }
void disablePump1(bool printFeedback) { g_pump1.disable(printFeedback); }
void emergencyStopPump1() { g_pump1.emergencyStop(); }
bool setPump1Duty(uint8_t percent, bool printFeedback) { return g_pump1.setDuty(percent, printFeedback); }
void setPump1Direction(PumpDirection dir) { g_pump1.setDirection(dir); }
PumpDirection getPump1Direction() { return g_pump1.direction; }
const char* getPump1DirectionStr() {
    return (g_pump1.direction == PUMP_DIR_FORWARD) ? "FORWARD (L_PWM Active)" : "REVERSE (R_PWM Active)";
}
bool isPump1Enabled() { return g_pump1.enabled; }
uint8_t getPump1Duty() { return g_pump1.duty; }
void printPump1Status() { g_pump1.printStatus(); }
