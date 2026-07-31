"""K230 摄像头实时预览工具。

只将摄像头画面输出到显示屏和 CanMV IDE，
视频录制与保存由 IDE 完成。
"""

from imports.PipeLine import PipeLine
from imports.config import (
    camera_sensor_id,
    display_mode,
    display_size,
    rgb888p_size,
    sensor_height,
    sensor_width,
)
from media.sensor import Sensor
from time import sleep_ms
import os


def create_sensor():
    """按项目配置创建摄像头。"""
    print("Initializing camera on CSI{}...".format(camera_sensor_id))
    return Sensor(
        id=camera_sensor_id,
        width=sensor_width,
        height=sensor_height,
    )


def main():
    """启动摄像头并持续输出实时画面。"""
    sensor = create_sensor()
    pipeline = PipeLine(
        rgb888p_size=rgb888p_size,
        display_size=display_size,
        display_mode=display_mode,
    )

    try:
        pipeline.create(sensor=sensor)
        print("Camera preview started on CSI{}".format(camera_sensor_id))
        print("Use CanMV IDE to record and save the video.")

        # 视频通道由硬件持续输出，主循环只需保持程序运行。
        while True:
            os.exitpoint()
            sleep_ms(20)
    except KeyboardInterrupt:
        print("Preview stopped by user.")
    finally:
        pipeline.destroy()
        print("Camera preview closed.")


if __name__ == "__main__":
    main()
