#!/usr/bin/env python3
"""
================================================================================
YFS401 Flow Sensor Calibration - PC-Side CSV Data Logger
================================================================================
Target: ESP32 Hardware Controller (LRC Stage 2)
Default Baud: 115200 baud
Output File:  flow_calibration.xlsx

Functionality:
1. Connects to the ESP32 USB serial/COM port at 115200 baud.
2. Reads 2.5-second CSV flow logging stream:
     timestamp_ms,pump2_pwm,frequency_hz,estimated_flow_lpm
3. Appends each reading to 'flow_calibration.xlsx' under columns:
     - Timestamp (ms)
     - Pump 2 PWM (%)
     - Frequency (Hz)
     - Estimated Flow (L/min)
     - Actual Flow (L/min)  [Left blank for physical measurement]
4. Saves workbook after every reading to prevent data loss.
5. If 'flow_calibration.xlsx' exists, appends data without overwriting.
6. Filters out non-CSV diagnostic and [LOG] text messages.
7. Clean exit on Ctrl+C.
================================================================================
"""

import sys
import os
import time
import argparse
from typing import Optional, List

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("\n[ERROR] 'pyserial' library not found!")
    print("Please install required libraries by running:")
    print("    pip install pyserial openpyxl\n")
    sys.exit(1)

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    print("\n[ERROR] 'openpyxl' library not found!")
    print("Please install required libraries by running:")
    print("    pip install pyserial openpyxl\n")
    sys.exit(1)

# Default Excel filename in script directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_EXCEL_PATH = os.path.join(SCRIPT_DIR, "flow_calibration.xlsx")

# Expected Excel Headers
EXCEL_HEADERS = [
    "Timestamp (ms)",
    "Pump 2 PWM (%)",
    "Frequency (Hz)",
    "Estimated Flow (L/min)",
    "Actual Flow (L/min)"
]

def find_available_com_ports() -> List[str]:
    """Scan and return list of available COM port names."""
    ports = serial.tools.list_ports.comports()
    return [p.device for p in ports]

def select_com_port(requested_port: Optional[str] = None) -> str:
    """Determine the COM port to use, with auto-detection fallback."""
    if requested_port:
        return requested_port.upper()

    available = serial.tools.list_ports.comports()
    if not available:
        print("[WARN] No active COM ports detected by serial scanner.")
        print("Defaulting to 'COM3'. If your ESP32 is on a different port, specify --port <PORT>.")
        return "COM3"

    # Prioritize common ESP32 USB-to-UART bridges (CP210x, CH340, FTDI)
    for p in available:
        desc = (p.description or "").lower()
        if "cp210" in desc or "ch340" in desc or "uart" in desc or "serial" in desc:
            print(f"[AUTO-DETECT] Selected ESP32 port: {p.device} ({p.description})")
            return p.device

    # If only one port is found, use it
    if len(available) == 1:
        selected = available[0].device
        print(f"[AUTO-DETECT] Using single available port: {selected} ({available[0].description})")
        return selected

    # If multiple ports exist and none uniquely matched ESP32, list them
    print("\nAvailable COM Ports:")
    for idx, p in enumerate(available, start=1):
        print(f"  [{idx}] {p.device}: {p.description}")
    try:
        choice = input(f"\nSelect port [1-{len(available)}] (or type port name, e.g., COM3): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(available):
            return available[int(choice) - 1].device
        elif choice:
            return choice.upper()
    except (EOFError, KeyboardInterrupt):
        sys.exit(0)

    return available[0].device

def get_or_create_workbook(filepath: str):
    """
    Open existing workbook or create a new one with styled headers.
    Returns (workbook, worksheet, existing_data_rows_count).
    """
    if os.path.exists(filepath):
        try:
            wb = openpyxl.load_workbook(filepath)
            ws = wb.active
            print(f"[EXCEL] Loaded existing file: {filepath}")

            # Check if headers exist
            headers_exist = False
            if ws.max_row >= 1:
                first_row = [str(ws.cell(row=1, column=c).value or "").strip() for c in range(1, len(EXCEL_HEADERS) + 1)]
                if first_row == EXCEL_HEADERS:
                    headers_exist = True

            if not headers_exist:
                # Add headers at row 1 if missing
                ws.insert_rows(1)
                setup_header_styling(ws)
                wb.save(filepath)

            existing_readings = max(0, ws.max_row - 1)
            print(f"[EXCEL] Existing records found: {existing_readings}. New records will be appended.")
            return wb, ws, existing_readings

        except Exception as e:
            print(f"[WARN] Could not load existing Excel file ({e}).")
            backup_path = filepath + f".bak_{int(time.time())}"
            print(f"[WARN] Creating backup of corrupted file at: {backup_path}")
            os.rename(filepath, backup_path)

    # Create brand new workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Flow Calibration"

    setup_header_styling(ws)
    wb.save(filepath)
    print(f"[EXCEL] Created new calibration spreadsheet: {filepath}")
    return wb, ws, 0

def setup_header_styling(ws):
    """Write headers with clean styling and adjust column widths."""
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid") # Dark Navy Blue
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    thin_border = Border(
        left=Side(style='thin', color='BFBFBF'),
        right=Side(style='thin', color='BFBFBF'),
        top=Side(style='thin', color='BFBFBF'),
        bottom=Side(style='thin', color='BFBFBF')
    )

    for col_idx, header_text in enumerate(EXCEL_HEADERS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header_text)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = thin_border

    # Set column widths for readability
    col_widths = [18, 18, 18, 24, 22]
    for col_idx, width in enumerate(col_widths, start=1):
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = width

    ws.row_dimensions[1].height = 28

def parse_csv_line(line: str) -> Optional[dict]:
    """
    Parses an incoming serial line.
    If it matches the 4-field ESP32 CSV format:
      timestamp_ms,pump2_pwm,frequency_hz,estimated_flow_lpm
    Returns dict with parsed values, otherwise returns None.
    """
    if not line:
        return None

    # Strip whitespace/newlines
    cleaned = line.strip()
    if not cleaned:
        return None

    tokens = [t.strip() for t in cleaned.split(',')]
    if len(tokens) != 4:
        return None

    # Check if this is the literal text header emitted by ESP32 on startup
    if tokens[0].lower().startswith("timestamp"):
        return {"is_header": True, "raw": cleaned}

    try:
        t_ms = int(tokens[0])
        pwm = int(tokens[1])
        # frequency can be parsed as float, then converted to int if whole number
        freq_raw = float(tokens[2])
        freq = int(round(freq_raw)) if freq_raw.is_integer() else round(freq_raw, 1)
        flow = float(tokens[3])

        return {
            "is_header": False,
            "timestamp_ms": t_ms,
            "pump2_pwm": pwm,
            "frequency_hz": freq,
            "estimated_flow_lpm": round(flow, 2),
            "actual_flow_lpm": None  # Left blank for user physical calculation
        }
    except (ValueError, TypeError):
        return None

def run_simulated_test(excel_path: str):
    """Self-test mode: simulates incoming serial CSV rows to verify Excel file creation."""
    print("\n--- RUNNING SELF-TEST MODE ---")
    wb, ws, initial_count = get_or_create_workbook(excel_path)

    test_lines = [
        "[LOG] Flow logging started",
        "timestamp_ms,pump2_pwm,frequency_hz,estimated_flow_lpm",
        "12345,50,285,2.91",
        "14845,50,286,2.92",
        "17345,50,284,2.90",
        "[HEARTBEAT] ESP32 Alive | ... (should be ignored)",
        "19845,75,420,4.29",
        "22345,100,560,5.71",
        "[LOG] Flow logging stopped"
    ]

    added = 0
    for line in test_lines:
        parsed = parse_csv_line(line)
        if parsed:
            if parsed.get("is_header"):
                print(f"[TEST ESP32 HEADER]: {line}")
            else:
                row_data = [
                    parsed["timestamp_ms"],
                    parsed["pump2_pwm"],
                    parsed["frequency_hz"],
                    parsed["estimated_flow_lpm"],
                    parsed["actual_flow_lpm"]
                ]
                ws.append(row_data)
                added += 1
                wb.save(excel_path)
                print(f"  [SAVED ROW #{initial_count + added}] {row_data[0]} ms | PWM: {row_data[1]}% | Freq: {row_data[2]} Hz | Flow: {row_data[3]:.2f} L/min")
        else:
            print(f"  [IGNORED TEXT] {line}")

    print(f"\n[SUCCESS] Self-test complete! Added {added} rows. Excel file saved at:\n{excel_path}\n")

def main():
    parser = argparse.ArgumentParser(
        description="ESP32 YFS401 Flow Sensor Continuous CSV Data Logger",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python flow_logger.py
  python flow_logger.py --port COM3
  python flow_logger.py --port COM3 --output my_calibration.xlsx
  python flow_logger.py --test
        """
    )
    parser.add_argument("-p", "--port", type=str, default=None,
                        help="Serial COM port (e.g. COM3). Auto-detected if omitted.")
    parser.add_argument("-b", "--baud", type=int, default=115200,
                        help="Serial baud rate (default: 115200)")
    parser.add_argument("-o", "--output", type=str, default=DEFAULT_EXCEL_PATH,
                        help=f"Target Excel file path (default: {DEFAULT_EXCEL_PATH})")
    parser.add_argument("--start", action="store_true", default=True,
                        help="Automatically send 'L' to ESP32 on startup to begin logging (default: True)")
    parser.add_argument("--no-start", action="store_false", dest="start",
                        help="Do not send 'L' on startup (listen-only mode)")
    parser.add_argument("--test", action="store_true",
                        help="Run standalone simulation test without hardware connection")

    args = parser.parse_args()

    # Self-test mode (validates Excel without hardware)
    if args.test:
        run_simulated_test(args.output)
        return

    # Prepare Excel workbook
    wb, ws, initial_records = get_or_create_workbook(args.output)

    # Determine COM port
    port_name = select_com_port(args.port)
    print(f"\n[SERIAL] Connecting to {port_name} at {args.baud} baud...")

    try:
        ser = serial.Serial(
            port=port_name,
            baudrate=args.baud,
            timeout=1.0,
            # Prevent automatic DTR/RTS reset toggling on Windows if possible
            dsrdtr=False,
            rtscts=False
        )
    except serial.SerialException as e:
        print(f"\n[ERROR] Could not open port {port_name}: {e}")
        print("Please check that:")
        print("  1. The ESP32 is plugged in via USB.")
        print("  2. No other program (e.g. PlatformIO Monitor, Arduino IDE) has the port open.")
        print(f"  3. Correct COM port is selected (use: python flow_logger.py --port <PORT>)\n")
        sys.exit(1)

    print(f"[SERIAL] Successfully connected to {port_name}!")
    print(f"[LOGGING] Data will be written to: {args.output}")
    print("[LOGGING] Press Ctrl+C at any time to safely stop logging and save.\n")

    # If --start is active, wait briefly for ESP32 connection stability and send 'L'
    if args.start:
        time.sleep(1.2) # Allow boot/serial settlement
        print("[SERIAL] Sending 'L' command to ESP32 to activate CSV logging...")
        try:
            ser.write(b"L\n")
            ser.flush()
        except Exception as e:
            print(f"[WARN] Could not send 'L' command: {e}")

    new_records_count = 0

    try:
        while True:
            raw_line = ser.readline()
            if not raw_line:
                continue

            line = raw_line.decode('utf-8', errors='ignore').strip()
            if not line:
                continue

            parsed = parse_csv_line(line)
            if parsed:
                if parsed.get("is_header"):
                    print(f"[ESP32] CSV Header: {line}")
                else:
                    # Valid CSV reading
                    row_data = [
                        parsed["timestamp_ms"],
                        parsed["pump2_pwm"],
                        parsed["frequency_hz"],
                        parsed["estimated_flow_lpm"],
                        parsed["actual_flow_lpm"]  # None
                    ]
                    ws.append(row_data)
                    new_records_count += 1

                    # Save immediately after each row for 100% crash and interrupt safety
                    wb.save(args.output)

                    print(f"[RECORD #{initial_records + new_records_count:04d}] "
                          f"Time: {parsed['timestamp_ms']:>8} ms | "
                          f"Pump 2 PWM: {parsed['pump2_pwm']:>3}% | "
                          f"Freq: {parsed['frequency_hz']:>4} Hz | "
                          f"Est Flow: {parsed['estimated_flow_lpm']:.2f} L/min")
            else:
                # Print non-CSV text for transparency (e.g., [LOG] messages, status)
                print(f"[ESP32]: {line}")

    except KeyboardInterrupt:
        print("\n\n[LOGGER] Stop signal (Ctrl+C) received.")

    finally:
        # Final flush and save
        try:
            wb.save(args.output)
            print(f"[EXCEL] Successfully saved: {args.output}")
        except Exception as e:
            print(f"[ERROR] Could not save Excel file on exit: {e}")

        # Send 'L' to stop logging on ESP32 if we started it
        if args.start and ser.is_open:
            try:
                print("[SERIAL] Sending 'L' to stop ESP32 CSV logging...")
                ser.write(b"L\n")
                ser.flush()
                time.sleep(0.3)
            except Exception:
                pass

        if ser.is_open:
            ser.close()
            print("[SERIAL] Port closed.")

        total_rows = ws.max_row - 1 if ws.max_row >= 1 else 0
        print("--------------------------------------------------")
        print(f"  Logging Session Summary:")
        print(f"  - New readings added: {new_records_count}")
        print(f"  - Total records in file: {total_rows}")
        print(f"  - File location: {args.output}")
        print("--------------------------------------------------\n")

if __name__ == "__main__":
    main()
