"""K230 数据集采集工具

从摄像头捕获图像并保存到 TF 卡，用于构建 YOLO 训练数据集。
显示屏显示实时画面，串口接收按键指令。

依赖 K230 nncase runtime / MicroPython 环境，在开发板上运行。
"""

from libs.PipeLine import PipeLine
import os, sys
from media.media import *
from media.sensor import *
from media.display import *
from time import *
import select
import image

from config import *

# ========== 采集参数 ==========
SAVE_DIR = "/sdcard/dataset_capture"       # 图片保存目录
IMAGE_QUALITY = 95                          # JPEG 保存质量 (0-100)

# 传感器分辨率（与 main.py 一致）
sensor_width = 1280
sensor_height = 720


def find_sensor():
    """扫描 CSI0~CSI2，返回第一个可用的摄像头对象和编号。"""
    errors = []
    for sensor_id in range(3):
        try:
            print("Scanning camera on CSI{}...".format(sensor_id))
            sensor = Sensor(id=sensor_id, width=sensor_width, height=sensor_height)
            print("Camera found on CSI{}".format(sensor_id))
            return sensor, sensor_id
        except Exception as exc:
            errors.append("CSI{}: {}".format(sensor_id, exc))
            print("No camera on CSI{}: {}".format(sensor_id, exc))

    raise RuntimeError("No camera found on CSI0~CSI2; " + "; ".join(errors))


def capture_frame(img, save_dir, seq):
    """保存当前帧为 JPEG，返回文件路径。"""
    timestamp = time()
    filename = "img_{:.0f}_{:04d}.jpg".format(timestamp, seq)
    filepath = os.path.join(save_dir, filename)
    img.save(filepath, quality=IMAGE_QUALITY)
    return filepath


if __name__ == "__main__":
    # 初始化摄像头和显示
    sensor, sensor_id = find_sensor()
    pl = PipeLine(rgb888p_size=rgb888p_size, display_size=display_size, display_mode=display_mode)
    pl.create(sensor=sensor)
    print("Using camera CSI{}".format(sensor_id))

    # 创建保存目录
    os.makedirs(SAVE_DIR, exist_ok=True)
    print("Images will be saved to: {}".format(SAVE_DIR))

    seq = 0
    print("\n" + "=" * 40)
    print("  K230 数据集采集工具")
    print("  保存目录: {}".format(SAVE_DIR))
    print("  采集分辨率: {}x{}".format(rgb888p_size[0], rgb888p_size[1]))
    print("")
    print("  [c/空格]  捕获当前帧")
    print("  [q]       退出")
    print("=" * 40 + "\n")

    try:
        while True:
            os.exitpoint()
            img = pl.get_frame()

            # 显示实时画面 + 提示
            pl.osd_img.clear()
            pl.osd_img.draw_string_advanced(0, 0, 32,
                "Captured: {}  [c]apture  [q]uit".format(seq),
                color=(0, 255, 0, 0))
            pl.show_image()

            # 非阻塞检测串口按键
            try:
                if select.select([sys.stdin], [], [], 0)[0]:
                    key = sys.stdin.read(1).lower()
                    if key in ("c", " "):
                        seq += 1
                        path = capture_frame(img, SAVE_DIR, seq)
                        print("#{} saved: {}".format(seq, path))

                        # 画面闪一下提示
                        pl.osd_img.clear()
                        pl.osd_img.draw_string_advanced(
                            display_size[0] // 2 - 80,
                            display_size[1] // 2 - 16,
                            32, "Saved #{}".format(seq),
                            color=(0, 255, 0, 0))
                        pl.show_image()
                        sleep_ms(300)

                    elif key == "q":
                        print("Exit by user.")
                        break
            except Exception:
                # stdin 不可用时静默跳过
                pass

    except KeyboardInterrupt:
        print("\nStopped by user.")
    except Exception as e:
        print("Error:", e)
    finally:
        pl.destroy()
        print("Done. {} images saved to {}".format(seq, SAVE_DIR))
