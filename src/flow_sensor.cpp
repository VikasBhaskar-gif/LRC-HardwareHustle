#include "flow_sensor.h"

// Volatile counters updated within interrupt service routine
static volatile uint32_t s_isrWindowPulses = 0;
static volatile uint32_t s_isrTotalPulses = 0;

// Calculated live metrics
static float s_liveFrequencyHz = 0.0f;
static float s_liveFlowLPM = 0.0f;
static unsigned long s_lastWindowTime = 0;

// Lightweight Interrupt Service Routine for GPIO 14
void IRAM_ATTR flowSensorISR() {
    s_isrWindowPulses++;
    s_isrTotalPulses++;
}

void initFlowSensor() {
    pinMode(FLOW_SENSOR_PIN, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(FLOW_SENSOR_PIN), flowSensorISR, RISING);

    s_liveFrequencyHz = 0.0f;
    s_liveFlowLPM = 0.0f;
    s_lastWindowTime = millis();

    Serial.println("[FLOW_SENSOR] Initialized (GPIO 14, YF-S401).");
}

void updateFlowSensor() {
    unsigned long now = millis();
    unsigned long elapsedMs = now - s_lastWindowTime;

    if (elapsedMs >= FLOW_SENSOR_UPDATE_INTERVAL_MS) {
        // Atomic read and reset of the window pulse count
        noInterrupts();
        uint32_t pulses = s_isrWindowPulses;
        s_isrWindowPulses = 0;
        interrupts();

        s_lastWindowTime = now;

        if (pulses == 0) {
            // Strictly handle zero flow to prevent tiny residual values
            s_liveFrequencyHz = 0.0f;
            s_liveFlowLPM = 0.0f;
        } else {
            // Frequency (Hz) = (pulses / elapsedSeconds)
            s_liveFrequencyHz = ((float)pulses * 1000.0f) / (float)elapsedMs;
            // Flow (L/min) = Frequency (Hz) / calibration constant
            s_liveFlowLPM = s_liveFrequencyHz / FLOW_SENSOR_HZ_PER_LPM;
        }
    }
}

float getFlowRateLPM() {
    return s_liveFlowLPM;
}

float getFlowFrequencyHz() {
    return s_liveFrequencyHz;
}

uint32_t getTotalPulseCount() {
    noInterrupts();
    uint32_t total = s_isrTotalPulses;
    interrupts();
    return total;
}

void resetFlowPulseCount() {
    noInterrupts();
    s_isrTotalPulses = 0;
    s_isrWindowPulses = 0;
    interrupts();
    s_liveFrequencyHz = 0.0f;
    s_liveFlowLPM = 0.0f;
    Serial.println("[FLOW_SENSOR] Cumulative pulse counter reset to 0.");
}

FlowRangeStatus getFlowRangeStatus() {
    if (s_liveFlowLPM <= 0.001f) {
        return FLOW_RANGE_ZERO;
    } else if (s_liveFlowLPM < FLOW_SENSOR_MIN_RATED_LPM) {
        return FLOW_RANGE_LOW;
    } else if (s_liveFlowLPM > FLOW_SENSOR_MAX_RATED_LPM) {
        return FLOW_RANGE_HIGH;
    }
    return FLOW_RANGE_NORMAL;
}

const char* getFlowRangeStatusStr() {
    switch (getFlowRangeStatus()) {
        case FLOW_RANGE_ZERO:   return "ZERO (No Flow)";
        case FLOW_RANGE_LOW:    return "BELOW RATED RANGE (<0.3 L/min)";
        case FLOW_RANGE_NORMAL: return "IN RANGE (0.3 - 6.0 L/min)";
        case FLOW_RANGE_HIGH:   return "ABOVE RATED RANGE (>6.0 L/min)";
        default:                return "UNKNOWN";
    }
}

void printFlowSensorStatus() {
    uint32_t totalPulses = getTotalPulseCount();

    Serial.println("--- Flow Sensor (GPIO 14) ---");
    Serial.printf("  Pulses:    %lu\n", (unsigned long)totalPulses);
    Serial.printf("  Frequency: %.2f Hz\n", s_liveFrequencyHz);
    Serial.printf("  Flow Rate: %.3f L/min\n", s_liveFlowLPM);
    Serial.printf("  Status:    %s\n", getFlowRangeStatusStr());
}
