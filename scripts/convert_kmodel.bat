@echo off
REM ONNX to K230 kmodel conversion script
REM Usage: cd scripts && convert_kmodel.bat

REM nncase needs .NET hostfxr path
set "DOTNET_ROOT=%USERPROFILE%\.dotnet"
set "PATH=%USERPROFILE%\.dotnet;%PATH%"

set MODEL=..\train\yolov11m2\weights\best.onnx
set DATASET=..\dataset\steelball\images\train
set WIDTH=320
set HEIGHT=320
set PTQ=0

echo [1/3] ONNX Simplify + Compile to kmodel ...
echo   Model:   %MODEL%
echo   Dataset: %DATASET%
echo   Size:    %WIDTH%x%HEIGHT%
echo   PTQ:     %PTQ%
echo.

call C:\environment\anaconda\Scripts\conda.exe run -n cv python test_yolo11\detect\to_kmodel.py ^
    --target k230 ^
    --model %MODEL% ^
    --dataset %DATASET% ^
    --input_width %WIDTH% ^
    --input_height %HEIGHT% ^
    --ptq_option %PTQ%

echo.
if exist ..\train\yolov11m2\weights\best.kmodel (
    echo [2/3] kmodel generated:
    dir ..\train\yolov11m2\weights\best.kmodel
    echo.
    echo [3/3] Copy best.kmodel to K230 /sdcard/ to deploy.
) else (
    echo [ERROR] kmodel not found, check logs above.
)

pause
