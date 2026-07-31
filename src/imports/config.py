"""Configuration for the K230 steel-ball detector application."""

# Display and camera
display_mode = "lcd"
rgb888p_size = [320, 320]
display_size = [640, 480]
display_interval = 2
sensor_width = 1280
sensor_height = 720
camera_sensor_id = 2

# Position output
serial_interval = 1
verbose_serial = False
uart2_enable = True
uart2_baudrate = 115200
uart2_tx_pin = 44
uart2_rx_pin = 45

# LongQiu wireless image module
wireless_image_enable = True
wireless_image_interval = 2
wireless_image_width = 188
wireless_image_height = 120
wireless_image_spi_baudrate = 2_000_000
wireless_image_cs_pin = 19
wireless_image_clk_pin = 15
wireless_image_mosi_pin = 16
wireless_image_miso_pin = 17
wireless_image_ready_pin = 18

# Model
kmodel_path = "/sdcard/best.kmodel"
model_input_size = [320, 320]
anchors = None

# Detection and tracking
confidence_threshold = 0.75
nms_threshold = 0.35
detect_threshold = 0.75
max_miss_count = 4
smooth_alpha = 0.65
track_length_cm = 25.0

# Diagnostics
debug_mode = 0
