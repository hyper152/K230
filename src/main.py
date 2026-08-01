"""K230 application entry: orchestration only."""

# 识别、显示、按键读取和运行状态管理函数全部放在 imports 中。
from imports.init import (
    show_no_sensor_screen,
    init_recognition,
    recognize_once,
    display_result,
    read_task_key,
    set_task_type,
    output_result,
    maintain_runtime,
    deinit_recognition,
)
# Port2 的初始化、媒体启动后重映射、发送和释放函数。
from imports.port2_link import (
    init_port2,
    remap_port2_after_media,
    send_port2,
    print_port2_debug,
    deinit_port2,
)
from imports.data_logger import init_data_log, close_data_log


# 必须先初始化 Port2，确保摄像头/媒体模块启动前 UART2 已创建。
init_port2()
init_data_log()
runtime = None

try:
    # 初始化摄像头、AI 模型、OSD 和三个任务按键。
    # 媒体模块启动后调用 remap_port2_after_media，恢复 IO44/IO45 的 UART2 复用。
    try:
        runtime = init_recognition(port2_media_ready=remap_port2_after_media)
    except RuntimeError as error:
        if "sensor" not in str(error).lower():
            raise
        print("[CAMERA ERROR]", repr(error))
        show_no_sensor_screen(
            port2_send=send_port2,
            service_callback=print_port2_debug,
        )

    while True:
        # 处理系统退出点，并每 60 帧进行一次垃圾回收。
        maintain_runtime(runtime)
        print_port2_debug()

        # read_task_key 返回 None，或返回 (key_index, click_count)：
        # key_index：K0/K1/K2 分别为 0/1/2；click_count：单击为 1，双击为 2。
        task_event = read_task_key(runtime)
        if task_event is not None:
            key_index, click_count = task_event

            # 单击映射：K0->任务1，K1->任务2，K2->任务3，并立即发送启动事件。
            if click_count == 1:
                set_task_type(runtime, key_index + 1)

            # 双击映射：K0->任务4，K1->任务5，K2->任务6。
            else:
                set_task_type(runtime, key_index + 4)

        # 获取一帧摄像头图像并执行钢球识别。
        detections = recognize_once(runtime)

        # 按 display_interval 配置刷新检测框、位置和底部刻度。
        display_result(runtime, detections)

        # 通过 Port2 输出钢球位置；与 READY 同周期输出当前任务类型。
        output_result(runtime, detections, send_port2)
finally:
    # 无论正常退出还是发生异常，都按顺序释放 AI/媒体资源和 UART2。
    try:
        if runtime is not None:
            deinit_recognition(runtime)
    finally:
        try:
            deinit_port2()
        finally:
            close_data_log()
