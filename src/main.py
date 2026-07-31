"""K230 application entry point with Port2 owned by this module."""

from machine import FPIOA, UART
from imports.init import start


UART2_TX_PIN = 44
UART2_RX_PIN = 45
UART2_BAUDRATE = 115200


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


def port2_send(message):
    data = message + "\r\n"
    written = port2.write(data)
    if written != len(data):
        print("Port2 short write: {}/{} bytes".format(written, len(data)))


# Send a visible startup burst and a readable marker directly from main.py.
port2.write(bytes([0x55]) * 256)
port2_send("UART2_READY")

try:
    start(port2_send=port2_send)
finally:
    port2.deinit()
