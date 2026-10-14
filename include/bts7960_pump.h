#ifndef BTS7960_PUMP_H
#define BTS7960_PUMP_H

#include <Arduino.h>
#include "hardware_config.h"

// BTS7960 / IBT-2 High-Power H-Bridge DC Motor Driver
// Controls direction, PWM speed (0-100%), and enable pins for a liquid handling pump.
struct Bts7960Pump {
    const char* name;       // e.g. "Pump 1"
    const char* initTag;    // e.g. "[PUMP 1] Initialized (Driver U2, stopped)."
    const char* statusTag;  // e.g. "--- Pump 1 (U2) ---"
    int lPwmPin;
    int rPwmPin;
    int lEnPin;
    int rEnPin;
    int lChannel;
    int rChannel;
    uint32_t pwmFreq;
    uint8_t resBits;
    PumpDirection direction;
    bool enabled;
    uint8_t duty;

    void init();
    void enable(bool printFeedback = true);
    void disable(bool printFeedback = true);
    void emergencyStop();
    bool setDuty(uint8_t percent, bool printFeedback = true);
    void setDirection(PumpDirection dir);
    void applyOutputs();
    void printStatus() const;
    uint32_t calculateRawDuty(uint8_t percent) const;
};

// Global pump instances
extern Bts7960Pump g_pump1;
extern Bts7960Pump g_pump2;
extern Bts7960Pump g_pump3;

#endif // BTS7960_PUMP_H
