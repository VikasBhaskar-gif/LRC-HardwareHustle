#ifndef FLOAT_SWITCH_H
#define FLOAT_SWITCH_H

#include <Arduino.h>
#include "hardware_config.h"

// Initialize GPIO 35 as INPUT (uses external 10k pull-up on PCB)
void initFloatSwitch();

// Software debouncing (call in loop)
void updateFloatSwitch();

// Read raw hardware pin state
int readFloatSwitchRaw();

// Query debounced state
bool isFloatSwitchTriggered();
bool isFloatSwitchNormal();

// Print status to Serial
void printFloatSwitchStatus();

#endif // FLOAT_SWITCH_H
