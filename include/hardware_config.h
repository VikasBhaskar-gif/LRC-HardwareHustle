#ifndef HARDWARE_CONFIG_H
#define HARDWARE_CONFIG_H

#include <Arduino.h>

// Hardware pin definitions and settings for the LRC liquid handling system.
//
// Fluid connections:
//   Pump 1 (U2): 10L Main Tank -> Sump
//   Pump 2 (U3): Sump -> Flow Sensor -> Main Tank
//   Pump 3 (U4): Flush Tank -> Equal Tee
//   Float Switch: Sump level (GPIO 35)
//   Flow Sensor: YF-S401 (GPIO 14)
//   Solenoid Valve: Process tank isolation (GPIO 27)
//   System Enable: Software control via Serial Monitor
//   Flush Button: Case 2 flush trigger (GPIO 34, PCB ON/OFF connector)

// Motor Direction Enumeration for IBT-2 / BTS7960 Full H-Bridge Drivers (Single Motor per Pump)
typedef enum {
    PUMP_DIR_FORWARD = 0,
    PUMP_DIR_REVERSE = 1
} PumpDirection;

// Macro helper to validate pin numbers
#define IS_PIN_VALID(pin)           ((pin) >= 0)

// Pump 1: Main Tank -> Sump (Driver U2)
#define PUMP1_L_PWM_PIN             32
#define PUMP1_R_PWM_PIN             33
#define PUMP1_L_EN_PIN              13
#define PUMP1_R_EN_PIN              26

#define PUMP1_EN_ACTIVE_HIGH        true
#define PUMP1_PWM_ACTIVE_HIGH       true

#define PUMP1_PWM_FREQ_HZ           5000   // 5 kHz PWM frequency
#define PUMP1_PWM_RESOLUTION_BITS   8      // 8-bit resolution (0-255)
#define PUMP1_L_PWM_CHANNEL         0
#define PUMP1_R_PWM_CHANNEL         1

#define PUMP1_DEFAULT_DIRECTION     PUMP_DIR_FORWARD

// Pump 2: Sump -> Flow Sensor -> Main Tank (Driver U3)
#define PUMP2_L_PWM_PIN             18
#define PUMP2_R_PWM_PIN             19
#define PUMP2_L_EN_PIN              16
#define PUMP2_R_EN_PIN              17

#define PUMP2_EN_ACTIVE_HIGH        true
#define PUMP2_PWM_ACTIVE_HIGH       true

#define PUMP2_PWM_FREQ_HZ           5000   // 5 kHz PWM frequency
#define PUMP2_PWM_RESOLUTION_BITS   8      // 8-bit resolution (0-255)
#define PUMP2_L_PWM_CHANNEL         2
#define PUMP2_R_PWM_CHANNEL         3

#define PUMP2_DEFAULT_DIRECTION     PUMP_DIR_FORWARD

// Normal duty setting for Pump 2 in Case 1
#define CASE1_PUMP2_DEFAULT_NORMAL_DUTY 100

// Float switch: Sump level detection (GPIO 35)
// Normal/Open = HIGH (3.3V), Triggered/Closed = LOW (0V)
#define FLOAT_SWITCH_PIN            35
#define FLOAT_SWITCH_TRIGGERED_LEVEL LOW
#define FLOAT_SWITCH_DEBOUNCE_MS    30

// Flow sensor: YF-S401 (GPIO 14)
// Formula: Flow (L/min) = Frequency (Hz) / 98.0
#define FLOW_SENSOR_PIN                 14
#define FLOW_SENSOR_HZ_PER_LPM          98.0f
#define FLOW_SENSOR_UPDATE_INTERVAL_MS  1000
#define FLOW_SENSOR_MIN_RATED_LPM       0.3f
#define FLOW_SENSOR_MAX_RATED_LPM       6.0f

// System ON/OFF control (Software-controlled via Serial Monitor; no physical switch on PCB)
#define SYSTEM_SWITCH_PIN           -1
#define SYSTEM_SWITCH_ON_LEVEL      HIGH
#define SYSTEM_SWITCH_DEBOUNCE_MS   30

// Solenoid valve (GPIO 27)
// Active HIGH: HIGH opens valve, LOW closes valve
#define SOLENOID_VALVE_PIN          27
#define SOLENOID_ACTIVE_HIGH        true

// Pump 3: Flush Pump (Driver U4, Case 2)
#define PUMP3_L_PWM_PIN             23
#define PUMP3_R_PWM_PIN             25
#define PUMP3_L_EN_PIN              21
#define PUMP3_R_EN_PIN              22

#define PUMP3_EN_ACTIVE_HIGH        true
#define PUMP3_PWM_ACTIVE_HIGH       true

#define PUMP3_PWM_FREQ_HZ           5000
#define PUMP3_PWM_RESOLUTION_BITS   8
#define PUMP3_L_PWM_CHANNEL         4
#define PUMP3_R_PWM_CHANNEL         5

#define PUMP3_DEFAULT_DIRECTION     PUMP_DIR_FORWARD

// Physical start button for complete automatic sequence (GPIO 34 on PCB ON/OFF SWITCH connector, active LOW)
// A single debounced button press starts Case 1; Case 2 automatically follows after sump-high recovery.
// Circuit verified against schematic: External 10 kΩ pull-up resistor (R10) to 3.3V and 100 nF capacitor (C9) to GND.
// ESP32 GPIO 34 is input-only without internal pull-ups; MUST use pinMode(34, INPUT), never INPUT_PULLUP.
#define START_BUTTON_PIN            34
#define START_BUTTON_ACTIVE_LEVEL   LOW
#define START_BUTTON_DEBOUNCE_MS    30

// Backwards-compatibility aliases for GPIO 34
#define FLUSH_BUTTON_PIN            START_BUTTON_PIN
#define FLUSH_BUTTON_ACTIVE_LEVEL   START_BUTTON_ACTIVE_LEVEL
#define FLUSH_BUTTON_DEBOUNCE_MS    START_BUTTON_DEBOUNCE_MS

// Automatic sequence timing parameters
#define CASE1_RETURN_DELAY_MS       10000UL // 10-second delay after float switch returns to normal before Case 2 starts
#define CASE2_FLUSH_DURATION_MS     90000UL // 90-second flush duration (90,000 ms)
#define FLUSH_DURATION_MS           CASE2_FLUSH_DURATION_MS // Shared constant alias
#define CASE2_PUMP1_FLUSH_DUTY      50     // Pump 1 runs at 50%
#define CASE2_PUMP2_FLUSH_DUTY      100    // Pump 2 runs at 100%
#define CASE2_PUMP3_FLUSH_DUTY      50     // Pump 3 runs at 50%

#endif // HARDWARE_CONFIG_H
