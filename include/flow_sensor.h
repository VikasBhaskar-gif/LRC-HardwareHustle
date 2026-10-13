#ifndef FLOW_SENSOR_H
#define FLOW_SENSOR_H

#include <Arduino.h>
#include "hardware_config.h"

// Flow sensor range status (rated 0.3 - 6.0 L/min)
typedef enum {
    FLOW_RANGE_ZERO = 0,    // Flow = 0 L/min
    FLOW_RANGE_LOW,         // Flow < 0.3 L/min
    FLOW_RANGE_NORMAL,      // In rated range (0.3 - 6.0 L/min)
    FLOW_RANGE_HIGH         // Above rated range (> 6.0 L/min)
} FlowRangeStatus;

// Initialize GPIO 14 interrupt for pulse counting
void initFlowSensor();

// Calculate flow frequency and rate (call in loop)
void updateFlowSensor();

// Flow rate and frequency readings
float getFlowRateLPM();
float getFlowFrequencyHz();

// Pulse count queries
uint32_t getTotalPulseCount();
void resetFlowPulseCount();

// Range status
FlowRangeStatus getFlowRangeStatus();
const char* getFlowRangeStatusStr();

// Print status to Serial
void printFlowSensorStatus();

#endif // FLOW_SENSOR_H
