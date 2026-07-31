"""LongQiu wireless image module driver for CanMV K230."""

from machine import FPIOA, Pin, SPI
from time import sleep_us, sleep_ms, ticks_us, ticks_diff
import _thread
import image

FRAME_HEAD = b"\xA0\xFF\xFF\xA0"
FRAME_TAIL = b"\xB0\xB0\x0A\x0D"


class WirelessImageSender:
    def __init__(self, width=188, height=120, baudrate=5_000_000,
                 cs_pin=19, clk_pin=15, mosi_pin=16, miso_pin=17,
                 ready_pin=18, spi_phase=1, compensate_bit_shift=False):
        self.width = width
        self.height = height
        self.baudrate = baudrate
        self.compensate_bit_shift = compensate_bit_shift
        self._native_path_reported = False
        self._source_shape = None
        self._x_map = None
        self._y_map = None
        self._raw = bytearray(width * height)
        self._frame = bytearray(width * height + 8)
        self._wire = bytearray(width * height + 9)

        fpioa = FPIOA()
        fpioa.set_function(cs_pin, FPIOA.GPIO19)
        fpioa.set_function(clk_pin, FPIOA.QSPI0_CLK)
        fpioa.set_function(mosi_pin, FPIOA.QSPI0_D0)
        fpioa.set_function(miso_pin, FPIOA.QSPI0_D1)
        fpioa.set_function(ready_pin, FPIOA.GPIO18)

        self.cs = Pin(cs_pin, Pin.OUT, pull=Pin.PULL_NONE, drive=15)
        self.ready = Pin(ready_pin, Pin.IN, pull=Pin.PULL_NONE)
        self.cs.value(1)

        # The vendor driver specifies SPI mode 3: CPOL=1, CPHA=1.
        self.spi = SPI(1, baudrate=baudrate, polarity=1,
                       phase=spi_phase, bits=8)
        print("Wireless image SPI initialized: {} Hz, mode={}, CS={}, CLK={}, MOSI={}, MISO={}, IO2={}".format(
            baudrate, 2 + spi_phase, cs_pin, clk_pin, mosi_pin, miso_pin, ready_pin))
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

        source_shape = (src_w, src_h)
        if self._source_shape != source_shape:
            self._x_map = tuple(col * src_w // self.width
                                for col in range(self.width))
            self._y_map = tuple(row * src_h // self.height
                                for row in range(self.height))
            self._source_shape = source_shape

        raw = self._raw
        index = 0
        # The green plane is a good luminance approximation and avoids three
        # ndarray scalar reads plus RGB arithmetic for every output pixel.
        # On CanMV those Python-level scalar accesses dominate frame time.
        for y in self._y_map:
            for x in self._x_map:
                if four_dim:
                    raw[index] = int(frame[0, 1, y, x])
                else:
                    raw[index] = int(frame[1, y, x])
                index += 1
        return None, raw

    def _green_plane_gray_bytes(self, plane, src_w, src_h):
        source_shape = (src_w, src_h)
        if self._source_shape != source_shape:
            self._x_map = tuple(col * src_w // self.width
                                for col in range(self.width))
            self._y_map = tuple(row * src_h // self.height
                                for row in range(self.height))
            self._source_shape = source_shape

        raw = self._raw
        index = 0
        for y in self._y_map:
            row_start = y * src_w
            for x in self._x_map:
                raw[index] = plane[row_start + x]
                index += 1
        return raw

    def _make_protocol_frame(self, camera_frame):
        # The native RGBP888 wrapper returns an invalid repeating 0x55 buffer
        # on this CanMV firmware. Use the verified ndarray conversion path.
        native_img, raw = self._fallback_gray_bytes(camera_frame)
        if not self._native_path_reported:
            print("Wireless image verified ndarray conversion enabled")
            self._native_path_reported = True

        frame = self._frame
        frame[0:4] = FRAME_HEAD
        frame[4:4 + self.width * self.height] = raw
        frame[-4:] = FRAME_TAIL
        return native_img, frame

    def _make_green_protocol_frame(self, plane, src_w, src_h):
        raw = self._green_plane_gray_bytes(plane, src_w, src_h)
        frame = self._frame
        frame[0:4] = FRAME_HEAD
        frame[4:4 + self.width * self.height] = raw
        frame[-4:] = FRAME_TAIL
        return frame

    def _encode_wire(self, frame):
        total = len(frame)
        wire = self._wire
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
            if native_img is not None:
                del native_img
        return True

    def send_green_plane(self, plane, src_w, src_h):
        frame = self._make_green_protocol_frame(plane, src_w, src_h)
        wire = self._encode_wire(frame) if self.compensate_bit_shift else frame
        for offset in range(0, len(wire), 4000):
            self._write_chunk(wire[offset:offset + 4000])
        return True

    def send_gray_bytes(self, raw):
        expected = self.width * self.height
        if len(raw) != expected:
            raise ValueError("gray payload size is {}, expected {}".format(
                len(raw), expected))
        frame = self._frame
        frame[0:4] = FRAME_HEAD
        frame[4:4 + expected] = raw
        frame[-4:] = FRAME_TAIL
        wire = self._encode_wire(frame) if self.compensate_bit_shift else frame
        for offset in range(0, len(wire), 4000):
            self._write_chunk(wire[offset:offset + 4000])
        return True

    def send_raw_bytes(self, raw):
        """Send JPEG/PNG bytes directly; the PC tool detects their signature."""
        for offset in range(0, len(raw), 4000):
            self._write_chunk(raw[offset:offset + 4000])
        return True

    def deinit(self):
        try:
            self.spi.deinit()
        except Exception:
            pass


class AsyncWirelessImageSender:
    """Latest-frame-only image pipeline running SPI work in a worker thread."""

    def __init__(self, sensor=None, sensor_channel=1, image_format="gray",
                 jpeg_quality=45, **kwargs):
        self.sender = WirelessImageSender(**kwargs)
        self.sensor = sensor
        self.sensor_channel = sensor_channel
        self.image_format = image_format.lower()
        self.jpeg_quality = jpeg_quality
        self._lock = _thread.allocate_lock()
        self._pending = None
        self._running = True
        self._stopped = False
        self.submitted = 0
        self.dropped = 0
        self.sent = 0
        self.snapshot_us = 0
        self.copy_us = 0
        self.send_us = 0
        self.jpeg_bytes = 0
        _thread.start_new_thread(self._worker, ())
        print("Wireless image worker started: format={}, jpeg_quality={}".format(
            self.image_format, self.jpeg_quality))

    @staticmethod
    def _jpeg_bytes(jpeg_img):
        # OpenMV-compatible firmwares expose bytearray(); keep two fallbacks
        # for CanMV builds with a slightly different image binding.
        if hasattr(jpeg_img, "bytearray"):
            data = jpeg_img.bytearray()
        elif hasattr(jpeg_img, "to_bytes"):
            data = jpeg_img.to_bytes()
        else:
            data = bytes(jpeg_img)
        if len(data) < 4 or data[0] != 0xFF or data[1] != 0xD8:
            raise ValueError("invalid JPEG buffer, size={}".format(len(data)))
        return data

    @staticmethod
    def _copy_green_plane(frame):
        shape = frame.shape
        if len(shape) == 4:
            src_h, src_w = shape[2], shape[3]
            plane = bytes(frame[0, 1, :, :])
        elif len(shape) == 3:
            src_h, src_w = shape[1], shape[2]
            plane = bytes(frame[1, :, :])
        else:
            raise ValueError("unsupported camera ndarray shape: {}".format(shape))
        expected = src_w * src_h
        if len(plane) != expected:
            raise ValueError("green plane size is {}, expected {}".format(
                len(plane), expected))
        return plane, src_w, src_h

    def submit(self, frame=None):
        if self.sensor is None:
            # Fallback: copy one plane while the camera frame is valid.
            plane, src_w, src_h = self._copy_green_plane(frame)
            item = (plane, src_w, src_h)
        else:
            # The worker snapshots the independent hardware grayscale channel.
            # A token is enough; no camera ndarray is copied in the YOLO thread.
            item = True
        self._lock.acquire()
        try:
            if self._pending is not None:
                self.dropped += 1
            self._pending = item
            self.submitted += 1
        finally:
            self._lock.release()
        return True

    def _take_pending(self):
        self._lock.acquire()
        try:
            item = self._pending
            self._pending = None
            return item
        finally:
            self._lock.release()

    def _worker(self):
        try:
            while self._running:
                item = self._take_pending()
                if item is None:
                    sleep_ms(1)
                    continue
                try:
                    if self.sensor is not None:
                        stage_start = ticks_us()
                        gray_img = self.sensor.snapshot(chn=self.sensor_channel)
                        snapshot_done = ticks_us()
                        if self.image_format == "jpeg":
                            jpeg_img = gray_img.compressed(
                                quality=self.jpeg_quality)
                            raw = self._jpeg_bytes(jpeg_img)
                            copy_done = ticks_us()
                            self.sender.send_raw_bytes(raw)
                            self.jpeg_bytes += len(raw)
                            del jpeg_img
                        else:
                            gray_np = gray_img.to_numpy_ref()
                            raw = bytes(gray_np)
                            copy_done = ticks_us()
                            expected = self.sender.width * self.sender.height
                            if len(raw) != expected:
                                raise ValueError("hardware gray frame size is {}, expected {}".format(
                                    len(raw), expected))
                            self.sender.send_gray_bytes(raw)
                            del gray_np
                        send_done = ticks_us()
                        self.snapshot_us += ticks_diff(snapshot_done, stage_start)
                        self.copy_us += ticks_diff(copy_done, snapshot_done)
                        self.send_us += ticks_diff(send_done, copy_done)
                        del gray_img
                    else:
                        self.sender.send_green_plane(item[0], item[1], item[2])
                    self.sent += 1
                except Exception as exc:
                    print("Wireless image worker send failed: {}".format(exc))
        finally:
            self._stopped = True

    def deinit(self):
        self._running = False
        # Allow the worker to leave without deinitializing SPI underneath it.
        for _ in range(500):
            if self._stopped:
                break
            sleep_ms(1)
        self.sender.deinit()
        print("Wireless image worker stopped: submitted={}, sent={}, dropped={}".format(
            self.submitted, self.sent, self.dropped))
        if self.sent > 0 and self.sensor is not None:
            print("Wireless image avg ms: snapshot={:.1f}, encode={:.1f}, spi={:.1f}, total={:.1f}".format(
                self.snapshot_us / self.sent / 1000,
                self.copy_us / self.sent / 1000,
                self.send_us / self.sent / 1000,
                (self.snapshot_us + self.copy_us + self.send_us) /
                self.sent / 1000))
            if self.image_format == "jpeg":
                print("Wireless image JPEG avg bytes: {:.0f}".format(
                    self.jpeg_bytes / self.sent))
