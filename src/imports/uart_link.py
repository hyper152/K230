"""UART2 link used to send ball positions to the external controller."""

from machine import FPIOA, UART
from time import sleep_ms
import _thread

print = lambda *args, **kwargs: None


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


def send_line(uart, message, echo=True):
    if uart is not None:
        try:
            data = message + "\r\n"
            written = uart.write(data)
            if written != len(data):
                print("UART2 short write: {}/{} bytes".format(written, len(data)))
        except Exception as exc:
            print("UART2 write failed: {}".format(exc))
    if echo:
        print(message)


def deinit_uart(uart):
    if uart is not None:
        try:
            uart.deinit()
        except Exception:
            pass


class PriorityUartSender:
    """Latest-value UART worker isolated from AI and image transmission."""

    def __init__(self, uart):
        self.uart = uart
        self._lock = _thread.allocate_lock()
        self._pending = None
        self._running = True
        self._stopped = False
        self.submitted = 0
        self.sent = 0
        self.dropped = 0
        _thread.start_new_thread(self._worker, ())
        print("UART2 priority worker started")

    def submit(self, message):
        self._lock.acquire()
        try:
            if self._pending is not None:
                self.dropped += 1
            self._pending = message
            self.submitted += 1
        finally:
            self._lock.release()

    def _take_pending(self):
        self._lock.acquire()
        try:
            message = self._pending
            self._pending = None
            return message
        finally:
            self._lock.release()

    def _worker(self):
        try:
            while self._running:
                message = self._take_pending()
                if message is None:
                    sleep_ms(1)
                    continue
                if self.uart is not None:
                    try:
                        data = message + "\r\n"
                        written = self.uart.write(data)
                        if written != len(data):
                            print("UART2 short write: {}/{} bytes".format(
                                written, len(data)))
                    except Exception as exc:
                        print("UART2 worker write failed: {}".format(exc))
                self.sent += 1
                # Explicit scheduling point for this CanMV MicroPython build.
                sleep_ms(0)
        finally:
            self._stopped = True

    def deinit(self):
        self._running = False
        for _ in range(200):
            if self._stopped:
                break
            sleep_ms(1)
        print("UART2 priority worker stopped: submitted={}, sent={}, dropped={}".format(
            self.submitted, self.sent, self.dropped))
