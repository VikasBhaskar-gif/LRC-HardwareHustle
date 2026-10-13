#ifndef FLUSH_BUTTON_H
#define FLUSH_BUTTON_H

#include "start_button.h"

// Backwards-compatibility wrapper for components referencing flush_button
inline void initFlushButton() { initStartButton(); }
inline void updateFlushButton() { updateStartButton(); }
inline bool wasFlushButtonPressed() { return wasStartButtonPressed(); }
inline bool isFlushButtonPhysicallyPressed() { return isStartButtonPhysicallyPressed(); }
inline int getFlushButtonRawState() { return getStartButtonRawState(); }
inline void printFlushButtonStatus() { printStartButtonStatus(); }

#endif // FLUSH_BUTTON_H
