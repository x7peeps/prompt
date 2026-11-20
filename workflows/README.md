# ComfyUI Desktop (4090, 端口 8190) — 统一出图入口

老大 2026-11-21 定：「4090 已有 comfyui desktop 你要用起来，另一个秋叶的暂定以后要废除（更新麻烦）」，并要求「把其他版本的 comfyui 都合并到这个版本，模型择优保留」+「每次出图检查是否有可以复用的工作流」。

## 三个实例的最终状态

| 端口 | 版本 | 角色 | 状态 |
|---|---|---|---|
| **8190** | ComfyUI Desktop standalone v0.45.3 (py3.13.12) | **唯一主力出图入口** | ✅ 已跑通 Qwen-Image / H3-Image |
| 8189 | 源码版 0.45.0 (H3Image) | H3 视频 ref2va 专用 | 保留（出图能力已并入 8190，节点零缺失） |
| 8188 | 秋叶整合包 0.19.3 | **已停用（2026-11-21）**，暂定以后废除 | ⛔ 进程已停，目录保留 |

## Desktop 的关键配置（2026-11-21 完成）

- **模型挂载**：`ComfyUI\extra_model_paths.yaml` → 同时挂 3 个库：
  - `D:\ComfyUI-official\models`（123GB 主库）
  - `D:\ComfyUI-H3Image\models`（38GB H3 专用）
  - `D:\ComfyUI\models`（58GB 秋叶库）
- **模型清单（清理后）**：3 checkpoints / 8 diffusion_models / 10 vae / 5 clip，含 H3-Image、Qwen-Image fp8、Wan2.1/2.2、FLUX 文本编码器（t5xxl fp8、umt5 fp8）
- **custom_nodes 已并入**：从秋叶那套复制了 ComfyUI-H3-Multishot、ComfyUI_MiniMaxH3_Director、ComfyUI-GGUF、ComfyUI-Manager、ComfyUI-MiniMaxH3DualClockSampler
- **节点数**：1124（8189 = 1059 全部覆盖，0 缺失；秋叶独有 29 个是云端 API 节点，需 API key，不属于本地能力）
- **gguf 包**：装在 `ComfyUI\.venv\Lib\site-packages\gguf`（从秋叶的 Python311 用户目录复制）

## Desktop 启动（离线可用）

`D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\start_desktop_backend.bat`

```
@echo off
cd /d "D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI"
set HF_HUB_OFFLINE=1
set COMFYUI_DISABLE_MANAGER=1
".venv\Scripts\python.exe" main.py --listen 0.0.0.0 --port 8190 --disable-manager --disable-metadata --disable-auto-launch > user\comfyui_8190.log 2>&1
```

注意：`--disable-manager` 是必须的。4090 连不上 `raw.githubusercontent.com`，ComfyUI-Manager 启动时会拉 5 个缓存 JSON 各 120 秒超时，把整个后端拖死（前端 503）。

## 每次出图的标准流程

1. **先查可复用工作流**：`python3 scripts/workflows.py list` → `show <id>` → `check <id>`（查目标机模型是否就位）
2. **有合适的** → 直接跑：`python3 scripts/workflows.py run <id> --prompt "..." --seed N`
3. **没有的** → 新建 workflow JSON 放进 `workflows/`，跑通后在 `catalog.json` 登记
4. **跑通的工作流 JSON 同步到 4090**：`ComfyUI\user\default\workflows\prompt-site\`（Desktop UI 里可直接调出）

## 已验证工作流（2026-11-21 实测）

| ID | 模型 | 用途 | 实测 |
|---|---|---|---|
| `qwen-image-txt2img-8190` | Qwen-Image fp8 (19GB) | 中文文字渲染准确的文生图 | 1024×1024，约 4 分钟 |
| `h3-image-txt2img-8190` | H3-Image w4a8 (11.7GB) | 等高线/肌理/大图直出（最大 16.8MP） | 3072×4608，32 秒 |
| `contour-split-poster-8190` | 同上 | 上下对半·等高线海报（老大原创提示词） | 已入站 contour 段 |

## 已知坑（2026-11-21 踩过）

1. **Desktop 后端启动被 Manager 拖死**：4090 连不上 `raw.githubusercontent.com`，Manager 拉 5 个缓存 JSON 各 120s 超时 → 前端 503。解法 = `--disable-manager`。
2. **`CLIPLoader` 的 `type` 在 0.45.x 里叫 `minimax`，不是 `minimax_h3`**（两版列表一致，别想当然）。
3. **H3 的 KSampler 不需要 EmptyLatentImage**：`MiniMaxH3ImageConditioning` 输出 slot 1 就是 latent（`["4", 1]`），没有 slot 会 400 required_input_missing。
4. **venv 隔离**：Desktop 的 Python 3.13 venv 不吃秋叶 Python311 用户目录的包，`pip install --user` 装的包它看不到，必须 `pip install --target <venv site-packages>`。
5. **Windows 防火墙**：Desktop 的 `standalone-env\python.exe` 被一条 Block 规则挡过；`.venv\Scripts\python.exe` 走了 `python.exe` Allow 规则才通。
