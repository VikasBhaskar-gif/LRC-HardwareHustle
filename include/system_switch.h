#ifndef SYSTEM_SWITCH_H
#define SYSTEM_SWITCH_H

#include <Arduino.h>
#include "hardware_config.h"

// Initialize System State (Software control via Serial Monitor)
void initSystemSwitch();

// Polling hook (no-op for software control, preserved for loop compatibility)
void updateSystemSwitch();

// Returns true if system is enabled
bool isSystemOn();

// Set system enable state (via Serial Monitor)
void setSystemOn(bool enabled);

// Toggle system enable state (via Serial Monitor)
void toggleSystemOn();

// Virtual raw state (returns HIGH if enabled, LOW if disabled)
int getSystemSwitchRawState();

// Print status to Serial
void printSystemSwitchStatus();

#endif // SYSTEM_SWITCH_H
