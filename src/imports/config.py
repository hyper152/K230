"""K230 钢球检测应用配置。"""

# ==================== 显示与摄像头 ====================
display_mode = "lcd"             # 显示输出模式：lcd 表示板载液晶屏
rgb888p_size = [320, 320]        # AI 推理通道图像尺寸：[宽, 高]，单位为像素
display_size = [640, 480]        # 显示画面尺寸：[宽, 高]，单位为像素
display_interval = 2             # 开启 OSD，每 2 个推理帧绘制并刷新一次
sensor_width = 1280              # 摄像头传感器输入宽度，单位为像素
sensor_height = 720              # 摄像头传感器输入高度，单位为像素
sensor_fps = 60                  # 以传感器支持的 60 FPS 模式供给 AI 通道
camera_sensor_id = 2             # 摄像头所在的 CSI 接口编号

# ==================== 位置输出 ====================
serial_interval = 1              # 位置数据发送间隔：每 1 个推理帧发送一次
uart2_baudrate = 115200          # UART2 波特率，保持与接收端通信协议一致
uart2_tx_pin = 44                # UART2 发送引脚，对应 IO44
uart2_rx_pin = 45                # UART2 接收引脚，对应 IO45
uart2_ready_interval_ms = 1000   # UART2_READY 就绪消息的周期发送间隔，单位为毫秒

# ==================== 任务选择按键 ====================
default_task_type = 1            # 上电默认任务
key0_pin = 34                    # K0：单击任务1，双击任务4，低电平有效
key1_pin = 35                    # K1：单击任务2，双击任务5，低电平有效
key2_pin = 0                     # K2：单击任务3，双击任务6，高电平有效
key_debounce_ms = 30             # 按键消抖时间
key_double_click_ms = 350        # 双击最大间隔；单击会在此时间后确认

# ==================== 模型 ====================
kmodel_path = "/sdcard/best.kmodel"       # K230 推理模型在 TF 卡中的绝对路径
model_input_size = [320, 320]              # 模型输入图像尺寸：[宽, 高]，单位为像素
anchors = None                             # 锚框配置；None 表示当前无锚框模型不使用预设锚框

# ==================== 检测与跟踪 ====================
confidence_threshold = 0.40    # 最终显示和输出检测结果的置信度阈值
nms_threshold = 0.35            # 非极大值抑制的交并比阈值，用于去除重叠检测框
detect_threshold = 0.40         # 模型候选结果的初步置信度筛选阈值
max_miss_count = 4              # 目标暂时丢失时允许保持上一次结果的最大帧数
smooth_alpha = 0.65             # 位置平滑系数；越大越偏向当前检测值，响应越快
track_length_cm = 25.0          # 实际轨道长度，单位为厘米，用于将像素坐标换算为物理位置
position_calibration_min_cm = 4.69   # 新 0 cm 对应调整前刻度 1 cm 的位置
position_calibration_max_cm = 21.48  # 新 25 cm 对应旧刻度外推 28 cm 的位置

# ==================== 调试诊断 ====================
debug_mode = 0                  # 调试输出级别；0 表示关闭详细性能计时信息
