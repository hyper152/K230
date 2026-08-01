"""Port2 UART ownership and transmission functions."""

from machine import FPIOA, UART
from .config import uart2_baudrate, uart2_tx_pin, uart2_rx_pin


_port2 = None
_fpioa = FPIOA()


def init_port2():
    """初始化 UART2，并发送启动就绪消息。"""
    global _port2
    if _port2 is not None:
        return
    _fpioa.set_function(uart2_tx_pin, FPIOA.UART2_TXD, oe=1)
    _fpioa.set_function(uart2_rx_pin, FPIOA.UART2_RXD, ie=1)
    _port2 = UART(
        UART.UART2,
        baudrate=uart2_baudrate,
        bits=UART.EIGHTBITS,
        parity=UART.PARITY_NONE,
        stop=UART.STOPBITS_ONE,
    )
    send_port2("UART2_READY")


def remap_port2_after_media():
    """媒体初始化后恢复 UART2 引脚复用，不重建 UART 对象。"""
    _fpioa.set_function(uart2_tx_pin, FPIOA.UART2_TXD, oe=1)
    _fpioa.set_function(uart2_rx_pin, FPIOA.UART2_RXD, ie=1)
    send_port2("UART2_MEDIA_READY")


def send_port2(message):
    """使用既有文本协议向 Port2 发送一行。"""
    if _port2 is None:
        raise RuntimeError("Port2 used before initialization")
    _port2.write(message + "\r\n")


def deinit_port2():
    """释放 UART2。"""
    global _port2
    if _port2 is not None:
        _port2.deinit()
        _port2 = None
