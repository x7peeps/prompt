#!/usr/bin/env python3
"""从本机真实产线抽取 prompt ↔ 产出配对，生成 prompt.x7peeps.com 的数据与静态资产。

数据源（全部真实产物，不编造）：
  1. 壁纸产线 batch13/14/15/17：prompts/*.txt + base/*.png（H3-Image 3072×5472）+ gen.log 里的 seed
  2. h3-drama-lab 图槽资产：assets/生图词.json + assets/*.png
  3. 4090 ComfyUI /history：H3 ref2va 视频 1344×768 + 中文动作提示词
"""
import json, os, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WALL = Path.home() / ".hermes/artifacts/xhs-account/wallpapers"
DRAMA = Path.home() / "Projects/h3-drama-lab"
IMG = ROOT / "assets/img"
VID = ROOT / "assets/video"
PST = ROOT / "assets/poster"
for d in (IMG, VID, PST):
    d.mkdir(parents=True, exist_ok=True)

HOST = "192.168.3.7:8189"


def run(cmd, **kw):
    return subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, **kw)


def sips_resize(src, dst, max_edge, quality=82):
    if dst.exists() and dst.stat().st_mtime > Path(src).stat().st_mtime:
        return dst
    r = run(["sips", "-Z", str(max_edge), "-s", "format", "jpeg",
             "-s", "formatOptions", str(quality), str(src), "--out", str(dst)])
    if r.returncode != 0 or not dst.exists():
        print("SIPS FAIL", src, r.stderr[:200], file=sys.stderr)
        return None
    return dst


def dims(p):
    r = run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(p)])
    w = re.search(r"pixelWidth:\s*(\d+)", r.stdout)
    h = re.search(r"pixelHeight:\s*(\d+)", r.stdout)
    return (int(w.group(1)), int(h.group(1))) if w and h else (None, None)


# ── 1. 壁纸：标题、导读、note 为人工撰写（依据提示词原文），其余字段从文件读 ──
WALL_META = {
    # slug: (批次, 中文标题, 一句导读, note)
    "birch": ("13", "秋桦与冰川缆车", "金黄桦林前，一道钢索穿过冰川",
              "提示词把画面切成下 / 中 / 上三段分别描述：近处是落叶与岩面纹理，中景是桦林与缆索，远景才是冰川。三段各自给了材质和光位，模型因此不会把远处当主体放大。"),
    "glacier": ("13", "冰川裂隙蓝", "冰壁的蓝不是滤镜，是深度差",
                "关键写法是给冰的每层深度指定色温：表层偏白、裂隙内偏青、冰下透出深蓝。颜色随深度变化，冰的体积感才出得来。"),
    "cable": ("13", "雪线之上的索道", "钢索、塔架、雾凇，一条线切开山谷",
              "画面里只有一条人造直线（缆索），其余全是自然曲线。提示词反复强调「the cable stays a single straight line」，避免模型把索道画成扭曲的绳索。"),
    "cliff": ("14", "海边月升断崖", "低机位，浪在脚下碎成白沫",
              "低机位是靠「camera at knee height, horizon in the upper third」两句一起锁的；只写 low angle，模型经常把地平线放中间。"),
    "lotus": ("14", "荷塘月色", "花瓣边缘的一圈冷光",
                "荷花的难点是花瓣半透。提示词用「backlit petal edges glowing」而不是「translucent」，因为后者会让模型把整朵处理成玻璃质感。"),
    "moonpath": ("14", "月光铺在海面", "一条光路，从地平线走到沙滩",
                 "水面反光的写法：不说「反光」，说「a broken column of moonlight reaching the shore」，给的是形状而不是效果，模型才会画出断续的波光而不是一片白。"),
    "paddy": ("15", "盐田与稻浪", "格子里装着天的颜色",
              "盐田的水面是天空的镜子，提示词把「格子」当构图主体：先写田埂的网格线，再写每格里反射的云。秩序感来自几何，不来自颜色。"),
    "saltgalaxy": ("15", "盐湖星空", "脚下是银河，头顶也是",
                  "同一片盐湖同时有倒影和星空，提示词必须指定「foreground reflection sharper than the sky」，否则模型会把倒影也糊成星点。"),
    "tulip": ("15", "郁金香花田", "低到花茎高度的一条红带",
              "花田最容易糊成一片色块。提示词用「individual stems visible in the near rows」逼出个体，再让远处的行距收窄成色带。"),
    "watertown": ("17", "雨后江南水乡", "青石板、灯影、一条窄河",
                  "中式的场景要用中式的物件词：马头墙、河埠头、乌篷船、灯笼。写 whitewashed walls 太泛，模型会照欧洲小镇画。"),
    "sunflower": ("17", "黄昏向日葵", "最后一束光打在低垂的花盘上",
                  "「petals slightly drooping after the day's heat」这一句是灵魂：它同时给了时间（傍晚）、状态（晒了一天）和材质（花瓣失水），比写 warm light 有效得多。"),
    "snowforest": ("17", "雪后针叶林", "低角度的冬日阳光斜切树干",
                   "雪景的层次靠「前中后三段各自的雪」：前景是带风纹的新雪，中景是压弯的枝条，远景是被雾吞掉的树影。只写 snowy forest 会得到一片白。"),
}

samples = []
for slug, (batch_no, title, sub, note) in WALL_META.items():
    bdir = next(WALL.glob(f"batch{batch_no}_*"), None)
    if not bdir:
        print("missing batch", batch_no); continue
    pf = bdir / "prompts" / f"{slug}.txt"
    src = bdir / "base" / f"{slug}.png"
    if not pf.exists() or not src.exists():
        print("missing files", slug); continue
    prompt = pf.read_text(encoding="utf-8").strip()
    seed = None
    log = bdir / "gen.log"
    if log.exists():
        m = re.search(rf"START {slug} seed=(\d+)", log.read_text(errors="replace"))
        if m: seed = int(m.group(1))
    w, h = dims(src)
    thumb = sips_resize(src, IMG / f"{slug}-t.jpg", 720, 80)
    full = sips_resize(src, IMG / f"{slug}-f.jpg", 1600, 84)
    samples.append(dict(
        id=f"w-{slug}", kind="image", title=title, subtitle=sub,
        model="MiniMax H3-Image", model_short="H3-Image",
        size=f"{w}×{h}", aspect="9:16", seed=seed, seconds=None, frames=None,
        prompt=prompt, prompt_lang="en", lang_label="英文提示词",
        note=note, tags=["风景", "壁纸", "分层构图"], group="plate",
        media=dict(full=f"assets/img/{full.name}", thumb=f"assets/img/{thumb.name}", video=None, poster=None),
        source=f"壁纸产线 batch{batch_no} · {bdir.name.split('_', 1)[1]}",
    ))

# ── 2. 图槽资产（h3-drama-lab）──
ASSET_META = {
    "女主": dict(title="短剧女主 · 全身三视图", sub="同一条提示词补一句全身约束，脚就有了",
               note="初版只写了「三格同一人物、同一服装」，出来的三格到大腿就截断了，鞋完全看不见。补上「每一格都是从头顶到脚底的完整全身，双脚与鞋全部可见」这一句之后，同一 seed 重跑才得到这条完整全身三视图。人物资产能不能用，往往就差这一句。",
               tags=["人物", "三视图", "提示词迭代"]),
    "男主": dict(title="短剧男主 · 全身三视图", sub="同模板换角色，只改人物描述段",
               note="三视图模板稳住之后，换角色只改人物描述那一段：年龄、发型、服装、身形。模板里「三格同一人物、同一光位、同一比例、不要两格不要四格」全部保留，人物资产才能批量产。",
               tags=["人物", "三视图", "资产"]),
    "出租屋": dict(title="短剧场景 · 出租屋主视角", sub="五件家具，位置逐件写死",
                note="场景提示词把五件家具的位置逐件写死（小方桌、木椅、后墙门、左墙窗、低垂灯泡），因为后续每个镜头都要回到这个空间。空间一旦不确定，分镜之间就会穿帮。",
                tags=["场景", "空间", "资产"]),
}
pj = json.loads((DRAMA / "assets/生图词.json").read_text(encoding="utf-8"))
for item in pj:
    name = item["name"]
    if name not in ASSET_META: continue
    # 优先用 v2（全身版）——产线里最终采用的是它
    cand = sorted((DRAMA / "assets").glob(f"{item['slot']}_{name}*.png"))
    if not cand: print("missing asset", name); continue
    src = [p for p in cand if "v2" in p.name] or cand
    src = src[-1]
    w, h = dims(src)
    meta = ASSET_META[name]
    thumb = sips_resize(src, IMG / f"asset{item['slot']}-t.jpg", 720, 80)
    full = sips_resize(src, IMG / f"asset{item['slot']}-f.jpg", 1600, 84)
    samples.append(dict(
        id=f"a-{item['slot']}", kind="image", title=meta["title"], subtitle=meta["sub"],
        model="MiniMax H3-Image", model_short="H3-Image",
        size=f"{w}×{h}", aspect="4:3" if w > h else "9:16", seed=int(item["seed"]) if item.get("seed") else None,
        seconds=None, frames=None,
        prompt=item["prompt"], prompt_lang="zh", lang_label="中文提示词",
        note=meta["note"], tags=meta["tags"],
        group=("plate" if item["slot"] == "3" else "character"),
        media=dict(full=f"assets/img/{full.name}", thumb=f"assets/img/{thumb.name}", video=None, poster=None),
        source="短剧实验室 h3-drama-lab · 图槽资产（v2 全身版）",
    ))

# ── 3. 视频：从 4090 history 挑选，下载 + 转码 + 抽首帧 ──
VIDEO_PICK = [
    ("HOK_CHAIN_00164_.mp4", "守约 · 扣扳机", "枪口焰、弹头尾迹、镜头快速拉开",
     "把「快」写成三段时间：扳机指刚扣下（起）→ 弹头出膛（过程）→ 枪口焰与尾迹飞出画面（止）。再补一句镜头运动（fast rack out），模型才知道快的方向是往外拉，不是抖动。这条与下面两条是同一场雪地戏的连续镜头。"),
    ("HOK_CHAIN_00165_.mp4", "李白 · 被魂链抽飞", "受力点、身体翻转、酒葫芦弹起",
     "被击飞的写法要点在「受力链」：链子扫到哪、人被带向哪、随身物件怎么反应。只写「被击飞」模型会让人物凭空平移；写上酒葫芦从砖沿弹起，才有重量。"),
    ("HOK_CHAIN_00167_.mp4", "李白 · 砸进雪里", "落地、雪雾、静止",
     "落地镜头靠「余波」：人落地之后雪雾还要继续动一两秒，最后才停。提示词把结束状态写成「雪雾散开，人摊在雪坑里不动」，模型才给得出收尾，而不是在落地瞬间切掉。"),
]

rows = {}
rp = Path.home() / ".hermes/cache/scratch/h3rows.json"
if rp.exists():
    rows = {r["files"][0]: r for r in json.load(open(rp))}

# h3rows.json 是 scratch 缓存，随时会被清掉；缓存没了就沿用上一版 samples.json 里的中文提示词，
# 不能因为一个临时文件缺失把已经核对过的提示词写成空字符串。
prev_video_prompt = {}
_prev = ROOT / "data/samples.json"
if _prev.exists():
    try:
        for _s in json.loads(_prev.read_text(encoding="utf-8")).get("samples", []):
            if _s.get("kind") == "video" and _s.get("prompt"):
                prev_video_prompt[_s["id"]] = _s["prompt"]
    except Exception as _e:
        print("prev samples read fail", _e)

for fname, title, sub, note in VIDEO_PICK:
    dst = VID / fname.lower().replace("hok_chain_", "v").replace("_.mp4", ".mp4")
    r = rows.get(fname, {})
    if not dst.exists():
        tmp = VID / (fname + ".part")
        got = run(["curl", "-s", "-m", "120", f"http://{HOST}/view?filename={fname}&type=output", "-o", str(tmp)])
        if not tmp.exists() or tmp.stat().st_size < 100000:
            print("video download fail", fname, got.stderr[:100]); tmp.unlink(missing_ok=True); continue
        # 转码：保持分辨率，crf 26，faststart，保留原音轨
        r2 = run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp), "-c:v", "libx264", "-crf", "26",
                  "-preset", "slow", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k",
                  "-movflags", "+faststart", str(dst)])
        tmp.unlink(missing_ok=True)
        if r2.returncode != 0 or not dst.exists():
            print("transcode fail", fname, r2.stderr[:200]); continue
    poster = PST / (dst.stem + ".jpg")
    if not poster.exists():
        # 封面取「最亮的一帧」：在动作中段抽三帧比亮度，避免首帧全黑的镜头
        dur = 2.33
        pr = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(dst)])
        try: dur = float(pr.stdout.strip() or dur)
        except ValueError: pass
        best, best_y = None, -1
        for k in (0.25, 0.5, 0.78):
            tmp = PST / f".{dst.stem}-{int(k*100)}.jpg"
            run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{dur * k:.2f}", "-i", str(dst),
                 "-frames:v", "1", "-vf", "scale=960:-2", str(tmp)])
            if not tmp.exists(): continue
            gf = PST / ".y.gray"
            run(["ffmpeg", "-y", "-v", "error", "-i", str(tmp), "-vf", "scale=1:1", "-f", "rawvideo",
                 "-pix_fmt", "gray", str(gf)])
            try:
                y = gf.read_bytes()[0]
            except Exception:
                y = 0
            gf.unlink(missing_ok=True)
            if y > best_y:
                if best and best.exists(): best.unlink()
                best, best_y = tmp, y
            else:
                tmp.unlink(missing_ok=True)
        if best and best.exists():
            best.rename(poster)
    w, h = dims(poster) if poster.exists() else (None, None)
    samples.append(dict(
        id="v-" + dst.stem, kind="video", title=title, subtitle=sub,
        model="MiniMax H3-Ref2VA", model_short="H3-Ref2VA",
        size="1344×768", aspect="16:9", seed=None, seconds=2.3, frames=52,
        prompt=(r.get("txt", "") or prev_video_prompt.get("v-" + dst.stem, "")).strip(),
        prompt_lang="zh", lang_label="中文提示词",
        note=note, tags=["视频", "动作", "运镜"], group="video",
        media=dict(full=None, thumb=f"assets/poster/{poster.name}", video=f"assets/video/{dst.name}",
                   poster=f"assets/poster/{poster.name}"),
        source="4090 ComfyUI · H3 Ref2VA · 52 帧",
    ))

# ── 4. 荷塘巨物 · 四机位（老大收集的生图提示词 → 4090 H3-Image 复现；每条附自己写的动作提示词）──
LOTUS = Path.home() / ".hermes/artifacts/prompt-lotus"
LOTUS_META = [
    dict(
        slug="p1", sid="l-under", src="p1.png",
        title="水下仰拍 · 天空是一扇天窗",
        sub="镜头泡在水里，贴住水面往正上方看",
        note="这条试了三版才成。第一版模型给的是沿水线切开的半水面镜头（水下与天空同框，但透视没仰起来）；第二版真的从水底往上看、能看到船底，却把一条金鱼画到水面以上的空中；"
             "第三版把「所有金鱼都在水面以下」「船体只占画面中部、上方留出天空」两句写进去才干净。教训：仰拍要给模型一个否定不掉的参照物——「看得到船底」比「垂直向上」更能逼出机位。",
        tags=["四机位", "仰拍", "巨物感", "水下"],
        motion=dict(
            title="动作：手指点水，涟漪向下",
            prompt="镜头保持在水下原位不动，水面上的木船轻轻左右晃动。小女孩伸出一根手指点进水里，指尖入水的瞬间，一圈涟漪从船边向下扩散，细小气泡成串升起，金鱼从画面两侧游过。结束时船和人都回到原位，光线与水面亮度不变。一镜到底，不剪辑，不切换机位。",
            note="水下仰拍的运动会破坏「天窗」构图，所以只给它两个小动作（手指点水、船身轻晃），镜头一动不动。",
        ),
    ),
    dict(
        slug="p2", sid="l-top", src="p2.png",
        title="高空俯拍 · 一片叶子占满前景",
        sub="人与狗只有指甲盖大，巨物感全靠近大远小",
        note="近大远小是这条的全部：前景叶片占满下缘，远处人与狗只有几个像素。想修掉叶心那个浅色圆盘，第二版整条跑成贴水面的低机位——巨物感更强，但「正上方俯拍」没了，圆盘也还在，所以站上用回第一版。"
             "判据：画面里荷叶是顶视的放射状叶脉、船体侧壁看不见，这才是俯拍；另外原稿把「王莲 / water lily pad / Victoria」写在负向里，H3-Image 不吃负向，已改成正面的荷叶形态描述。",
        tags=["四机位", "俯拍", "近大远小", "巨物感"],
        motion=dict(
            title="动作：船原地打转，水珠滚落",
            prompt="镜头在正上方保持不动，只做极缓慢的推近。木船在原地轻轻打转，女孩抬头望向天空，狗的耳朵被风吹动；一片荷叶上的水珠滚落进水里，涟漪一圈圈散开。结束时船停回两片大叶之间，构图与开头一致。",
            note="俯拍最怕镜头动，一动巨物感就散；把动势放在船和水珠上，机位只留一次几乎看不出的推近。",
        ),
    ),
    dict(
        slug="p3", sid="l-mid", src="p3.png",
        title="中景 · 扯叶子，水帘落下",
        sub="拉扯、倾斜、倾倒、溅起，四个状态都写成看得见的东西",
        note="初版有两个硬伤：女孩的手悬在荷叶上方没有接触点，水帘是一根悬空的透明水柱。第二版把接触点写死（抓住最低处的叶缘、把叶缘往下拉、叶面被拉出折痕），并要求水幕「形状跟着叶缘走，是一片帘子，不是一根水柱」，才成立。"
             "50mm + 浅景深在这里是必要的：背景荷叶一虚，手和水帘才立得住。原稿的负面词表（塑料皮肤 / 美颜滤镜 / 网红脸 / 面部模糊）也一并改写成正面：真实的皮肤质感、毛发根根分明。",
        tags=["四机位", "中景", "水帘", "50mm"],
        motion=dict(
            title="动作：整片叶面倾倒",
            prompt="镜头位置不变。女孩双手用力一扯荷叶边缘，整片叶面倾斜，积存的清水整片倾倒下来形成一道水帘；狗被水花溅到，往后缩了半步。水帘落进水里，荷叶回弹轻晃，水珠还悬在空中。结束在荷叶停止晃动、水面涟漪散开的一刻。一镜到底。",
            note="图生视频要的是一个连续动作，不是四个：起手（扯）→ 过程（倾倒成帘）→ 余响（回弹、涟漪）。",
        ),
    ),
    dict(
        slug="p4", sid="l-close", src="p4.png",
        title="近景 · 狗咬着莲蓬往后扯",
        sub="两个动作同时发生，靠船头船尾把它们分开",
        note="两个动作（船头狗扯莲蓬、船尾女孩撑篙）靠位置分开才不糊。第一版光线与巨伞荷叶都对，但女孩和狗被画到了两条船上；第二版把它们收回同一条船、茎杆也拉出了弓形，代价是天气跑成灰白阴天、背景荷叶没长成巨伞。"
             "这条的真实结论：同一条船和弓形茎杆能写出来，梦幻暖光与巨物尺度还压不住，得分开生成或后期补光。原稿「用嘴哎住」是「咬住」的手误，已改。",
        tags=["四机位", "近景", "双动作", "莲蓬"],
        motion=dict(
            title="动作：扯莲蓬 + 撑一篙",
            prompt="镜头位置不变。狗咬着莲蓬的茎杆往后一扯，茎杆被拉成弓形，莲蓬被拉到狗鼻前；同一时间，女孩把竹篙往水里一撑，船身向前滑出半米。结束在船头轻轻一沉、水面涟漪扩散开的瞬间。一镜到底。",
            note="两个动作要给两段时间差：狗先扯（前 1 秒），船再动（后 1 秒），否则两条动线会互相打架。",
        ),
    ),
]

for m in LOTUS_META:
    src = LOTUS / str(m["src"])
    stem = {"p1": "underwater", "p2": "aerial", "p3": "medium", "p4": "close"}[str(m["slug"])]
    pf = LOTUS / f"{m['slug']}-{stem}.txt"
    if not src.exists() or not pf.exists():
        print("missing lotus", m["slug"], src.exists(), pf.exists()); continue
    prompt = pf.read_text(encoding="utf-8").strip()
    w, h = dims(src)
    thumb = sips_resize(src, IMG / f"{m['sid']}-t.jpg", 820, 80)
    full = sips_resize(src, IMG / f"{m['sid']}-f.jpg", 1800, 84)
    if not thumb or not full:
        print("lotus resize fail", m["slug"]); continue
    samples.append(dict(
        id=m["sid"], kind="image", title=m["title"], subtitle=m["sub"],
        model="MiniMax H3-Image", model_short="H3-Image",
        size=f"{w}×{h}", aspect="16:9", seed=5285, seconds=None, frames=None,
        prompt=prompt, prompt_lang="zh", lang_label="中文提示词 · 原稿改编",
        note=m["note"], tags=m["tags"], group="lotus",
        media=dict(full=f"assets/img/{full.name}", thumb=f"assets/img/{thumb.name}", video=None, poster=None),
        motion=m["motion"],
        source="老大收集 · 荷塘巨物四机位 · 4090 H3-Image 复现（6272×2688 / seed 5285）",
    ))

out = ROOT / "data/samples.json"
out.parent.mkdir(exist_ok=True)
payload = {
    "updated": "2026-11-18",
    "models": sorted({s["model"] for s in samples}),
    "groups": [
        {"id": "lotus", "label": "荷塘四机位", "note": "同一场景四个机位：水下仰拍 → 高空俯拍 → 中景 → 近景；四条各自独立生成（未锁参考图），人、狗与服装不跨镜一致"},
        {"id": "character", "label": "人物资产", "note": "三视图：同一人、同一光位、三格完整全身"},
        {"id": "video", "label": "动作镜头", "note": "图生视频：起始状态 → 动作 → 结束状态"},
        {"id": "plate", "label": "壁纸与场景", "note": "竖版 9:16：12 张 8K 风景 + 1 个短剧场景"},
    ],
    "samples": samples,
}
json.dump(payload, out.open("w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\n=== {len(samples)} samples ===")
for s in samples:
    print(f"{s['id']:16s} {s['kind']:5s} {s['title']:14s} prompt={len(s['prompt']):4d} {s['media']['thumb']}")
