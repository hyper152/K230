"""K230 应用入口，Port2 由本模块统一管理。"""

from machine import FPIOA, UART
import time
from imports.init import start


UART2_TX_PIN = 44
UART2_RX_PIN = 45
UART2_BAUDRATE = 115200


port2 = None
port2_fpioa = FPIOA()


def port2_init():
    """在媒体模块初始化前创建 UART2，保持与已验证版本的顺序一致。"""
    global port2
    if port2 is not None:
        return
    port2_fpioa.set_function(UART2_TX_PIN, FPIOA.UART2_TXD, oe=1)
    port2_fpioa.set_function(UART2_RX_PIN, FPIOA.UART2_RXD, ie=1)
    port2 = UART(
        UART.UART2,
        baudrate=UART2_BAUDRATE,
        bits=UART.EIGHTBITS,
        parity=UART.PARITY_NONE,
        stop=UART.STOPBITS_ONE,
    )
    print("Port2 initialized in main: baudrate={} (IO{}=TX, IO{}=RX)".format(
        UART2_BAUDRATE,
        port2_fpioa.get_pin_num(FPIOA.UART2_TXD),
        port2_fpioa.get_pin_num(FPIOA.UART2_RXD),
    ))
    port2_send("UART2_READY")


def port2_media_ready():
    """摄像头启动后重新设置引脚方向和复用，不重建 UART 对象。"""
    port2_fpioa.set_function(UART2_TX_PIN, FPIOA.UART2_TXD, oe=1)
    port2_fpioa.set_function(UART2_RX_PIN, FPIOA.UART2_RXD, ie=1)
    port2_send("UART2_MEDIA_READY")
    print("Port2 mapping reasserted after media init")


def port2_send(message):
    if port2 is None:
        raise RuntimeError("Port2 used before media initialization")
    data = message + "\r\n"
    written = port2.write(data)
    # 等待最后一个停止位完整发送到 IO44。
    if hasattr(port2, "flush"):
        port2.flush()
    # 与最小串口测试保持一致，给驱动和中断留出发送时间。
    time.sleep_ms(2)
    if written != len(data):
        print("Port2 short write: {}/{} bytes".format(written, len(data)))


port2_init()

try:
    start(port2_init=port2_media_ready, port2_send=port2_send)
finally:
    if port2 is not None:
        port2.deinit()
