#ifndef COMMISSIONING_H
#define COMMISSIONING_H

#include <Arduino.h>

// Commissioning mode status query
bool isCommissioningModeActive();

// Entry and Exit routines
void enterCommissioningMode();
void exitCommissioningMode();

// Menu display and command processing
void printCommissioningMenu();
bool handleCommissioningCommand(char cmd);
bool handleCommissioningCommandLine(const char* line);

// Individual Commissioning Tests
void runPump1CommissioningTest(uint8_t duty);
void runPump2CommissioningTest(uint8_t duty);
void runSolenoidCommissioningTest(bool openValve);
void runFloatSwitchCommissioningTest();
void runFlowSensorCommissioningTest();
void runFlushButtonCommissioningTest();
void runSystemSwitchCommissioningTest();

// Full Case 1 Sequence
void runFullCase1SimulationSequence();

// Full Commissioning Diagnostic Screen
void printCommissioningDiagnosticScreen();

#endif // COMMISSIONING_H
