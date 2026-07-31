"""K230D BOX PH2.0 接口2 UART2 最小发送测试。"""

from machine import FPIOA, UART
import time


TX_PIN = 44
RX_PIN = 45
BAUDRATE = 115200

fpioa = FPIOA()
fpioa.set_function(TX_PIN, FPIOA.UART2_TXD, oe=1)
fpioa.set_function(RX_PIN, FPIOA.UART2_RXD, ie=1)

print("UART2 TX pin:", fpioa.get_pin_num(FPIOA.UART2_TXD))
print("UART2 RX pin:", fpioa.get_pin_num(FPIOA.UART2_RXD))

uart2 = UART(
    UART.UART2,
    baudrate=BAUDRATE,
    bits=UART.EIGHTBITS,
    parity=UART.PARITY_NONE,
    stop=UART.STOPBITS_ONE,
)

counter = 0
try:
    while True:
        data = "UART2_TEST:{}\r\n".format(counter).encode()
        written = uart2.write(data)
        print("write {}/{} bytes: {}".format(written, len(data), data))
        counter += 1
        time.sleep_ms(500)
finally:
    uart2.deinit()
