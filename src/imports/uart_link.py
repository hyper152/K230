"""UART2 link used to send ball positions to the external controller."""

from machine import FPIOA, UART


def init_uart2(baudrate=115200, tx_pin=44, rx_pin=45):
    try:
        fpioa = FPIOA()
        fpioa.set_function(tx_pin, FPIOA.UART2_TXD)
        fpioa.set_function(rx_pin, FPIOA.UART2_RXD)
        uart = UART(UART.UART2, baudrate=baudrate, bits=UART.EIGHTBITS,
                    parity=UART.PARITY_NONE, stop=UART.STOPBITS_ONE)
        print("UART2 initialized: baudrate={} (IO{}=TX, IO{}=RX)".format(
            baudrate, tx_pin, rx_pin))
        probe = "UART2_READY\r\n"
        written = uart.write(probe)
        print("UART2 startup probe: {}/{} bytes".format(written, len(probe)))
        return uart
    except Exception as exc:
        print("UART2 init failed, fallback to REPL serial only: {}".format(exc))
        return None


def send_line(uart, message):
    if uart is not None:
        try:
            data = message + "\r\n"
            written = uart.write(data)
            if written != len(data):
                print("UART2 short write: {}/{} bytes".format(written, len(data)))
        except Exception as exc:
            print("UART2 write failed: {}".format(exc))
    print(message)


def deinit_uart(uart):
    if uart is not None:
        try:
            uart.deinit()
        except Exception:
            pass
