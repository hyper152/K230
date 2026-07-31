"""K230D BOX PH2.0 接口2 IO44 物理引脚测试。

运行后 IO44 每 500 ms 在高低电平之间翻转。
此测试不使用 UART，用于确认 PH2.0 接口2 的 TX/IO44 针位。
"""

from machine import FPIOA, Pin
import time


TEST_PIN = 44

fpioa = FPIOA()
fpioa.set_function(TEST_PIN, FPIOA.GPIO44, oe=1)
pin = Pin(TEST_PIN, Pin.OUT, pull=Pin.PULL_NONE, drive=7)

level = 0
print("PORT2 IO44 GPIO toggle test started")
while True:
    level = 1 - level
    pin.value(level)
    print("IO44={}".format(level))
    time.sleep_ms(500)
