#ifndef DUTY_PARSER_H
#define DUTY_PARSER_H

#include <Arduino.h>
#include <ctype.h>
#include <stdlib.h>

// Status results for duty-cycle command parsing (5% increments)
enum DutyParseResult {
  DUTY_PARSE_OK = 0,
  DUTY_PARSE_NOT_A_DUTY_CMD,
  DUTY_PARSE_INVALID_FORMAT,
  DUTY_PARSE_OUT_OF_RANGE,
  DUTY_PARSE_NOT_MULTIPLE_OF_5
};

// Parsed duty command data
struct DutyCommand {
  int targetPump;      // 1 = Pump 1, 2 = Pump 2, 0 = default
  uint8_t dutyPercent; // 0, 5, 10, ..., 100
  int rawValue;        // Raw integer entered by user
  DutyParseResult status;
};

// Parses serial input for duty commands (e.g. d50, d1 50, d2 50) in 5% steps (0-100%)
inline DutyParseResult parseDuty5PercentCommand(const char *input,
                                                int defaultPump,
                                                DutyCommand &outCmd) {
  outCmd.targetPump = defaultPump;
  outCmd.dutyPercent = 0;
  outCmd.rawValue = 0;
  outCmd.status = DUTY_PARSE_NOT_A_DUTY_CMD;

  if (!input) {
    return DUTY_PARSE_NOT_A_DUTY_CMD;
  }

  // Skip leading whitespace
  const char *p = input;
  while (*p && isspace((unsigned char)*p)) {
    p++;
  }
  if (!*p) {
    return DUTY_PARSE_NOT_A_DUTY_CMD;
  }

  int pump = defaultPump;

  // Check for explicit pump prefix:
  // "1d" or "1D" (e.g. 1d50)
  if ((p[0] == '1') && (p[1] == 'd' || p[1] == 'D')) {
    pump = 1;
    p += 2;
  }
  // "2d" or "2D" (e.g. 2d50)
  else if ((p[0] == '2') && (p[1] == 'd' || p[1] == 'D')) {
    pump = 2;
    p += 2;
  }
  // "p1" / "P1" or "p2" / "P2" (e.g. p1 50, p1=50)
  else if ((p[0] == 'p' || p[0] == 'P') && (p[1] == '1' || p[1] == '2')) {
    pump = p[1] - '0';
    p += 2;
  }
  // "d1" or "d2" followed by a separator and digits (e.g., "d1 50", "d1=50",
  // "d1:50") NOTE: "d1" or "d2" without a separator (or "d10", "d15", "d100",
  // "d20", "d25") are duty percentage values (e.g. 1%, 2%, 10%, 15%, 100%, 20%,
  // 25%), NOT pump selectors!
  else if ((p[0] == 'd' || p[0] == 'D') && (p[1] == '1' || p[1] == '2') &&
           (p[2] == ' ' || p[2] == '\t' || p[2] == '=' || p[2] == ':')) {
    const char *nextNum = p + 2;
    while (*nextNum && (isspace((unsigned char)*nextNum) || *nextNum == '=' ||
                        *nextNum == ':')) {
      nextNum++;
    }
    if (isdigit((unsigned char)*nextNum) || *nextNum == '-' ||
        *nextNum == '+') {
      pump = p[1] - '0';
      p = nextNum;
    } else {
      outCmd.status = DUTY_PARSE_INVALID_FORMAT;
      return DUTY_PARSE_INVALID_FORMAT;
    }
  }
  // Standard "d" / "D" prefix
  else if (p[0] == 'd' || p[0] == 'D') {
    pump = defaultPump;
    p++;
    // If string was just 'd' or 'D' alone, this is NOT a duty command (legacy
    // single char 'd')
    while (*p && isspace((unsigned char)*p)) {
      p++;
    }
    if (!*p) {
      return DUTY_PARSE_NOT_A_DUTY_CMD;
    }
  }
  // Pure numeric in submenus (when defaultPump > 0)
  else if (defaultPump > 0 &&
           (isdigit((unsigned char)*p) || *p == '-' || *p == '+')) {
    pump = defaultPump;
  } else {
    return DUTY_PARSE_NOT_A_DUTY_CMD;
  }

  // Skip separator whitespace or '=' or ':'
  while (*p && (isspace((unsigned char)*p) || *p == '=' || *p == ':')) {
    p++;
  }

  if (!*p) {
    outCmd.status = DUTY_PARSE_INVALID_FORMAT;
    return DUTY_PARSE_INVALID_FORMAT;
  }

  // Must start with sign or digit
  if (!isdigit((unsigned char)*p) && *p != '-' && *p != '+') {
    outCmd.status = DUTY_PARSE_INVALID_FORMAT;
    return DUTY_PARSE_INVALID_FORMAT;
  }

  char *endPtr = nullptr;
  long val = strtol(p, &endPtr, 10);
  outCmd.rawValue = (int)val;

  if (endPtr == p) {
    outCmd.status = DUTY_PARSE_INVALID_FORMAT;
    return DUTY_PARSE_INVALID_FORMAT;
  }

  // Skip trailing whitespace and optional '%'
  const char *trail = endPtr;
  while (*trail && isspace((unsigned char)*trail)) {
    trail++;
  }
  if (*trail == '%') {
    trail++;
    while (*trail && isspace((unsigned char)*trail)) {
      trail++;
    }
  }

  // If any trailing characters remain, format is invalid (e.g. "d50x")
  if (*trail != '\0') {
    outCmd.status = DUTY_PARSE_INVALID_FORMAT;
    return DUTY_PARSE_INVALID_FORMAT;
  }

  // Range check: [0, 100]
  if (val < 0 || val > 100) {
    outCmd.status = DUTY_PARSE_OUT_OF_RANGE;
    return DUTY_PARSE_OUT_OF_RANGE;
  }

  // Multiple of 5 check
  if ((val % 5) != 0) {
    outCmd.status = DUTY_PARSE_NOT_MULTIPLE_OF_5;
    return DUTY_PARSE_NOT_MULTIPLE_OF_5;
  }

  outCmd.dutyPercent = (uint8_t)val;
  outCmd.targetPump = pump;
  outCmd.status = DUTY_PARSE_OK;
  return DUTY_PARSE_OK;
}

// Print user error message when duty parsing fails
inline void printDutyParseError(const char *rawInput, const DutyCommand &cmd) {
  if (cmd.status == DUTY_PARSE_NOT_MULTIPLE_OF_5) {
    Serial.printf("[ERROR] Duty '%d%%' must be a multiple of 5 (0 to 100%%).\n", cmd.rawValue);
  } else if (cmd.status == DUTY_PARSE_OUT_OF_RANGE) {
    Serial.printf("[ERROR] Duty '%d%%' out of range (0 to 100%%).\n", cmd.rawValue);
  } else if (cmd.status == DUTY_PARSE_INVALID_FORMAT) {
    Serial.printf("[ERROR] Invalid command '%s'. Use d<value> in steps of 5.\n", rawInput ? rawInput : "");
  }
}

#endif // DUTY_PARSER_H
