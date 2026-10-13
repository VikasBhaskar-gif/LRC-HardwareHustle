#ifndef PUMP_CONTROLLER_H
#define PUMP_CONTROLLER_H

#include <Arduino.h>
#include "hardware_config.h"

// Initialize Pump 1 (Driver U2 on PCB)
void initPump1();

// Enable / disable Pump 1 driver
void enablePump1(bool printFeedback = true);
void disablePump1(bool printFeedback = true);

// Emergency stop: disables driver and zeroes duty
void emergencyStopPump1();

// Set PWM duty cycle (0-100%)
bool setPump1Duty(uint8_t percent, bool printFeedback = true);

// Direction control (forward / reverse)
void setPump1Direction(PumpDirection dir);
PumpDirection getPump1Direction();
const char* getPump1DirectionStr();

// Query functions
bool isPump1Enabled();
uint8_t getPump1Duty();

// Print status to Serial
void printPump1Status();

#endif // PUMP_CONTROLLER_H
