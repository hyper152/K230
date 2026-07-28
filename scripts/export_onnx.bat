@echo off
REM YOLO PyTorch → ONNX 导出脚本
REM 用法: scripts\export_onnx.bat

set WEIGHTS=..\train\yolov11m2\weights\best.pt
set IMSZ=320

echo Exporting %WEIGHTS% to ONNX (imgsz=%IMSZ%) ...
call conda run -n cv python -m ultralytics export model=%WEIGHTS% format=onnx imgsz=%IMSZ% simplify=True

echo Done.
pause
