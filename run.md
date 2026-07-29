# K230 钢球检测 — 运行指南

## 模型转换（PT → ONNX → kmodel）

### 1️⃣ PT → ONNX

在 PC 上导出：

```bash
cd scripts
export_onnx.bat
```

或手动执行：

```bash
conda activate cv
yolo export model=train/yolov11m2/weights/best.pt format=onnx imgsz=320 simplify=True
```

输出: `train/yolov11m2/weights/best.onnx`

### 2️⃣ ONNX → kmodel

#### 环境要求

| 组件 | 说明 |
|------|------|
| .NET 7.0 SDK | nncase 依赖，安装后设 `DOTNET_ROOT` |
| nncase==2.11.0 | `pip install nncase==2.11.0` |
| nncase-kpu==2.11.0 | 从 GitHub Release 下载 whl 安装 |

#### 执行转换

```bash
cd scripts
./convert_kmodel.bat
```

脚本流程：
1. ONNX Simplify — 优化算子、简化图结构
2. PTQ 量化校准 — 从训练集中取 20 张图片做 int8 量化
3. 编译生成 `best.kmodel`

**ptq_option 可选：**

| 选项 | 方法 | 适用场景 |
|------|------|----------|
| 0 ✅ | NoClip + uint8/uint8 | 推荐，速度和精度平衡 |
| 1 | NoClip + int16/uint8 | 权重更高精度 |
| 2 | NoClip + uint8/int16 | 激活更高精度 |
| 3 | Kld + uint8/uint8 | 分布校准 |
| 4~5 | Kld + int16 | 更高精度但更慢 |

输出: `train/yolov11m2/weights/best.kmodel`

---

## 硬件准备

- 嘉楠 K230 开发板（CanMV K230 / 亚博K230等）
- 摄像头（支持 OV5645 或 GC2093 等）
- LCD 显示屏或 HDMI 显示器
- TF 卡（至少 512MB）

## 部署文件

将以下文件复制到 K230 的 TF 卡 `/sdcard/` 目录：

| 文件 | 来源 | 说明 |
|------|------|------|
| `best.kmodel` | `train/yolov11m2/weights/best.kmodel` | 量化后的模型 |
| `run.py` | `scripts/run.py` | 主推理脚本 |
| `config.py` | `scripts/config.py` | 配置文件 |

```
/sdcard/
├── best.kmodel
├── run.py
└── config.py
```

## 参数配置

编辑 `config.py` 调整参数（**在复制到 TF 卡前修改**）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `display_mode` | `"lcd"` | `"lcd"` 或 `"hdmi"` |
| `rgb888p_size` | `[1280, 720]` | 采集分辨率 |
| `display_size` | `[800, 480]` | 显示分辨率 |
| `kmodel_path` | `"/sdcard/best.kmodel"` | kmodel 在板子上的路径 |
| `confidence_threshold` | `0.50` | 置信度阈值 |
| `nms_threshold` | `0.35` | NMS 阈值 |
| `max_miss_count` | `4` | 漏检容忍帧数 |
| `smooth_alpha` | `0.65` | 位置平滑系数 |

### 调参技巧

- **误检多** → 提高 `confidence_threshold`（0.60 ~ 0.70）
- **漏检多** → 降低 `confidence_threshold`（0.30 ~ 0.45）
- **框抖动** → 降低 `smooth_alpha`（0.4 ~ 0.5）
- **框拖尾** → 降低 `max_miss_count`（2 ~ 3）

## 运行

在 K230 终端执行：

```bash
# 进入 SD 卡目录
cd /sdcard

# 运行推理
python run.py
```

### 预期效果

- LCD/HDMI 实时显示摄像头画面
- 左上角显示 `balls: N`（当前检测到的钢球数量）
- 钢球用紫色框标出，带标签和置信度
- 画面流畅无卡顿

### 退出

- 按 Ctrl+C 终止程序

## 常见问题

### 找不到 kmodel

```
OSError: open kmodel file error
```

检查 `config.py` 中的 `kmodel_path` 路径，确保 `best.kmodel` 在对应位置。

### 摄像头无画面

- 检查摄像头排线是否插紧
- 尝试更换 `rgb888p_size` 为 `[640, 480]`
- 确认摄像头型号是否被 K230 支持

### 运行报错 no module named 'libs'

推理脚本必须在 K230 板子上运行，不能直接在 PC 上执行。
`libs` 是 K230 固件自带的 nncase runtime 库。

### 检测效果差

- 检查光线是否充足
- 重新导出 ONNX 时确认 `imgsz` 与训练一致
- 尝试不同的 `ptq_option`（0~5）重新量化

### 画面卡顿

- 降低 `rgb888p_size`（如 `[640, 480]`）
- 检查 TF 卡读写速度
