# prompt.x7peeps.com

提示词样本册：把真实产线里「一条提示词 → 它真的出来了什么」的配对公开出来。
每条样本保留模型、尺寸、种子与完整提示词原文，点开可整段复制。

## 内容来源（全部真实产物，无编造）

| 类型 | 来源 | 数量 |
|---|---|---|
| 图像 | 壁纸产线 `~/.hermes/artifacts/xhs-account/wallpapers/batch13–17`（MiniMax H3-Image，3072×5472） | 12 |
| 图像 | 短剧实验室 `~/Projects/h3-drama-lab` 图槽资产（H3-Image，v2 全身版） | 3 |
| 视频 | 4090 ComfyUI · H3 Ref2VA（1344×768 / 52 帧） | 3 |

## 目录

```
index.html            单文件站点（内联样式与脚本，无构建步骤）
data/samples.json     样本数据（由 scripts/build_data.py 生成）
assets/img/           图像详情图（最长边 1600）与缩略图（720）
assets/video/         视频（h264 crf26 + faststart）
assets/poster/        视频封面（自动取最亮的一帧）
scripts/build_data.py 从产线目录抽取 prompt ↔ 产出，生成数据与转码资产
scripts/probe.py      真实渲染取证：多档视口截图 + 几何/溢出/资源/交互断言
scripts/serve.py      本地预览（no-store，HTTP/1.1）
```

## 新增一条样本

1. 在 `scripts/build_data.py` 里加一条映射（标题、导读、note、来源），或直接改 `data/samples.json`；
2. 资产走 `sips` / `ffmpeg` 生成缩略图与封面；
3. 跑 `python3 scripts/build_data.py`；
4. 跑 `python3 scripts/probe.py`，`PROBLEMS` 必须为空；
5. 部署：push 到 main，GitHub Pages 自动发布。

## 纪律

- **提示词与产出必须严格对应**。2026-11-17 首版曾从 4090 的 history 挑了 12 条视频，逐帧核对发现多条的文件内容与记录的 prompt 错位（个别输出文件被覆盖重复），最终只保留 3 条画面与提示词能一一对上的。
  判据：抽末帧看画面里的人物/兵器/动作，与 prompt 的「起始状态 / 动作 / 结束状态」三段逐项对上，对不上就不上。
- 参数原文不改写。中文提示词就是中文原文，英文就是英文原文。
- 视频封面用「最亮的一帧」而不是首帧：H3 Ref2VA 的首帧常是静止准备姿态，全黑镜头会毁掉封面。

## 本地预览

```bash
python3 scripts/serve.py 8931
# http://127.0.0.1:8931/
```
