#ifndef PUMP2_CONTROLLER_H
#define PUMP2_CONTROLLER_H

#include <Arduino.h>
#include "hardware_config.h"

// Initialize Pump 2 (Driver U3 on PCB)
void initPump2();

// Enable / disable Pump 2 driver
void enablePump2(bool printFeedback = true);
void disablePump2(bool printFeedback = true);

// Emergency stop: disables driver and zeroes duty
void emergencyStopPump2();

// Set PWM duty cycle (0-100%)
bool setPump2Duty(uint8_t percent, bool printFeedback = true);

// Direction control (forward / reverse)
void setPump2Direction(PumpDirection dir);
PumpDirection getPump2Direction();
const char* getPump2DirectionStr();

// Query functions
bool isPump2Enabled();
uint8_t getPump2Duty();

// Print status to Serial
void printPump2Status();

#endif // PUMP2_CONTROLLER_H
