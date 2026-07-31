"""K230D BOX PH2.0 接口1/2 UART 交叉回环测试。

接线：接口1 TX(IO40) -> 接口2 RX(IO45)
      接口2 TX(IO44) -> 接口1 RX(IO41)
"""

from machine import FPIOA, UART
import time


fpioa = FPIOA()
fpioa.set_function(40, FPIOA.UART1_TXD, oe=1)
fpioa.set_function(41, FPIOA.UART1_RXD, ie=1)
fpioa.set_function(44, FPIOA.UART2_TXD, oe=1)
fpioa.set_function(45, FPIOA.UART2_RXD, ie=1)

uart1 = UART(UART.UART1, baudrate=115200)
uart2 = UART(UART.UART2, baudrate=115200)

try:
    while True:
        uart2.write(b"FROM_UART2\r\n")
        time.sleep_ms(50)
        print("UART1 received:", uart1.read())

        uart1.write(b"FROM_UART1\r\n")
        time.sleep_ms(50)
        print("UART2 received:", uart2.read())
        time.sleep_ms(900)
finally:
    uart1.deinit()
    uart2.deinit()
