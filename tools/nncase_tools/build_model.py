"""一键将 Ultralytics best.pt 导出为 ONNX，并编译为 K230 KModel。

填写下方配置后直接运行：
py build_model.py

参数配置清单：
| 参数 | 值 | 说明 |
|------|----|------|
| 模型 | YOLOv8n (3M 参数量) | K230 兼容、nncase 可转 |
| 输出尺寸 | 320×320 | K230 RTOS ~33ms/帧，Linux SDK ~58ms/帧 |
| 输出格式 | 标准 detect 头 | 非 u 变体，nncase 兼容 |
| 最终目标 | imgsz: 320 | 训练-推理尺寸一致，量化不掉精度 |
| ONNX 导出 | opset=11, fixed [1,3,320,320], half=False | nncase v2.11 兼容 |
| nncase 量化 | uint8, 20+ 校准图 | 标准 PTQ 量化路径 |
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


# ======================== 在这里填写路径 ======================== #

# 待转换的 PyTorch 模型路径（YOLOv8n，3M 参数量）
MODEL_PATH = r"C:\Users\23615\Desktop\.hyper\embedded\2026电赛TI杯\k230\weights\yolov8n\2\best.pt"

# PTQ 校准图片目录（至少放入 20 张图片）
CALIBRATION_IMAGE_DIR = r"C:\Users\23615\Desktop\.hyper\PC\CV\data\img\steelball\images"

# 模型输入尺寸，必须是 32 的倍数
IMAGE_SIZE = 320

# Conda 可执行文件；本机已确认该路径存在
CONDA_EXE_PATH = r"C:\.environment\anaconda\Scripts\conda.exe"

# =============================================================== #

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}
DEFAULT_SAMPLE_COUNT = 20


def run(command: list[str], cwd: Path) -> None:
    print("\n>", subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, cwd=str(cwd), check=True)


def find_conda() -> str | None:
    """返回真实的 conda 可执行文件，而不是 PowerShell 中的 conda 函数。"""
    if CONDA_EXE_PATH and Path(CONDA_EXE_PATH).is_file():
        return CONDA_EXE_PATH
    for env_name in ("CONDA_EXE", "_CONDA_EXE"):
        conda = os.environ.get(env_name)
        if conda and Path(conda).is_file():
            return conda
    return shutil.which("conda") or shutil.which("conda.exe")


def python_command(env_name: str, conda: str | None) -> list[str]:
    """当前 Conda 环境直接用当前 Python，否则通过 conda run 调用。"""
    current_env = os.environ.get("CONDA_DEFAULT_ENV", "")
    conda_prefix = os.environ.get("CONDA_PREFIX", "")
    executable = Path(sys.executable).resolve()
    interpreter_is_in_conda = False
    if conda_prefix:
        try:
            executable.relative_to(Path(conda_prefix).resolve())
            interpreter_is_in_conda = True
        except ValueError:
            pass

    if current_env.lower() == env_name.lower() and interpreter_is_in_conda:
        return [sys.executable]
    if conda is None:
        raise FileNotFoundError(
            "找不到 conda 可执行文件。请先执行 conda activate {} 后再运行脚本。".format(
                env_name
            )
        )
    return [conda, "run", "-n", env_name, "python"]


def main() -> int:
    tool_dir = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(
        description="best.pt -> best.onnx -> best.kmodel（K230，PTQ 量化）"
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(CALIBRATION_IMAGE_DIR),
        help="覆盖代码开头设置的校准图片目录",
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=Path(MODEL_PATH),
        help="覆盖代码开头设置的 .pt 模型路径",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=IMAGE_SIZE,
        help="覆盖代码开头设置的模型输入尺寸",
    )
    parser.add_argument(
        "--export-env",
        default="Vision",
        help="安装了 ultralytics 的 Conda 环境",
    )
    parser.add_argument(
        "--nncase-env",
        default="base",
        help="安装了 nncase/nncase-kpu 的 Conda 环境",
    )
    args = parser.parse_args()

    model = args.model.expanduser().resolve()
    dataset = args.dataset.expanduser().resolve()

    conda = find_conda()
    if not model.is_file() or model.suffix.lower() != ".pt":
        parser.error("模型文件不存在或不是 .pt 文件：{}".format(model))
    if not dataset.is_dir():
        parser.error("校准图片目录不存在：{}".format(dataset))
    if args.imgsz <= 0 or args.imgsz % 32 != 0:
        parser.error("--imgsz 必须是正数且为 32 的倍数")

    images = sorted(
        path
        for path in dataset.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )
    if len(images) < DEFAULT_SAMPLE_COUNT:
        parser.error(
            "校准图片不足：找到 {} 张，至少需要 {} 张".format(
                len(images), DEFAULT_SAMPLE_COUNT
            )
        )

    onnx_file = model.with_suffix(".onnx")
    kmodel_file = model.with_suffix(".kmodel")

    print("模型：{}".format(model))
    print("校准集：{}（{} 张图片）".format(dataset, len(images)))
    print("输入尺寸：{}x{}".format(args.imgsz, args.imgsz))

    # ONNX 导出：opset=11, 固定输入 [1,3,320,320], half=False（nncase v2.11 兼容）
    export_code = (
        "from ultralytics import YOLO; "
        "YOLO({!r}).export(format='onnx', imgsz={}, simplify=True, "
        "dynamic=False, batch=1, opset=11, half=False)".format(
            str(model), args.imgsz
        )
    )
    run(python_command(args.export_env, conda) + ["-c", export_code], tool_dir)
    if not onnx_file.is_file():
        raise FileNotFoundError("ONNX 导出完成，但未找到输出文件：{}".format(onnx_file))

    run(
        python_command(args.nncase_env, conda)
        + [
            str(tool_dir / "to_kmodel.py"),
            "--target",
            "k230",
            "--model",
            str(onnx_file),
            "--dataset",
            str(dataset),
            "--input_width",
            str(args.imgsz),
            "--input_height",
            str(args.imgsz),
            "--ptq_option",
            "0",
        ],
        tool_dir,
    )
    if not kmodel_file.is_file():
        raise FileNotFoundError("nncase 编译完成，但未找到输出文件：{}".format(kmodel_file))

    print("\n生成成功：")
    print("  ONNX  : {}".format(onnx_file))
    print("  KModel: {}".format(kmodel_file))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print("\n转换失败，子进程退出码：{}".format(exc.returncode), file=sys.stderr)
        raise SystemExit(exc.returncode)
