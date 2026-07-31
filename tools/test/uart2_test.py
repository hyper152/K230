"""K230D BOX PH2.0 接口2 UART2 最小发送测试。"""

from machine import FPIOA, UART
import time


TX_PIN = 44
RX_PIN = 45
BAUDRATE = 115200

fpioa = FPIOA()
fpioa.set_function(TX_PIN, FPIOA.UART2_TXD)
fpioa.set_function(RX_PIN, FPIOA.UART2_RXD)

print("UART2 TX pin:", fpioa.get_pin_num(FPIOA.UART2_TXD))
print("UART2 RX pin:", fpioa.get_pin_num(FPIOA.UART2_RXD))

uart2 = UART(
    UART.UART2,
    baudrate=BAUDRATE,
    bits=UART.EIGHTBITS,
    parity=UART.PARITY_NONE,
    stop=UART.STOPBITS_ONE,
)

# 0x55 的数据位为 01010101，连续发送时示波器上会形成清晰、稳定的方波。
# 115200 波特率下，相邻翻转间隔约 8.68 us，方波频率约 57.6 kHz。
pattern = bytes([0x55]) * 256
try:
    while True:
        written = uart2.write(pattern)
        if written != len(pattern):
            print("UART2 short write: {}/{}".format(written, len(pattern)))
        time.sleep_ms(2)
finally:
    uart2.deinit()
