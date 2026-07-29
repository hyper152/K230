"""K230 钢球检测 — 部署参数配置"""

# 显示模式: "lcd" 或 "hdmi"
display_mode = "lcd"

# 摄像头采集分辨率
rgb888p_size = [640, 360]

# 显示分辨率
display_size = [800, 480]

# kmodel 路径（K230 设备上的路径）
kmodel_path = "/sdcard/best.kmodel"

# 模型输入尺寸
model_input_size = [320, 320]

# 检测阈值
confidence_threshold = 0.50
nms_threshold = 0.35

# 锚点（None 表示使用模型默认锚点）
anchors = None

# 每帧都做推理；显示和终端输出按相同频率同步刷新。
display_interval = 2

# 时序平滑参数
max_miss_count = 4        # 连续漏检最大帧数
smooth_alpha = 0.65       # 位置平滑系数
