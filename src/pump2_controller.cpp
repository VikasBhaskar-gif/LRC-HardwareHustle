#include "pump2_controller.h"
#include "bts7960_pump.h"

// -----------------------------------------------------------------------------
// Pump 2 Public C Interface (Delegates to g_pump2)
// -----------------------------------------------------------------------------

void initPump2() { g_pump2.init(); }
void enablePump2(bool printFeedback) { g_pump2.enable(printFeedback); }
void disablePump2(bool printFeedback) { g_pump2.disable(printFeedback); }
void emergencyStopPump2() { g_pump2.emergencyStop(); }
bool setPump2Duty(uint8_t percent, bool printFeedback) { return g_pump2.setDuty(percent, printFeedback); }
void setPump2Direction(PumpDirection dir) { g_pump2.setDirection(dir); }
PumpDirection getPump2Direction() { return g_pump2.direction; }
const char* getPump2DirectionStr() {
    return (g_pump2.direction == PUMP_DIR_FORWARD) ? "FORWARD (L_PWM Active)" : "REVERSE (R_PWM Active)";
}
bool isPump2Enabled() { return g_pump2.enabled; }
uint8_t getPump2Duty() { return g_pump2.duty; }
void printPump2Status() { g_pump2.printStatus(); }
