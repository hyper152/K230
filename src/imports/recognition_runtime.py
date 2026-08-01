"""Camera/model runtime, display scheduling and Port2 result output."""

import os
import gc
from time import ticks_ms, ticks_diff
from .PipeLine import PipeLine
from .steel_ball_app import YOLOv12App, find_sensor
from .task_keys import TaskKeyController
from .config import *


def init_recognition(port2_media_ready=None):
    """初始化摄像头、模型和按键，返回由 main.py 持有的状态。"""
    try:
        os.stat(kmodel_path)
    except Exception:
        raise RuntimeError("Model file not found: {}".format(kmodel_path))

    sensor = find_sensor()
    pipeline = PipeLine(
        rgb888p_size=rgb888p_size,
        display_size=display_size,
        display_mode=display_mode,
    )
    detector = None
    try:
        pipeline.create(sensor=sensor)
        if port2_media_ready is not None:
            port2_media_ready()

        detector = YOLOv12App(
            kmodel_path, model_input_size, anchors,
            rgb888p_size, display_size, debug_mode,
        )
        detector.config_preprocess()
    except Exception:
        try:
            if detector is not None:
                detector.deinit()
        finally:
            pipeline.destroy()
        raise
    return {
        "pl": pipeline,
        "yolo": detector,
        "keys": TaskKeyController(),
        "task_type": default_task_type,
        "frame_count": 0,
        "last_ready_ms": ticks_ms(),
    }


def recognize_once(state):
    """获取一帧图像并执行一次钢球识别。"""
    state["frame_count"] += 1
    return state["yolo"].run(state["pl"].get_frame())


def display_result(state, result):
    """按照配置周期刷新 OSD。"""
    frame_count = state["frame_count"]
    if display_interval > 0 and frame_count % display_interval == 0:
        state["yolo"].draw_result(
            state["pl"], result, state["task_type"]
        )
        state["pl"].show_image()


def read_task_key(state):
    """返回 None 或 (K键序号, 点击次数)。"""
    return state["keys"].poll(ticks_ms())


def set_task_type(state, task_type):
    """保存 main.py 判断出的任务编号。"""
    state["task_type"] = task_type


def output_result(state, result, port2_send):
    """输出 READY、任务编号和钢球位置。"""
    now_ms = ticks_ms()
    if (uart2_ready_interval_ms > 0 and
            ticks_diff(now_ms, state["last_ready_ms"]) >= uart2_ready_interval_ms):
        port2_send("UART2_READY")
        port2_send("TASK_TYPE:{}".format(state["task_type"]))
        state["last_ready_ms"] = now_ms

    frame_count = state["frame_count"]
    if serial_interval > 1 and frame_count % serial_interval != 0:
        return
    if result:
        position_cm = state["yolo"].x_to_position_cm(result[0][0])
        port2_send("BALL_POS_CM:{:.2f}".format(position_cm))
    else:
        port2_send("BALL_POS_CM:NA")


def maintain_runtime(state):
    """处理退出点并定期回收内存。"""
    os.exitpoint()
    if state["frame_count"] > 0 and state["frame_count"] % 60 == 0:
        gc.collect()


def deinit_recognition(state):
    """释放模型和媒体资源。"""
    try:
        state["yolo"].deinit()
    finally:
        state["pl"].destroy()
