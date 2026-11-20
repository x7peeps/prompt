@echo off
REM DRY-RUN: 只列出待删项，不删任何东西
setlocal enabledelayedexpansion
set LOG=D:\Comfy-Desktop\consolidate-dryrun-20261121.log
echo ==== dry-run %date% %time% ==== > %LOG%

REM --- A. 下载残骸 (.sN / .pN / .BAK) ---
for %%D in (D:\ComfyUI-official\models D:\ComfyUI\models D:\ComfyUI-H3Image\models) do (
  for /r %%D %%F in (*) do (
    set "FN=%%~nxF"
    set "FULL=%%F"
    echo "!FN!" | findstr /r /c:"^\..*\.s[0-7]$" >nul && echo SHARD_S ^| !FULL! >> %LOG%
    echo "!FN!" | findstr /r /c:"^\..*\.p[0-7]$" >nul && echo SHARD_P ^| !FULL! >> %LOG%
    echo "!FN!" | findstr /r /c:"\.BAK$" >nul && echo BAK ^| !FULL! >> %LOG%
  )
)

REM --- B. 跨库同名 ---
echo DUP_umt5_H3Image ^| D:\ComfyUI-H3Image\models\text_encoders\umt5_xxl_fp8_e4m3fn_scaled.safetensors >> %LOG%
echo DUP_umt5_legacy ^| D:\ComfyUI\models\text_encoders\umt5_xxl_fp8_e4m3fn_scaled.safetensors >> %LOG%
echo DUP_curve_unet ^| D:\ComfyUI-official\models\unet\minimax_h3_curve_Q8_0.gguf >> %LOG%
echo ==== end ==== >> %LOG%
