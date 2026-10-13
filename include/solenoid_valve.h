#ifndef SOLENOID_VALVE_H
#define SOLENOID_VALVE_H

#include <Arduino.h>
#include "hardware_config.h"

// Initialize GPIO 27 as OUTPUT (starts CLOSED/LOW)
void initSolenoidValve();

// Open the valve (GPIO 27 HIGH)
void openSolenoid();

// Close the valve (GPIO 27 LOW)
void closeSolenoid();

// Toggle between OPEN and CLOSED
void toggleSolenoid();

// Query current state (true = OPEN, false = CLOSED)
bool isSolenoidOpen();

// Hardware output enable for simulation
void setSolenoidHardwareOutputEnabled(bool enabled);
bool isSolenoidHardwareOutputEnabled();

// Print status to Serial
void printSolenoidStatus();

// Aliases matching requirement specification: init(), open(), close(), isOpen()
inline void initSolenoid() { initSolenoidValve(); }
inline void solenoidOpen() { openSolenoid(); }
inline void solenoidClose() { closeSolenoid(); }
inline void solenoidToggle() { toggleSolenoid(); }
inline bool solenoidIsOpen() { return isSolenoidOpen(); }

#endif // SOLENOID_VALVE_H
