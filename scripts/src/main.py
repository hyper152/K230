"""K230 钢球检测推理入口

依赖 K230 nncase runtime 环境，在 K230 开发板上运行。
"""

from libs.PipeLine import PipeLine, ScopedTiming
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
from machine import UART
from machine import FPIOA

from config import *

# ========== 所有参数统一在此定义（覆盖 config.py） ==========

# 显示
display_mode = "lcd"
rgb888p_size = [320, 320]
display_size = [640, 480]
display_interval = 2

# 串口与屏幕分开刷新：位置数据每帧输出，屏幕每 2 帧刷新
serial_interval = 1
verbose_serial = False

# UART2 硬件串口（IO44=UART2_TXD, IO45=UART2_RXD）
# 开：通过 UART2 把位置数据发给外部主控；关：仅走 REPL/调试串口
uart2_enable = True
uart2_baudrate = 115200

# 模型 IO
kmodel_path = "/sdcard/best.kmodel"
model_input_size = [320, 320]
anchors = None

# 检测阈值
confidence_threshold = 0.75
nms_threshold = 0.35
detect_threshold = 0.75

# 时序平滑
max_miss_count = 4
smooth_alpha = 0.65

# 钢球运动范围：画面最左端为 0 cm，最右端为 25 cm
track_length_cm = 25.0

# 调试
debug_mode = 0

# 传感器
sensor_width = 1280
sensor_height = 720


def find_sensor():
    """扫描 CSI0~CSI2，返回第一个可用的摄像头对象和编号。"""
    errors = []
    for sensor_id in range(3):
        try:
            print("Scanning camera on CSI{}...".format(sensor_id))
            sensor = Sensor(
                id=sensor_id,
                width=sensor_width,
                height=sensor_height
            )
            print("Camera found on CSI{}".format(sensor_id))
            return sensor, sensor_id
        except Exception as exc:
            errors.append("CSI{}: {}".format(sensor_id, exc))
            print("No camera on CSI{}: {}".format(sensor_id, exc))
            gc.collect()

    raise RuntimeError(
        "No camera found on CSI0~CSI2; " + "; ".join(errors)
    )


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
    """初始化 UART2 硬件串口（IO44=TX, IO45=RX）。

    必须在 pl.create() 之前调用，避免 media/sensor 启动时重配 FPIOA
    覆盖掉 UART2 的引脚分配。返回 UART 对象或 None。
    """
    if not uart2_enable:
        return None
    try:
        fpioa = FPIOA()
        fpioa.set_function(44, FPIOA.UART2_TXD)
        fpioa.set_function(45, FPIOA.UART2_RXD)
        u2 = UART(UART.UART2, baudrate=uart2_baudrate,
                  bits=UART.EIGHTBITS, parity=UART.PARITY_NONE, stop=UART.STOPBITS_ONE)
        # 自检：发送一条测试消息，方便确认 port2 是否真的有输出
        u2.write("UART2_OK\r\n")
        print("UART2 initialized: baudrate={} (IO44=TX, IO45=RX)".format(uart2_baudrate))
        return u2
    except Exception as exc:
        print("UART2 init failed, fallback to REPL serial only: {}".format(exc))
        return None


if __name__ == "__main__":
    # ------------------------------------------------------------------ #
    #  初始化 UART2（必须先于 pl.create，避免引脚被 media 重配）
    # ------------------------------------------------------------------ #
    uart2 = init_uart2()

    # ------------------------------------------------------------------ #
    #  初始化摄像头 & PipeLine（参考正点原子官方例程）
    # ------------------------------------------------------------------ #
    sensor, sensor_id = find_sensor()
    pl = PipeLine(rgb888p_size=rgb888p_size, display_size=display_size, display_mode=display_mode)
    pl.create(sensor=sensor)
    print("Using camera CSI{}".format(sensor_id))

    def serial_send(msg):
        """同时输出到 REPL/调试串口和 UART2（如果已启用）。"""
        if uart2 is not None:
            try:
                uart2.write(msg + "\r\n")
            except Exception:
                pass
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
        pl.destroy()
        if uart2 is not None:
            try:
                uart2.deinit()
            except Exception:
                pass
        print("钢球检测已停止")
