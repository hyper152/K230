"""Camera/model runtime, display scheduling and Port2 result output."""

import os
import gc
from time import ticks_ms, ticks_diff
from .PipeLine import PipeLine
from .steel_ball_app import YOLOv12App, find_sensor
from .task_keys import TaskKeyController
from .data_logger import log_vision
from .config import *


def show_no_sensor_screen(port2_send=None, service_callback=None):
    """Show a persistent LCD error instead of terminating without a camera."""
    from media.display import Display
    from media.media import MediaManager
    import image
    import time

    display_started = False
    media_started = False
    try:
        if display_mode in ("hdmi", "lt9611"):
            display_device = Display.LT9611
        else:
            display_device = Display.ST7701
        Display.init(
            display_device,
            width=display_size[0],
            height=display_size[1],
            osd_num=1,
            to_ide=True,
        )
        display_started = True
        MediaManager.init()
        media_started = True

        error_image = image.Image(
            Display.width(), Display.height(), image.ARGB8888
        )
        error_image.clear()
        error_image.draw_string_advanced(
            max(0, Display.width() // 2 - 150),
            max(0, Display.height() // 2 - 55),
            56,
            "NO SENSOR",
            color=(255, 255, 0, 0),
        )
        error_image.draw_string_advanced(
            max(0, Display.width() // 2 - 155),
            Display.height() // 2 + 25,
            24,
            "Check camera and CSI cable",
            color=(255, 255, 255, 255),
        )
        Display.show_image(error_image, 0, 0, Display.LAYER_OSD3)
        print("[CAMERA] NO SENSOR")

        last_na_ms = time.ticks_ms()
        while True:
            os.exitpoint()
            if service_callback is not None:
                service_callback()
            now_ms = time.ticks_ms()
            if (port2_send is not None
                    and time.ticks_diff(now_ms, last_na_ms) >= 500):
                port2_send("BALL_POS_CM:NA")
                last_na_ms = now_ms
            time.sleep_ms(20)
    finally:
        if display_started:
            try:
                Display.deinit()
            except Exception:
                pass
        if media_started:
            try:
                MediaManager.deinit()
            except Exception:
                pass


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
        "pending_task_start": 0,
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
    """保存任务编号，并安排一次可靠的任务启动事件。"""
    state["task_type"] = task_type
    state["pending_task_start"] = task_type


def output_result(state, result, port2_send):
    """输出 READY、任务编号和钢球位置。"""
    now_ms = ticks_ms()
    log_vision(state["frame_count"], result, state["yolo"])
    pending_task = state["pending_task_start"]
    if pending_task:
        # 三行在同一次循环连续发出。STM32在一次Update中只产生一个事件，
        # 因而既能抵抗偶发丢字节，也不会把状态机重复启动三次。
        for _ in range(task_command_repeat_count):
            port2_send("TASK_START:{}".format(pending_task))
        state["pending_task_start"] = 0

    if (uart2_ready_interval_ms > 0 and
            ticks_diff(now_ms, state["last_ready_ms"]) >= uart2_ready_interval_ms):
        port2_send("UART2_READY")
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
