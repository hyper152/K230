# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

K230D BOX 钢球检测项目 — 基于 YOLO 的钢球（steel ball）检测，部署到 **正点原子 K230D BOX** 开发板（嘉楠 K230D 芯片）上运行。

**完整流程：** PC 端训练 YOLO → 导出 ONNX（imgsz=320）→ nncase PTQ 量化编译 kmodel → 复制到 TF 卡 → K230D 端 MicroPython + nncase runtime 推理。

## Project Structure

```
k230/
├── dataset/steelball/           # YOLO 格式数据集（单类别: steel_ball）
│   ├── images/{train,test,val}/ # .jpg + .json 配套文件
│   └── labels/{train,test,val}/ # .txt (cls xc yc w h 归一化)
├── weights/                     # 模型权重（训练产出）
│   ├── yolov8/best.pt           # YOLOv8 权重
│   ├── yolov11m2/weights/       # YOLO11m 训练产出 (pt/onnx/kmodel)
│   └── ...
├── scripts/
│   ├── run.py                   # K230D 推理主程序
│   ├── config.py                # 推理参数配置
│   ├── export_onnx.bat          # pt → onnx 导出
│   ├── convert_kmodel.bat       # onnx → kmodel 转换
│   └── nncase_tools/            # nncase 转换 & 验证脚本
│       ├── to_kmodel.py         # onnx → kmodel 编译（PTQ 量化）
│       ├── simulate.py          # kmodel 离线模拟（对比 ONNX cosine similarity）
│       └── save_bin.py          # 保存 ONNX/kmodel 输入 bin 文件
└── resources/                   # 开发板资料（DNK230D LVGL 示例）
```

## Environment

转换环境在 **conda base**（`C:\.environment\anaconda`），nncase 为 user-site 安装：

```bash
# nncase 工具链（版本必须匹配）
pip install nncase==2.11.0
pip install /path/to/nncase_kpu-2.11.0-py2.py3-none-win_amd64.whl    # GitHub Releases 下载
# 依赖 .NET 7+ SDK（nncase 编译需要）
```

**训练环境**（若有训练需求）：conda `Vision` 环境，ultralytics 8.4.27。

**注意：** `to_kmodel.py` 中 `generate_data()` 函数会过滤图片扩展名（`.jpg/.jpeg/.png/.bmp`），忽略目录中的 `.json` 等非图片文件。

## Conversion Pipeline

### pt → ONNX（PC 端）
```bash
cd scripts
conda run -n Vision python -c "from ultralytics import YOLO; YOLO('../weights/yolov8/best.pt').export(format='onnx', imgsz=320, simplify=True)"
```

或用 `export_onnx.bat`（需修改 `WEIGHTS` 路径）。

### ONNX → kmodel（PC 端）
```bash
cd scripts
conda run -n base python nncase_tools/to_kmodel.py \
    --target k230 \
    --model ../weights/yolov8/best.onnx \
    --dataset ../dataset/steelball/images/train \
    --input_width 320 --input_height 320 \
    --ptq_option 0
```

### ptq_option

| 选项 | 量化方式 | 说明 |
|------|----------|------|
| 0 | NoClip + uint8/uint8 | ✅ 推荐，精度与速度平衡 |
| 1 | NoClip + int16/uint8 | 权重 int16，精度更高 |
| 3 | Kld + uint8/uint8 | KLD 校准方法 |

### 部署到 K230D
```bash
# 复制到 TF 卡，插入开发板
cp weights/yolov8/best.kmodel /sdcard/
cp scripts/run.py /sdcard/
cp scripts/config.py /sdcard/
# 串口终端执行（115200 8N1）
cd /sdcard && python run.py
```

## Inference Architecture (`run.py`)

**`YOLOv12App`** 类继承 `AIBase`，核心流程：

1. **初始化**：加载 kmodel，配置 AI2D 预处理（padding + resize）
2. **预处理**（`config_preprocess`）：等比例缩放 + padding 到模型输入尺寸，用 `[104, 117, 123]` 填充
3. **推理**：`super().run()` → nncase runtime 执行
4. **后处理**（`postprocess`）：直接读取 `output[4, i]` 置信度（单类别模型），边界框按 `scale_x/scale_y` 缩放回采集分辨率 → NMS → 时序滤波
5. **关键特性**：
   - **时序平滑**（`temporal_filter`）：`max_miss_count`（默认4）帧漏检容忍 + `smooth_alpha`（默认0.65）位置指数平滑
   - **显示同步**：`display_interval`（默认2）控制显示和串口输出的刷新节拍
   - **OSD 绘制**：`draw_result()` 在显示层叠加检测框和计数

### Config 参数 (`config.py`)

| 参数 | 默认 | 说明 |
|------|------|------|
| `display_mode` | `lcd` | `lcd` / `hdmi` |
| `rgb888p_size` | `[640, 360]` | 采集分辨率（实际会对齐 16px） |
| `display_size` | `[800, 480]` | 显示分辨率 |
| `model_input_size` | `[320, 320]` | 模型输入尺寸 |
| `confidence_threshold` | 0.50 | 检测置信度阈值 |
| `nms_threshold` | 0.35 | NMS IoU 阈值 |
| `display_interval` | 2 | 显示刷新帧间隔 |
| `max_miss_count` | 4 | 连续漏检容忍帧数 |
| `smooth_alpha` | 0.65 | 位置平滑系数（0.4~0.8） |

## Dataset

- 单类别：`steel_ball`
- YOLO 标注格式：`cls x_center y_center width height`（归一化到 [0, 1]）
- `images/` 下每张 `.jpg` 带一个 `.json` 配套文件（标注工具产物，推理时忽略）
- 划分：`train/` 444 张, `test/` 和 `val/` 各若干

## Verification Scripts

PC 端可用 `nncase.Simulator` 离线验证 kmodel 精度：

```bash
# 1. 准备输入数据
conda run -n base python nncase_tools/save_bin.py --image test.jpg --save_path . --input_width 320 --input_height 320

# 2. 模拟推理并对比 ONNX 结果的 cosine similarity
conda run -n base python nncase_tools/simulate.py --model best.onnx --model_input onnx_input_float32.bin --kmodel best.kmodel --kmodel_input kmodel_input_uint8.bin --input_width 320 --input_height 320
```

## Board Info

- **硬件：** 正点原子 K230D BOX（嘉楠 K230D 芯片）
- **串口：** CH340, 115200 8N1, Type-C UART 口
- **数据：** TF 卡启动，`/sdcard/` 挂载点
- **LCD 背光：** GPIO pin 5，高电平有效（`run.py` 中初始化）
