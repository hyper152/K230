# K230 钢球检测

基于 YOLO11m 的钢球（steel ball）检测项目，部署到嘉楠 K230 开发板运行。

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
    ├── config.py                   # 推理参数配置
    ├── export_onnx.bat             # pt → onnx 导出
    └── convert_kmodel.bat          # onnx → kmodel 转换（预留）
```

## 推理 — K230 开发板

将 `train/yolov11m2/weights/best.kmodel` 拷贝到 K230 的 `/sdcard/` 目录下，
然后在 K230 上运行：

```bash
cd /sdcard
python scripts/run.py
```

## ONNX 导出

在 PC 上执行：

```bash
cd scripts
export_onnx.bat
```

需要 conda 环境 `cv`（ultralytics + onnxruntime）。
