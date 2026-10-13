#ifndef START_BUTTON_H
#define START_BUTTON_H

#include <Arduino.h>
#include "hardware_config.h"

// Initialize GPIO 34 as INPUT (active-LOW button on PCB ON/OFF connector with external 10k pull-up and 100nF filter)
void initStartButton();

// Software debouncing and edge detection (call in loop)
void updateStartButton();

// Returns true once when button is pressed (falling edge trigger)
bool wasStartButtonPressed();

// Returns true while button is physically held down
bool isStartButtonPhysicallyPressed();

// Direct raw hardware read
int getStartButtonRawState();

// Print status to Serial
void printStartButtonStatus();

#endif // START_BUTTON_H
