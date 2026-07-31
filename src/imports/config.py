"""K230 钢球检测应用配置。"""

# ==================== 显示与摄像头 ====================
display_mode = "lcd"             # 显示输出模式：lcd 表示板载液晶屏
rgb888p_size = [320, 320]        # AI 推理通道图像尺寸：[宽, 高]，单位为像素
display_size = [640, 480]        # 显示画面尺寸：[宽, 高]，单位为像素
display_interval = 2             # 画面刷新间隔：每 2 个推理帧刷新一次
sensor_width = 1280              # 摄像头传感器输入宽度，单位为像素
sensor_height = 720              # 摄像头传感器输入高度，单位为像素
camera_sensor_id = 2             # 摄像头所在的 CSI 接口编号

# ==================== 位置输出 ====================
serial_interval = 1              # 位置数据发送间隔：每 1 个推理帧发送一次
serial_log_interval = 20         # IDE 串口日志间隔：每 20 帧打印一次，不影响 UART2 发送频率
verbose_serial = False           # 是否在 IDE 输出详细的检测与位置调试信息
uart2_enable = True              # 是否启用 UART2 位置数据输出
uart2_baudrate = 115200          # UART2 波特率，单位为 bit/s
uart2_tx_pin = 44                # UART2 发送引脚，对应 IO44
uart2_rx_pin = 45                # UART2 接收引脚，对应 IO45
uart2_ready_interval_ms = 1000   # UART2_READY 就绪消息的周期发送间隔，单位为毫秒

# ==================== 龙邱无线图传模块 ====================
# 当前 CanMV 固件中，SPI(1) 图传与已验证的 UART2 Port2 通道冲突。
# 使用 Port2 输出钢球位置时，应保持图传功能关闭。
wireless_image_enable = False              # 是否启用龙邱无线图传
wireless_image_interval = 1                # 图像提交间隔：每 1 个推理帧提交一次
wireless_image_width = 192                 # 图传图像宽度，单位为像素
wireless_image_height = 120                # 图传图像高度，单位为像素
wireless_image_sensor_channel = 1          # 图传使用的摄像头通道编号
wireless_image_format = "jpeg"            # 图传图像编码格式
wireless_image_jpeg_quality = 45           # JPEG 压缩质量，数值越大画质越高且数据量越大
wireless_image_spi_baudrate = 10_000_000   # 图传 SPI 通信速率，单位为 bit/s
wireless_image_spi_phase = 1               # SPI 时钟相位配置，取值为 0 或 1
wireless_image_compensate_bit_shift = False  # 是否启用 SPI 数据位偏移补偿
wireless_image_cs_pin = 19                 # 图传 SPI 片选引脚，对应 IO19
wireless_image_clk_pin = 15                # 图传 SPI 时钟引脚，对应 IO15
wireless_image_mosi_pin = 16               # 图传 SPI 主机输出引脚，对应 IO16
wireless_image_miso_pin = 17               # 图传 SPI 主机输入引脚，对应 IO17
wireless_image_ready_pin = 18              # 图传模块就绪握手引脚，对应 IO18

# ==================== 模型 ====================
kmodel_path = "/sdcard/best.kmodel"       # K230 推理模型在 TF 卡中的绝对路径
model_input_size = [320, 320]              # 模型输入图像尺寸：[宽, 高]，单位为像素
anchors = None                             # 锚框配置；None 表示当前无锚框模型不使用预设锚框

# ==================== 检测与跟踪 ====================
confidence_threshold = 0.50     # 最终显示和输出检测结果的置信度阈值
nms_threshold = 0.35            # 非极大值抑制的交并比阈值，用于去除重叠检测框
detect_threshold = 0.50         # 模型候选结果的初步置信度筛选阈值
max_miss_count = 4              # 目标暂时丢失时允许保持上一次结果的最大帧数
smooth_alpha = 0.65             # 位置平滑系数；越大越偏向当前检测值，响应越快
track_length_cm = 25.0          # 实际轨道长度，单位为厘米，用于将像素坐标换算为物理位置
position_calibration_min_cm = 3.0   # 原始位置的 4 cm 标定为输出位置 0 cm
position_calibration_max_cm = 19.5  # 原始位置的 20 cm 标定为输出位置 25 cm

# ==================== 调试诊断 ====================
debug_mode = 0                  # 调试输出级别；0 表示关闭详细性能计时信息
