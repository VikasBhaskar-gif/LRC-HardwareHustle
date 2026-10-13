#ifndef PUMP3_CONTROLLER_H
#define PUMP3_CONTROLLER_H

#include <Arduino.h>
#include "hardware_config.h"

// Initialize Pump 3 (Driver U4 on PCB)
void initPump3();

// Enable / disable Pump 3 driver
void enablePump3(bool printFeedback = true);
void disablePump3(bool printFeedback = true);

// Emergency stop: disables driver and zeroes duty
void emergencyStopPump3();

// Set PWM duty cycle (0-100%)
bool setPump3Duty(uint8_t percent, bool printFeedback = true);

// Direction control (forward / reverse)
void setPump3Direction(PumpDirection dir);
PumpDirection getPump3Direction();
const char* getPump3DirectionStr();

// Query functions
bool isPump3Enabled();
uint8_t getPump3Duty();

// Print status to Serial
void printPump3Status();

#endif // PUMP3_CONTROLLER_H
