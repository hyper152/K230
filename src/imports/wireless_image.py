"""LongQiu wireless image module driver for CanMV K230."""

from machine import FPIOA, Pin, SPI
from time import sleep_us
import image

FRAME_HEAD = b"\xA0\xFF\xFF\xA0"
FRAME_TAIL = b"\xB0\xB0\x0A\x0D"


class WirelessImageSender:
    def __init__(self, width=188, height=120, baudrate=5_000_000,
                 cs_pin=19, clk_pin=15, mosi_pin=16, miso_pin=17,
                 ready_pin=18, compensate_bit_shift=True):
        self.width = width
        self.height = height
        self.baudrate = baudrate
        self.compensate_bit_shift = compensate_bit_shift
        self._native_path_reported = False

        fpioa = FPIOA()
        fpioa.set_function(cs_pin, FPIOA.GPIO19)
        fpioa.set_function(clk_pin, FPIOA.QSPI0_CLK)
        fpioa.set_function(mosi_pin, FPIOA.QSPI0_D0)
        fpioa.set_function(miso_pin, FPIOA.QSPI0_D1)
        fpioa.set_function(ready_pin, FPIOA.GPIO18)

        self.cs = Pin(cs_pin, Pin.OUT, pull=Pin.PULL_NONE, drive=15)
        self.ready = Pin(ready_pin, Pin.IN, pull=Pin.PULL_NONE)
        self.cs.value(1)

        # Empirically phase=0 is retained for this CanMV firmware. The module
        # link has a stable one-bit shift, compensated in _encode_wire().
        self.spi = SPI(1, baudrate=baudrate, polarity=1, phase=0, bits=8)
        print("Wireless image SPI initialized: {} Hz, CS={}, CLK={}, MOSI={}, MISO={}, IO2={}".format(
            baudrate, cs_pin, clk_pin, mosi_pin, miso_pin, ready_pin))
        print("Wireless image IO2 initial level: {}".format(self.ready.value()))

    @staticmethod
    def _wait_level(pin, target, timeout_us=500):
        elapsed = 0
        while pin.value() != target:
            if elapsed >= timeout_us:
                return False
            sleep_us(50)
            elapsed += 50
        return True

    def _write_chunk(self, data):
        # Vendor code waits briefly but does not discard a frame on timeout.
        self._wait_level(self.ready, 1, 500)
        self.cs.value(0)
        try:
            self.spi.write(data)
        finally:
            self.cs.value(1)
        self._wait_level(self.ready, 0, 500)

    def _native_gray_bytes(self, frame):
        if not hasattr(image, "RGBP888"):
            raise RuntimeError("native image buffer API unavailable")

        shape = frame.shape
        if len(shape) == 4:
            src_h, src_w = shape[2], shape[3]
            src_data = frame.reshape((3, src_h, src_w))
        elif len(shape) == 3:
            src_h, src_w = shape[1], shape[2]
            src_data = frame
        else:
            raise ValueError("unsupported camera ndarray shape: {}".format(shape))

        src_img = image.Image(src_w, src_h, image.RGBP888,
                              alloc=image.ALLOC_REF, data=src_data)
        gray = src_img.to_grayscale(
            x_scale=self.width / src_w,
            y_scale=self.height / src_h,
            copy=True
        )
        if gray.width() != self.width or gray.height() != self.height:
            raise ValueError("native scale result is {}x{}".format(
                gray.width(), gray.height()))
        # Heap-backed images on this firmware do not expose a reliable
        # address through virtaddr(). Copy from the actual ndarray buffer.
        raw = bytes(gray.to_numpy_ref())
        if len(raw) != self.width * self.height:
            raise ValueError("native grayscale buffer size is {}".format(len(raw)))
        return gray, raw

    def _fallback_gray_bytes(self, frame):
        shape = frame.shape
        if len(shape) == 4:
            src_h, src_w = shape[2], shape[3]
            four_dim = True
        elif len(shape) == 3:
            src_h, src_w = shape[1], shape[2]
            four_dim = False
        else:
            raise ValueError("unsupported camera ndarray shape: {}".format(shape))

        raw = bytearray(self.width * self.height)
        index = 0
        for row in range(self.height):
            y = row * src_h // self.height
            for col in range(self.width):
                x = col * src_w // self.width
                if four_dim:
                    r = int(frame[0, 0, y, x])
                    g = int(frame[0, 1, y, x])
                    b = int(frame[0, 2, y, x])
                else:
                    r = int(frame[0, y, x])
                    g = int(frame[1, y, x])
                    b = int(frame[2, y, x])
                raw[index] = (77 * r + 150 * g + 29 * b) >> 8
                index += 1
        return None, raw

    def _make_protocol_frame(self, camera_frame):
        # The native RGBP888 wrapper returns an invalid repeating 0x55 buffer
        # on this CanMV firmware. Use the verified ndarray conversion path.
        native_img, raw = self._fallback_gray_bytes(camera_frame)
        if not self._native_path_reported:
            print("Wireless image verified ndarray conversion enabled")
            self._native_path_reported = True

        frame = bytearray(self.width * self.height + 8)
        frame[0:4] = FRAME_HEAD
        frame[4:4 + self.width * self.height] = raw
        frame[-4:] = FRAME_TAIL
        return native_img, frame

    @staticmethod
    def _encode_wire(frame):
        total = len(frame)
        wire = bytearray(total + 1)
        # Captured SPI data is shifted right by one bit. Seed the preceding
        # bit, then shift the stream left once so the module reconstructs it.
        wire[0] = frame[0] >> 7
        for i in range(total):
            following = frame[i + 1] if i + 1 < total else frame[0]
            wire[i + 1] = ((frame[i] << 1) & 0xFE) | (following >> 7)
        return wire

    def send(self, camera_frame):
        native_img, frame = self._make_protocol_frame(camera_frame)
        wire = self._encode_wire(frame) if self.compensate_bit_shift else frame
        try:
            for offset in range(0, len(wire), 4000):
                self._write_chunk(wire[offset:offset + 4000])
        finally:
            del wire
            del frame
            if native_img is not None:
                del native_img
        return True

    def deinit(self):
        try:
            self.spi.deinit()
        except Exception:
            pass
