#include "pump3_controller.h"
#include "bts7960_pump.h"

// -----------------------------------------------------------------------------
// Pump 3 Public C Interface (Delegates to g_pump3)
// -----------------------------------------------------------------------------

void initPump3() { g_pump3.init(); }
void enablePump3(bool printFeedback) { g_pump3.enable(printFeedback); }
void disablePump3(bool printFeedback) { g_pump3.disable(printFeedback); }
void emergencyStopPump3() { g_pump3.emergencyStop(); }
bool setPump3Duty(uint8_t percent, bool printFeedback) { return g_pump3.setDuty(percent, printFeedback); }
void setPump3Direction(PumpDirection dir) { g_pump3.setDirection(dir); }
PumpDirection getPump3Direction() { return g_pump3.direction; }
const char* getPump3DirectionStr() {
    return (g_pump3.direction == PUMP_DIR_FORWARD) ? "FORWARD (L_PWM Active)" : "REVERSE (R_PWM Active)";
}
bool isPump3Enabled() { return g_pump3.enabled; }
uint8_t getPump3Duty() { return g_pump3.duty; }
void printPump3Status() { g_pump3.printStatus(); }
