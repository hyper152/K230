# K230D BOX 钢球检测

基于 YOLO11m 的钢球（steel ball）检测项目，部署到 **正点原子 K230D BOX** 开发板运行。

## 硬件介绍

本项目的目标硬件为 **正点原子 K230D BOX** 开发板，基于嘉楠 K230D 芯片。

| 项目 | 链接 |
|------|------|
| 🛒 购买链接 | [正点原子官方旗舰店](https://detail.tmall.com/item.htm?id=863144196152) |
| 🎬 综合例程演示 | [B站视频：BV1JxA8eEEQd](https://www.bilibili.com/video/BV1JxA8eEEQd) |
| 📦 资料下载（A盘） | [百度网盘](https://pan.baidu.com/s/1pcs17VI43a8GhWz7YMzF_Q) 提取码：`4y7m` |

## 目录结构

```
k230/
├── README.md                       # 本文件
├── dataset/                        # 数据集
│   └── steelball/
│       ├── images/{train,test,val}/
│       └── labels/{train,test,val}/
├── train/                          # 训练产出
│   └── yolov11m2/
│       ├── weights/                # 模型权重
│       │   ├── best.pt             # PyTorch 权重
│       │   ├── best.onnx           # ONNX 导出
│       │   └── last.pt             # 最后 epoch 权重
│       ├── results.csv             # 训练日志
│       └── plots/                  # 训练曲线 / 混淆矩阵
└── scripts/                        # 工具脚本 & 部署代码
    ├── run.py                      # K230 推理主程序
    ├── run.md                      # K230 运行指南（部署、调参、排错）
    ├── config.py                   # 推理参数配置
    ├── export_onnx.bat             # pt → onnx 导出
    ├── convert_kmodel.bat          # onnx → kmodel 转换
    └── test_yolo11/detect/         # 官方转换工具（nncase 脚本）
```

## 完整部署流程

### 1️⃣ 环境准备（仅首次）

在 conda 环境 `cv` 中安装转换工具：

```bash
conda activate cv

:: 安装 nncase 转换工具链
pip install nncase==2.11.0

:: 下载并安装 nncase-kpu（版本必须一致）
:: 下载地址: https://github.com/kendryte/nncase/releases
pip install nncase_kpu-2.11.0-py2.py3-none-win_amd64.whl

:: 安装 .NET 7.0 SDK（nncase 依赖）
:: 下载: https://dotnet.microsoft.com/download/dotnet/7.0
:: 安装后验证: dotnet --version  →  7.0.x
```

### 2️⃣ pt → ONNX 导出

```bash
cd scripts
export_onnx.bat
```

输出: `train/yolov11m2/weights/best.onnx`

### 3️⃣ ONNX → kmodel 转换

```bash
cd scripts
convert_kmodel.bat
```

转换过程：
1. ONNX Simplify（优化算子）
2. 加载校准图片进行 PTQ 量化（从训练集中取 20 张）
3. 编译生成 `best.kmodel`

**ptq_option 说明：**

| 选项 | 量化方式 | 说明 |
|------|----------|------|
| 0 | NoClip + uint8/uint8 | ✅ 推荐，精度与速度平衡 |
| 1 | NoClip + int16/uint8 | 权重 int16，精度更高 |
| 2 | NoClip + uint8/int16 | 激活 int16 |
| 3 | Kld + uint8/uint8 | KLD 校准方法 |
| 4 | Kld + int16/uint8 | |
| 5 | Kld + uint8/int16 | |

### 4️⃣ 部署到 K230D BOX

将 TF 卡插入电脑，复制部署文件：

```bash
:: 将 kmodel 复制到 TF 卡
copy train\yolov11m2\weights\best.kmodel J:\sdcard\
copy scripts\run.py J:\sdcard\
copy scripts\config.py J:\sdcard\
```

将 TF 卡插入 K230D BOX，通过串口（115200 波特率）连接终端：

```bash
# 在串口终端执行
cd /sdcard
python run.py
```

> 串口连接方式详见 [run.md](scripts/run.md) 和 [串口使用指南](#串口使用指南)。

## 推理说明

推理脚本 `scripts/run.py` 在 K230D BOX 上使用 nncase runtime 运行，通过 PipeLine 获取摄像头画面，经 AI2D 预处理后推理，输出钢球检测框并通过 OSD 叠加显示。

关键参数在 `config.py` 中配置：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `display_mode` | `lcd` | 显示模式 (`"lcd"` 或 `"hdmi"`) |
| `rgb888p_size` | `[1280, 720]` | 采集分辨率 |
| `display_size` | `[800, 480]` | 显示分辨率 |
| `model_input_size` | `[320, 320]` | 模型输入尺寸 |
| `confidence_threshold` | `0.50` | 检测置信度阈值 |
| `nms_threshold` | `0.35` | NMS 阈值 |
| `max_miss_count` | `4` | 连续漏检容忍帧数 |
| `smooth_alpha` | `0.65` | 检测框位置平滑系数 |

## 常见问题

### Q: nncase 报 "Failed to get hostfxr path"
缺少 .NET 7.0 SDK。安装后重启终端。

### Q: onnx 转 kmodel 报 NAN
onnx 版本过高，降级到 1.15.0 或 1.16.1：
```bash
pip install onnx==1.15.0 onnxruntime==1.19.0
```

### Q: 找不到 nncase_kpu
Windows 不能在线安装，需手动下载 whl：
- 官方 Release: https://github.com/kendryte/nncase/releases
- 版本号必须与 nncase 一致（如 2.11.0）

## 串口使用指南

K230D BOX 通过 Type-C 线连接到电脑，同时实现供电和串口通信。

### Windows 连接步骤

1. **安装驱动**（CH340 芯片）：连接开发板后，设备管理器出现 `USB-SERIAL CH340 (COMx)`
2. **串口参数**：波特率 **115200**，8 数据位，1 停止位，无校验
3. **推荐工具**：MobaXterm（Session → Serial）或 PuTTY
4. **登录**：连接后按 Enter，出现 MicroPython REPL 提示符 `>>>`

### 运行推理

```bash
cd /sdcard
python run.py
```

### 退出程序

按 `Ctrl+C` 终止推理，返回 REPL。

### 常见串口问题

| 问题 | 解决 |
|------|------|
| 串口无输出 | 检查 USB 线是否插到 UART 口（非 OTG 口），按 RST 键复位 |
| 输出乱码 | 检查波特率是否为 **115200** |
| 无法输入 | 复位后等待启动完成，再按 Enter |
