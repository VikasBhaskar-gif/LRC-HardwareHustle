#ifndef CASE1_CONTROLLER_H
#define CASE1_CONTROLLER_H

#include <Arduino.h>

// Case 1 and Case 2 controller
//
// Case 1 (Normal recirculation):
//   Pump 1: 50%, Pump 2: 100%, Pump 3: OFF, Solenoid: OPEN.
//   Float switch on GPIO 35 stops Pump 1 if sump level is high.
//
// Case 2 (90-second flush sequence):
//   Triggered by physical momentary push button on GPIO 34 (PCB ON/OFF connector).
//   Solenoid CLOSES to isolate process tank.
//   Pump 1 (50%), Pump 2 (100%), Pump 3 (50%) run for 90 seconds.
//   All pumps stop after 90 seconds into latched shutdown.

// Default duty cycle targets for Case 1 per Stage 2 specification
#define CASE1_PUMP1_DEFAULT_NORMAL_DUTY     50   // 50% duty cycle
#define CASE1_PUMP2_DEFAULT_NORMAL_DUTY     100  // 100% duty cycle

// State Machine Enumeration for Case 1 & Case 2
typedef enum {
    CASE1_STATE_SAFE_IDLE = 0,
    CASE1_STATE_INIT = 0,          // Alias for safe-idle standby
    CASE1_STATE_EMERGENCY_STOP,
    CASE1_STATE_SYSTEM_OFF,
    CASE1_STATE_NORMAL,
    CASE1_STATE_SUMP_HIGH,
    CASE1_STATE_RETURN_TO_NORMAL,
    CASE2_STATE_FLUSHING,
    CASE2_STATE_SHUTDOWN
} Case1State;

// Input Source Tracking
typedef enum {
    CASE1_SRC_REAL_SENSOR = 0,
    CASE1_SRC_SIMULATION  = 1
} Case1InputSource;

// Initialize Case controller (enters SAFE_IDLE with all pump targets 0% and solenoid CLOSED)
void initCase1Controller();

// Physical Start Button Trigger (Starts the complete automatic Case 1 -> Case 2 sequence)
// Ignored if sequence is already running, flushing, or in latched final shutdown.
bool case1StartSequence();

// Explicit Operator Start for Case 1 Normal Flow (Command: N / Commissioning)
// Returns true if started, false if blocked by E-Stop, System Switch OFF, or Case 2 state
bool case1StartNormalFlow();

// Periodic system update routine taking both ON/OFF switch and float switch states
void updateCase1WithInputs(bool isSystemSwitchOn, bool isFloatSwitchTriggered);

// Return-to-normal 1-second transition delay queries
bool isCase1TransitionDelayActive();
unsigned long getCase1TransitionRemainingMs();

// Case 2 Flush Sequence Controls
bool triggerCase2FlushSequence();
bool isCase2FlushingActive();
bool isCase2ShutdownActive();
unsigned long getCase2FlushRemainingMs();
uint32_t getCase2FlushDurationMs();
void setCase2FlushDurationMs(uint32_t ms);

// Emergency Stop controls
void case1TriggerEmergencyStop();
void case1ClearEmergencyStop();
bool isCase1EmergencyStopActive();

// Manual Simulated Event Triggers (Commands: n, x, r)
void case1TriggerSimulatedNormal();
void case1TriggerSimulatedSumpHigh();
void case1TriggerSimulatedReturnToNormal();

// Configuration & State Queries
Case1State getCase1State();
const char* getCase1StateStr();
Case1InputSource getCase1InputSource();
const char* getCase1InputSourceStr();

uint8_t getCase1Pump1TargetDuty();
uint8_t getCase1Pump2TargetDuty();
uint8_t getCase1Pump3TargetDuty();
void setCase1Pump1NormalDuty(uint8_t duty);
void setCase1Pump2NormalDuty(uint8_t duty);

// Safety Hardware Coupling Control
void setCase1HardwareOutputEnabled(bool enabled);
bool isCase1HardwareOutputEnabled();

// Print detailed status report
void printCase1Status();

#endif // CASE1_CONTROLLER_H
