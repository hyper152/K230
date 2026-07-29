# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

K230D BOX 钢球检测项目 — 基于 YOLO11m 的钢球（steel ball）检测，部署到正点原子 K230D BOX 开发板（嘉楠 K230D 芯片）上运行。

**流程：** PC 端训练 YOLO → 导出 ONNX → nncase 量化编译为 kmodel → 复制到 TF 卡 → K230D 端用 MicroPython + nncase runtime 推理。

## Project Structure

```
k230/
├── dataset/steelball/       # YOLO 格式数据集 (images/ + labels/, 各含 train/test/val)
├── train/yolov11m2/         # 训练产出
│   ├── weights/             # best.pt / best.onnx / best.kmodel / last.pt
│   ├── results.csv          # 每个 epoch 的 loss / mAP / lr
│   ├── plots/               # 训练曲线、混淆矩阵、预测示例
│   └── args.yaml            # 训练超参数（imgsz=640, epochs=100, batch=-1）
├── scripts/
│   ├── run.py               # K230D 推理主程序（摄像头 → AI2D 预处理 → nncase 推理 → OSD 显示）
│   ├── config.py            # 推理参数（分辨率、阈值、平滑系数等）
│   ├── export_onnx.bat      # pt → onnx 导出（conda env: cv）
│   ├── convert_kmodel.bat   # onnx → kmodel 转换（调用 test_yolo11/detect/to_kmodel.py）
│   └── test_yolo11/detect/  # nncase 官方转换 & 测试脚本（to_kmodel.py, simulate.py 等）
└── README.md                # 项目说明、部署步骤、串口指南
```

## Key Architecture

### PC 端（训练 & 转换）
- **训练：** `yolo train model=yolo11m.pt data=ball.yaml` (Ultralytics YOLO, conda `cv` 环境)
- **导出：** `export_onnx.bat` → YOLO 导出 ONNX (imgsz=320, simplify=True)
- **转换：** `convert_kmodel.bat` → nncase PTQ 量化编译为 kmodel（--ptq_option 0~5，推荐 0）

### K230D BOX 端（推理）
- MicroPython 环境，通过串口（115200）交互
- `run.py` 使用 `libs.PipeLine`（摄像头）、`libs.AI2D`（预处理）、`nncase_runtime`（推理）、内置 `image` 模块（OSD 绘图）
- 检测结果带时序平滑（`temporal_filter`）+ 位置平滑（`smooth_alpha`），防止钢球抖动
- 输出通过 OSD 叠加在 LCD/HDMI 上，串口打印日志

## Common Commands

```bash
# 训练
conda activate cv
yolo train model=yolo11m.pt data=ball.yaml imgsz=640 epochs=100 batch=-1 project=results name=yolov11m2

# pt → ONNX 导出
cd scripts && export_onnx.bat

# ONNX → kmodel 转换
cd scripts && convert_kmodel.bat

# 部署到 K230D BOX
copy train\yolov11m2\weights\best.kmodel J:\sdcard\
copy scripts\run.py J:\sdcard\
copy scripts\config.py J:\sdcard\

# 在 K230D 串口终端执行
cd /sdcard && python run.py   # Ctrl+C 退出
```

## Dataset

- 钢球单类别检测（class_id = `steel_ball`）
- YOLO 标注格式：`cls x_center y_center width height`（归一化坐标）
- 数据集划分：`dataset/steelball/images|labels/{train,test,val}/`

## Tuning Parameters (config.py)

| 参数 | 范围 | 调参方向 |
|------|------|----------|
| `confidence_threshold` | 0.30~0.70 | 高→误检少，低→漏检少 |
| `nms_threshold` | 0.25~0.50 | 高→框合并少 |
| `smooth_alpha` | 0.4~0.8 | 低→更平滑，高→更跟手 |
| `max_miss_count` | 2~6 | 低→框消失快，高→框滞留久 |
| `ptq_option` | 0~5 | 0=速度和精度平衡，1/4=int16 权重更高精度 |

## Board Info

- **硬件：** 正点原子 K230D BOX（嘉楠 K230D 芯片）
- **串口：** CH340, 115200 8N1, Type-C UART 口
- **资料：** [百度网盘](https://pan.baidu.com/s/1pcs17VI43a8GhWz7YMzF_Q) 提取码 `4y7m`
- **购买：** [正点原子天猫店](https://detail.tmall.com/item.htm?id=863144196152)
