"""K230 steel-ball detection application.

依赖 K230 nncase runtime 环境，在 K230 开发板上运行。
"""

from .PipeLine import PipeLine, ScopedTiming
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
import os, gc
from media.media import *
from media.sensor import *
from media.display import *
from time import *
import nncase_runtime as nn
import ulab.numpy as np
import image
import aidemo
from machine import UART, SPI, Pin
from machine import FPIOA
from .uart_link import init_uart2 as init_uart2_link
from .uart_link import deinit_uart
from .uart_link import PriorityUartSender
from .wireless_image import AsyncWirelessImageSender
from .config import *


def find_sensor():
    """扫描 CSI0~CSI2，返回第一个可用的摄像头对象和编号。"""
    print("Initializing camera on CSI{}...".format(camera_sensor_id))
    sensor = Sensor(
        id=camera_sensor_id,
        width=sensor_width,
        height=sensor_height
    )
    print("Camera found on CSI{}".format(camera_sensor_id))
    return sensor, camera_sensor_id


class YOLOv12App(AIBase):

    def __init__(self, kmodel_path, model_input_size, anchors,
                 rgb888p_size, display_size, debug_mode):

        super().__init__(kmodel_path, model_input_size, rgb888p_size, debug_mode)

        self.class_id = ["steel_ball"]

        self.kmodel_path = kmodel_path
        self.model_input_size = model_input_size
        self.confidence_threshold = confidence_threshold
        self.detect_threshold = detect_threshold
        self.nms_threshold = nms_threshold
        self.anchors = anchors

        self.rgb888p_size = [ALIGN_UP(rgb888p_size[0], 16), rgb888p_size[1]]
        self.display_size = [ALIGN_UP(display_size[0], 16), display_size[1]]
        self.debug_mode = debug_mode

        self.ai2d = Ai2d(debug_mode)
        self.ai2d.set_ai2d_dtype(
            nn.ai2d_format.NCHW_FMT,
            nn.ai2d_format.NCHW_FMT,
            np.uint8,
            np.uint8
        )

        # 短时跟踪
        self.last_dets = []
        self.miss_count = 0
        self.max_miss_count = max_miss_count
        self.smooth_alpha = smooth_alpha

        self.scale_x = self.rgb888p_size[0] / self.model_input_size[0]
        self.scale_y = self.scale_x

    def config_preprocess(self, input_image_size=None):
        with ScopedTiming("set preprocess config", self.debug_mode > 0):
            ai2d_input_size = input_image_size if input_image_size else self.rgb888p_size
            top, bottom, left, right = self.get_padding_param()

            if self.debug_mode > 0:
                print("padding: {} {} {} {}".format(top, bottom, left, right))

            self.ai2d.pad([0, 0, 0, 0, top, bottom, left, right], 0, [104, 117, 123])
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            self.ai2d.build(
                [1, 3, ai2d_input_size[1], ai2d_input_size[0]],
                [1, 3, self.model_input_size[1], self.model_input_size[0]]
            )

    def postprocess(self, results):
        det_res = []
        with ScopedTiming("postprocess", self.debug_mode > 0):
            output = results[0][0]

            # 当前模型只有 steel_ball 一个类别，直接读取第 5 行置信度。
            # 避免每个候选框都创建切片、求 max 并转 Python list。
            for i in range(output.shape[1]):
                score = output[4, i]
                if score > self.detect_threshold:
                    x = output[0, i] * self.scale_x
                    y = output[1, i] * self.scale_y
                    w = output[2, i] * self.scale_x
                    h = output[3, i] * self.scale_y
                    det_res.append([x, y, w, h, 0, score])

            det_res.sort(key=lambda x: x[-1], reverse=True)
            det_res = self.nms(det_res, self.nms_threshold)

            show_res = []
            for det in det_res:
                if det[-1] >= self.confidence_threshold:
                    show_res.append(det)

            if len(show_res) == 0 and len(det_res) > 0:
                show_res.append(det_res[0])

            show_res = self.temporal_filter(show_res)

        return show_res

    # ------------------------------------------------------------------ #
    #  工具函数
    # ------------------------------------------------------------------ #

    def nms(self, dets, iou_threshold):
        keep = []
        while len(dets) > 0:
            best = dets[0]
            keep.append(best)
            remain = []
            for i in range(1, len(dets)):
                if self.box_iou(best, dets[i]) < iou_threshold:
                    remain.append(dets[i])
            dets = remain
        return keep

    def box_iou(self, a, b):
        ax1, ay1 = a[0] - a[2] / 2, a[1] - a[3] / 2
        ax2, ay2 = a[0] + a[2] / 2, a[1] + a[3] / 2
        bx1, by1 = b[0] - b[2] / 2, b[1] - b[3] / 2
        bx2, by2 = b[0] + b[2] / 2, b[1] + b[3] / 2
        inter_w = max(0, min(ax2, bx2) - max(ax1, bx1))
        inter_h = max(0, min(ay2, by2) - max(ay1, by1))
        inter_area = inter_w * inter_h
        area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
        area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
        union = area_a + area_b - inter_area
        return inter_area / union if union > 0 else 0

    @staticmethod
    def center_dist(a, b):
        return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2

    def x_to_position_cm(self, x):
        """将钢球中心横坐标按画面宽度线性换算为 0~25 cm。"""
        image_width = self.rgb888p_size[0]
        if image_width <= 0:
            return 0.0
        position_cm = float(x) * track_length_cm / image_width
        return max(0.0, min(track_length_cm, position_cm))

    def temporal_filter(self, dets):
        if len(dets) > 0:
            filtered = []
            for det in dets:
                best_prev = None
                best_iou = 0
                for prev in self.last_dets:
                    iou = self.box_iou(det, prev)
                    if iou > best_iou:
                        best_iou = iou
                        best_prev = prev

                if best_prev is not None:
                    dist2 = self.center_dist(det, best_prev)
                    if best_iou > 0.05 or dist2 < 120 * 120:
                        det[0] = self.smooth_alpha * det[0] + (1 - self.smooth_alpha) * best_prev[0]
                        det[1] = self.smooth_alpha * det[1] + (1 - self.smooth_alpha) * best_prev[1]
                        det[2] = self.smooth_alpha * det[2] + (1 - self.smooth_alpha) * best_prev[2]
                        det[3] = self.smooth_alpha * det[3] + (1 - self.smooth_alpha) * best_prev[3]

                filtered.append(det)

            self.last_dets = filtered
            self.miss_count = 0
            return filtered

        # 短暂漏检：用上一帧结果顶住
        if len(self.last_dets) > 0 and self.miss_count < self.max_miss_count:
            self.miss_count += 1
            hold_dets = []
            for det in self.last_dets:
                hold = [det[0], det[1], det[2], det[3], det[4], det[5] * 0.85]
                hold_dets.append(hold)
            self.last_dets = hold_dets
            return hold_dets

        self.last_dets = []
        self.miss_count = 0
        return []

    def draw_result(self, pl, dets):
        with ScopedTiming("display_draw", self.debug_mode > 0):
            pl.osd_img.clear()
            pl.osd_img.draw_string_advanced(0, 0, 32, "balls: {}".format(len(dets)), color=(255, 0, 255, 0))
            if dets:
                ball_pos_text = "BallPos: {:.2f} cm".format(
                    self.x_to_position_cm(dets[0][0])
                )
            else:
                ball_pos_text = "BallPos: --"
            pl.osd_img.draw_string_advanced(
                0, 36, 32, ball_pos_text, color=(255, 0, 255, 0)
            )

            if dets:
                for det in dets:
                    x, y, w, h = map(lambda v: int(round(v, 0)), det[:4])
                    x = x * self.display_size[0] // self.rgb888p_size[0]
                    y = y * self.display_size[1] // self.rgb888p_size[1]
                    w = w * self.display_size[0] // self.rgb888p_size[0]
                    h = h * self.display_size[1] // self.rgb888p_size[1]

                    x1, y1 = x - w // 2, y - h // 2
                    if x1 < 0:
                        x1 = 0
                    if y1 < 0:
                        y1 = 0
                    if x1 + w > self.display_size[0]:
                        w = self.display_size[0] - x1
                    if y1 + h > self.display_size[1]:
                        h = self.display_size[1] - y1
                    if w <= 0 or h <= 0:
                        continue

                    pl.osd_img.draw_rectangle(x1, y1, w, h, color=(255, 0, 255, 0), thickness=2)
                    pl.osd_img.draw_string_advanced(
                        x1, y1, 32,
                        "{} {}".format(self.class_id[det[-2]], round(det[-1], 2)),
                        color=(255, 0, 255, 0)
                    )

    def get_padding_param(self):
        dst_w, dst_h = self.model_input_size
        ratio = min(dst_w / self.rgb888p_size[0], dst_h / self.rgb888p_size[1])
        new_w = int(ratio * self.rgb888p_size[0])
        new_h = int(ratio * self.rgb888p_size[1])
        dw, dh = (dst_w - new_w) / 2, (dst_h - new_h) / 2
        return 0, int(round(dh * 2 + 0.1)), 0, int(round(dw * 2 - 0.1))


def init_uart2():
    """按 ATK-DNK230D 官方例程初始化 PH2.0 接口2。"""
    if not uart2_enable:
        return None
    try:
        fpioa = FPIOA()
        fpioa.set_function(uart2_tx_pin, FPIOA.UART2_TXD)
        fpioa.set_function(uart2_rx_pin, FPIOA.UART2_RXD)
        u2 = UART(UART.UART2, baudrate=uart2_baudrate,
                  bits=UART.EIGHTBITS, parity=UART.PARITY_NONE, stop=UART.STOPBITS_ONE)
        probe = "UART2_READY\r\n"
        probe_written = u2.write(probe)
        tx_pin = fpioa.get_pin_num(FPIOA.UART2_TXD)
        rx_pin = fpioa.get_pin_num(FPIOA.UART2_RXD)
        print("UART2 initialized: baudrate={} (IO{}=TX, IO{}=RX)".format(
            uart2_baudrate, tx_pin, rx_pin))
        print("UART2 startup probe: {}/{} bytes".format(probe_written, len(probe)))
        return u2
    except Exception as exc:
        print("UART2 init failed, fallback to REPL serial only: {}".format(exc))
        return None


def init_wireless_image():
    """初始化龙邱图传模块SPI链路（模式3，IO2握手）。"""
    if not wireless_image_enable:
        return None
    try:
        fpioa = FPIOA()
        fpioa.set_function(wireless_image_cs_pin, FPIOA.GPIO19)
        fpioa.set_function(wireless_image_clk_pin, FPIOA.QSPI0_CLK)
        fpioa.set_function(wireless_image_mosi_pin, FPIOA.QSPI0_D0)
        fpioa.set_function(wireless_image_miso_pin, FPIOA.QSPI0_D1)
        fpioa.set_function(wireless_image_ready_pin, FPIOA.GPIO18)

        cs = Pin(wireless_image_cs_pin, Pin.OUT, pull=Pin.PULL_NONE, drive=15)
        # 官方龙邱例程将 IO2 配置为浮空输入；模块主动输出握手电平。
        # 使用内部下拉可能使 IO2 无法可靠读到就绪高电平。
        ready = Pin(wireless_image_ready_pin, Pin.IN, pull=Pin.PULL_NONE)
        cs.value(1)
        spi = SPI(1, baudrate=wireless_image_spi_baudrate,
                  polarity=1, phase=0, bits=8)
        print("Wireless image SPI initialized: CS={}, CLK={}, MOSI={}, MISO={}, IO2={}".format(
            wireless_image_cs_pin, wireless_image_clk_pin,
            wireless_image_mosi_pin, wireless_image_miso_pin,
            wireless_image_ready_pin))
        print("Wireless image IO2 initial level: {}".format(ready.value()))
        return spi, cs, ready
    except Exception as exc:
        print("Wireless image SPI init failed: {}".format(exc))
        return None


def wait_pin_level(pin, target, timeout_us=20000):
    """以50 us轮询握手线，超时返回False。"""
    elapsed = 0
    while pin.value() != target:
        if elapsed >= timeout_us:
            return False
        sleep_us(50)
        elapsed += 50
    return True


def send_wireless_chunk(spi, cs, ready, data):
    """遵循模块IO2握手发送一个不超过4000字节的分块。"""
    wait_pin_level(ready, 1, 500)
    cs.value(0)
    try:
        spi.write(data)
    finally:
        cs.value(1)
    wait_pin_level(ready, 0, 500)
    # 官方例程的结束握手等待是无返回值的：即使未观察到低电平，
    # 也继续发送下一块。模块的低脉冲可能在 spi.write() 返回前结束，
    # Python 轮询因此可能只看到已经恢复的高电平。
    wait_pin_level(ready, 0, 500)
    return True


def send_wireless_image(spi, cs, ready, img):
    """发送龙邱协议的188x120灰度原始图像。"""
    pixel_count = wireless_image_width * wireless_image_height
    frame = bytearray(pixel_count + 8)
    frame[0:4] = b"\xA0\xFF\xFF\xA0"

    index = 4
    if hasattr(img, "to_grayscale"):
        gray = img.to_grayscale(copy=True)
        src_w = gray.width()
        src_h = gray.height()
        for row in range(wireless_image_height):
            src_y = row * src_h // wireless_image_height
            for col in range(wireless_image_width):
                src_x = col * src_w // wireless_image_width
                frame[index] = gray.get_pixel(src_x, src_y)
                index += 1
        del gray
    else:
        # PipeLine.get_frame() returns an RGB888P NCHW ndarray.
        shape = img.shape
        if len(shape) == 4:
            src_h = shape[2]
            src_w = shape[3]
            for row in range(wireless_image_height):
                src_y = row * src_h // wireless_image_height
                for col in range(wireless_image_width):
                    src_x = col * src_w // wireless_image_width
                    r = int(img[0, 0, src_y, src_x])
                    g = int(img[0, 1, src_y, src_x])
                    b = int(img[0, 2, src_y, src_x])
                    frame[index] = (77 * r + 150 * g + 29 * b) >> 8
                    index += 1
        elif len(shape) == 3:
            src_h = shape[1]
            src_w = shape[2]
            for row in range(wireless_image_height):
                src_y = row * src_h // wireless_image_height
                for col in range(wireless_image_width):
                    src_x = col * src_w // wireless_image_width
                    r = int(img[0, src_y, src_x])
                    g = int(img[1, src_y, src_x])
                    b = int(img[2, src_y, src_x])
                    frame[index] = (77 * r + 150 * g + 29 * b) >> 8
                    index += 1
        else:
            raise ValueError("unsupported camera ndarray shape: {}".format(shape))

    frame[index:index + 4] = b"\xB0\xB0\x0A\x0D"

    # This module/K230 wiring combination samples the SPI stream one bit late:
    # received[i] = previous_tx_lsb << 7 | tx[i] >> 1.
    # Pre-shift the complete stream and add one sacrificial sync byte so the
    # receiver reconstructs frame[] exactly, including its four-byte header.
    total = len(frame)
    wire = bytearray(total + 1)
    wire[0] = 0x01
    for i in range(total):
        next_byte = frame[i + 1] if i + 1 < total else frame[0]
        wire[i + 1] = ((frame[i] << 1) & 0xFE) | (next_byte >> 7)

    offset = 0
    wire_total = len(wire)
    while offset < wire_total:
        end = min(offset + 4000, wire_total)
        if not send_wireless_chunk(spi, cs, ready, wire[offset:end]):
            return False
        offset = end
    return True


def run():
    # ------------------------------------------------------------------ #
    #  初始化摄像头 & PipeLine（参考正点原子官方例程）
    # ------------------------------------------------------------------ #
    sensor, sensor_id = find_sensor()
    pl = PipeLine(
        rgb888p_size=rgb888p_size,
        display_size=display_size,
        display_mode=display_mode,
        gray_size=[wireless_image_width, wireless_image_height]
                  if wireless_image_enable else None,
        gray_channel=wireless_image_sensor_channel
    )
    pl.create(sensor=sensor)
    print("Using camera CSI{}".format(sensor_id))

    wireless_sensor = sensor if wireless_image_enable else None

    # media/sensor 完成后，再按官方顺序映射 FPIOA 并创建 UART 对象。
    uart2 = init_uart2_link(uart2_baudrate, uart2_tx_pin, uart2_rx_pin)
    uart_sender = PriorityUartSender(uart2)
    wireless_image = None
    if wireless_image_enable:
        try:
            wireless_image = AsyncWirelessImageSender(
                width=wireless_image_width,
                height=wireless_image_height,
                baudrate=wireless_image_spi_baudrate,
                cs_pin=wireless_image_cs_pin,
                clk_pin=wireless_image_clk_pin,
                mosi_pin=wireless_image_mosi_pin,
                miso_pin=wireless_image_miso_pin,
                ready_pin=wireless_image_ready_pin,
                spi_phase=wireless_image_spi_phase,
                compensate_bit_shift=wireless_image_compensate_bit_shift,
                sensor=wireless_sensor,
                sensor_channel=wireless_image_sensor_channel,
                sensor_lock=pl.snapshot_lock,
                image_format=wireless_image_format,
                jpeg_quality=wireless_image_jpeg_quality
            )
        except Exception as exc:
            print("Wireless image SPI init failed: {}".format(exc))

    def serial_send(msg):
        """同时输出到 REPL/调试串口和 UART2（如果已启用）。"""
        # UART2 remains full-rate; REPL output is throttled independently.
        echo = (serial_log_interval > 0 and
                frame_count % serial_log_interval == 0)
        uart_sender.submit(msg)
        if echo:
            print(msg)

    yolo_det = YOLOv12App(kmodel_path, model_input_size, anchors,
                          rgb888p_size, display_size, debug_mode)
    yolo_det.config_preprocess()

    print("=" * 50)
    print("K230D 钢球检测启动")
    print("显示模式:", display_mode)
    print("检测阈值: conf={}, nms={}".format(confidence_threshold, nms_threshold))
    print("=" * 50)

    frame_count = 0
    try:
        while True:
            frame_count += 1
            os.exitpoint()
            with ScopedTiming("total", 0):
                img = pl.get_frame()
                res = yolo_det.run(img)
                if (wireless_image is not None and
                        frame_count % wireless_image_interval == 0):
                    try:
                        wireless_image.submit(img)
                    except Exception as exc:
                        print("Wireless image send failed: {}".format(exc))
                # 每帧推理；屏幕刷新与串口数据输出使用独立节拍。
                output_frame = frame_count % display_interval == 0
                output_serial = frame_count % serial_interval == 0
                if output_frame:
                    yolo_det.draw_result(pl, res)
                    pl.show_image()

                # ------ 串口输出钢珠检测结果 ------ #
                if len(res) > 0 and output_serial:
                    # 结果已按置信度排序，只输出最可信钢球，减少串口阻塞。
                    x, y, w, h, cls_id, score = res[0][:6]
                    position_cm = yolo_det.x_to_position_cm(x)
                    serial_send("BALL_POS_CM:{:.2f}".format(position_cm))

                    if verbose_serial:
                        print("=== Frame {} | 检测到 {} 个钢珠 ===".format(frame_count, len(res)))
                        # 图像坐标系（模型输入空间）中的中心坐标和宽高
                        cx_img = round(x, 1)
                        cy_img = round(y, 1)
                        w_img = round(w, 1)
                        h_img = round(h, 1)
                        # 换算到显示坐标系
                        cx_disp = int(x * display_size[0] // rgb888p_size[0])
                        cy_disp = int(y * display_size[1] // rgb888p_size[1])
                        print("  Ball#0: center=({}, {})  size=({}x{})  conf={:.3f}".format(
                            cx_img, cy_img, w_img, h_img, score
                        ))
                        print("          display=({}, {})  confidence={:.3f}".format(
                            cx_disp, cy_disp, score
                        ))
                elif output_serial:
                    serial_send("BALL_POS_CM:NA")
                    if verbose_serial:
                        print("=== Frame {} | 未检测到钢珠 ===".format(frame_count))

                if frame_count % 60 == 0:
                    gc.collect()
    except Exception as e:
        print("Error:", e)
    finally:
        yolo_det.deinit()
        uart_sender.deinit()
        if wireless_image is not None:
            wireless_image.deinit()
        pl.destroy()
        deinit_uart(uart2)
        print("钢球检测已停止")
