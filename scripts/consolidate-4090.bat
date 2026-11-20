@echo off
REM ============================================================
REM 4090 ComfyUI consolidation — 合并到 Desktop (8190)
REM 1) 清理下载残骸 (.s0-.s7 / .p0-.p7 / .BAK)
REM 2) 跨库同名重复：保留一份，删其余
REM 3) 生成清单报告
REM 幂等：可重复执行
REM ============================================================
setlocal enabledelayedexpansion
set LOG=D:\Comfy-Desktop\consolidate-20261121.log
echo ==== consolidate start %date% %time% ==== > %LOG%

REM ---------- 1) 下载残骸 ----------
set /a SHARDS=0
for /r D:\ComfyUI-official\models %%F in (*) do (
  set "FN=%%~nxF"
  echo "!FN!" | findstr /r /c:"^\..*\.s[0-7]$" >nul && (
    del /f /q "%%F" >> %LOG% 2>&1
    set /a SHARDS+=1
  )
  echo "!FN!" | findstr /r /c:"^\..*\.p[0-7]$" >nul && (
    del /f /q "%%F" >> %LOG% 2>&1
    set /a SHARDS+=1
  )
  echo "!FN!" | findstr /r /c:"\.BAK$" >nul && (
    del /f /q "%%F" >> %LOG% 2>&1
    set /a SHARDS+=1
  )
  echo "!FN!" | findstr /r /c:"^\.p[0-9]_.*\.p[0-7]$" >nul && (
    del /f /q "%%F" >> %LOG% 2>&1
    set /a SHARDS+=1
  )
)
echo shards_and_bak_removed=!SHARDS! >> %LOG%

REM ---------- 2) 跨库同名重复：保留 ComfyUI-official 优先，其次 H3Image，最后 ComfyUI ----------
echo ==== dedupe ==== >> %LOG%
for %%N in (umt5_xxl_fp8_e4m3fn_scaled.safetensors) do (
  if exist "D:\ComfyUI-official\models\text_encoders\%%N" (
    if exist "D:\ComfyUI-H3Image\models\text_encoders\%%N" del /f /q "D:\ComfyUI-H3Image\models\text_encoders\%%N" >> %LOG% 2>&1
    if exist "D:\ComfyUI\models\text_encoders\%%N" del /f /q "D:\ComfyUI\models\text_encoders\%%N" >> %LOG% 2>&1
    echo dedupe_umt5_kept_official >> %LOG%
  )
)
REM minimax_h3_curve_Q8_0.gguf: diffusion_models 与 unet 各一份，保留 diffusion_models
if exist "D:\ComfyUI-official\models\unet\minimax_h3_curve_Q8_0.gguf" (
  del /f /q "D:\ComfyUI-official\models\unet\minimax_h3_curve_Q8_0.gguf" >> %LOG% 2>&1
  echo dedupe_curve_kept_diffusion_models >> %LOG%
)
REM audio vae: codex-h3-20261002 与 codex-h3-lan-20261002 是不同版本，都留
REM ---------- 3) 清单 ----------
echo ==== final inventory ==== >> %LOG%
for /r D:\ComfyUI-official\models %%F in (*.safetensors) do echo official ^| %%~zF ^| %%~fF >> %LOG%
for /r D:\ComfyUI\models %%F in (*.safetensors) do echo legacy ^| %%~zF ^| %%~fF >> %LOG%
for /r D:\ComfyUI-H3Image\models %%F in (*.safetensors) do echo h3image ^| %%~zF ^| %%~fF >> %LOG%
echo ==== consolidate done %date% %time% ==== >> %LOG%
echo DONE >> %LOG%
