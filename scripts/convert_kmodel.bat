@echo off
REM ONNX → K230 kmodel 转换脚本（需安装 nncase 工具链）
REM 用法: scripts\convert_kmodel.bat

set ONNX_PATH=..\train\yolov11m2\weights\best.onnx
set KMODEL_PATH=..\train\yolov11m2\weights\best.kmodel

echo Converting %ONNX_PATH% to kmodel ...
echo TODO: 请使用 nncase 的 ncc 工具:
echo   ncc compile %ONNX_PATH% %KMODEL_PATH% -i onnx -o kmodel
echo.
echo 转换完成后将 best.kmodel 拷贝到 K230 开发板的 /sdcard/ 目录下。
pause
