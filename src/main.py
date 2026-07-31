"""K230 application entry point with Port2 owned by this module."""

from machine import FPIOA, UART
import time
from imports.init import start


UART2_TX_PIN = 44
UART2_RX_PIN = 45
UART2_BAUDRATE = 115200


port2 = None


def port2_init():
    """Initialize Port2 only after PipeLine/media initialization."""
    global port2
    if port2 is not None:
        return
    fpioa = FPIOA()
    fpioa.set_function(UART2_TX_PIN, FPIOA.UART2_TXD)
    fpioa.set_function(UART2_RX_PIN, FPIOA.UART2_RXD)
    port2 = UART(
        UART.UART2,
        baudrate=UART2_BAUDRATE,
        bits=UART.EIGHTBITS,
        parity=UART.PARITY_NONE,
        stop=UART.STOPBITS_ONE,
    )
    print("Port2 initialized in main: baudrate={} (IO{}=TX, IO{}=RX)".format(
        UART2_BAUDRATE,
        fpioa.get_pin_num(FPIOA.UART2_TXD),
        fpioa.get_pin_num(FPIOA.UART2_RXD),
    ))
    # Same physical-output test, now at the verified initialization point.
    port2.write(bytes([0x55]) * 256)
    if hasattr(port2, "flush"):
        port2.flush()
    time.sleep_ms(2)
    port2_send("UART2_READY")


def port2_send(message):
    if port2 is None:
        raise RuntimeError("Port2 used before media initialization")
    data = message + "\r\n"
    written = port2.write(data)
    # Ensure the final stop bit reaches IO44 before the SPI worker resumes.
    if hasattr(port2, "flush"):
        port2.flush()
    # Match tools/test/uart2_test.py: allow the driver/IRQ to drain TX.
    time.sleep_ms(2)
    if written != len(data):
        print("Port2 short write: {}/{} bytes".format(written, len(data)))


try:
    start(port2_init=port2_init, port2_send=port2_send)
finally:
    if port2 is not None:
        port2.deinit()
