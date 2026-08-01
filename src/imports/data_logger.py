"""Write vision and STM32 debug data to the TF card."""

import os
from time import ticks_ms, ticks_diff


LOG_DIR = "/sdcard/logs"
FLUSH_INTERVAL = 20

_log_file = None
_log_path = None
_pending_rows = 0
_start_ms = 0


def _csv_text(value):
    text = str(value).replace('"', '""')
    return '"{}"'.format(text)


def init_data_log():
    """Create one new CSV file for this boot/run and return its path."""
    global _log_file, _log_path, _pending_rows, _start_ms
    try:
        try:
            os.stat(LOG_DIR)
        except Exception:
            os.mkdir(LOG_DIR)

        index = 1
        while True:
            path = "{}/run_{:04d}.csv".format(LOG_DIR, index)
            try:
                os.stat(path)
                index += 1
            except Exception:
                break

        _log_file = open(path, "w")
        _log_path = path
        _pending_rows = 0
        _start_ms = ticks_ms()
        _log_file.write(
            "time_ms,source,frame,detected,x_px,position_cm,stm32_line\n"
        )
        _log_file.flush()
        print("[LOG]", path)
        return path
    except Exception as error:
        _log_file = None
        print("[LOG ERROR]", repr(error))
        return None


def _write(row):
    global _pending_rows
    if _log_file is None:
        return
    try:
        _log_file.write(row + "\n")
        _pending_rows += 1
        if _pending_rows >= FLUSH_INTERVAL:
            _log_file.flush()
            _pending_rows = 0
    except Exception as error:
        print("[LOG WRITE ERROR]", repr(error))


def log_vision(frame, result, yolo):
    """Log the selected detection once per inference frame."""
    elapsed = ticks_diff(ticks_ms(), _start_ms)
    if result:
        x_px = float(result[0][0])
        position_cm = yolo.x_to_position_cm(x_px)
        _write("{0},VISION,{1},1,{2:.2f},{3:.3f},".format(
            elapsed, frame, x_px, position_cm
        ))
    else:
        _write("{},VISION,{},0,,,,".format(elapsed, frame))


def log_stm32(line):
    """Log one complete line received from STM32 UART1/UART2 link."""
    elapsed = ticks_diff(ticks_ms(), _start_ms)
    _write("{},STM32,,,,,{}".format(elapsed, _csv_text(line)))


def close_data_log():
    global _log_file
    if _log_file is not None:
        try:
            _log_file.flush()
            _log_file.close()
        except Exception as error:
            print("[LOG CLOSE ERROR]", repr(error))
        _log_file = None


def get_log_path():
    return _log_path
