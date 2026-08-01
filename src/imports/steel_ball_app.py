"""K230 steel-ball detection application.

依赖 K230 nncase runtime 环境，在 K230 开发板上运行。
"""

from .PipeLine import ScopedTiming
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from media.media import *
from media.sensor import *
from media.display import *
import nncase_runtime as nn
import ulab.numpy as np
import image
from .config import *

def find_sensor():
    """按照配置创建摄像头对象。"""
    sensor = Sensor(
        id=camera_sensor_id,
        width=sensor_width,
        height=sensor_height,
        fps=sensor_fps
    )
    return sensor


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
        """将钢球中心横坐标经两点标定后换算为 0～25 cm。"""
        image_width = self.rgb888p_size[0]
        if image_width <= 0:
            return 0.0

        # 先按画面宽度计算原始位置，再将原 4～20 cm 线性映射到 0～25 cm。
        raw_position_cm = float(x) * track_length_cm / image_width
        calibration_span_cm = (
            position_calibration_max_cm - position_calibration_min_cm
        )
        if calibration_span_cm <= 0:
            return 0.0

        position_cm = (
            (raw_position_cm - position_calibration_min_cm)
            * track_length_cm
            / calibration_span_cm
        )
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

    def draw_result(self, pl, dets, task_type):
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
            pl.osd_img.draw_string_advanced(
                0, 72, 32, "Task: {}".format(task_type),
                color=(255, 255, 255, 0)
            )

            # 屏幕底部刻度与 x_to_position_cm() 使用同一组标定参数。
            # 标尺端点分别对应输出位置 0 cm 和 track_length_cm。
            scale_y = self.display_size[1] - 10
            raw_start_x = (position_calibration_min_cm / track_length_cm
                           * self.rgb888p_size[0])
            raw_end_x = (position_calibration_max_cm / track_length_cm
                         * self.rgb888p_size[0])
            scale_start_x = int(raw_start_x * self.display_size[0]
                                / self.rgb888p_size[0])
            scale_end_x = int(raw_end_x * self.display_size[0]
                              / self.rgb888p_size[0])
            scale_width = scale_end_x - scale_start_x
            scale_color = (255, 255, 255, 255)

            if scale_width > 0:
                pl.osd_img.draw_rectangle(
                    scale_start_x, scale_y, scale_width, 2,
                    color=scale_color, fill=True
                )
                tick_cm = 0
                while tick_cm <= int(track_length_cm):
                    tick_x = scale_start_x + int(
                        tick_cm * scale_width / track_length_cm
                    )
                    tick_height = 12 if tick_cm % 5 == 0 else 6
                    pl.osd_img.draw_rectangle(
                        tick_x, scale_y - tick_height, 2, tick_height,
                        color=scale_color, fill=True
                    )
                    if tick_cm % 5 == 0:
                        label_x = max(0, min(self.display_size[0] - 36,
                                             tick_x - 10))
                        pl.osd_img.draw_string_advanced(
                            label_x, scale_y - 34, 20,
                            str(tick_cm), color=scale_color
                        )
                    tick_cm += 1

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
