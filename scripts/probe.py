#!/usr/bin/env python3
"""真实渲染取证 + 交付断言：多档视口截图、几何/溢出/资源/交互/数据一致性。

用法: python3 scripts/probe.py [url] [outdir]
退出码: 0 = 无问题；1 = 有问题
"""
import json, os, sys
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8931/"
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser("~/.hermes/artifacts/prompt-site/shots")
os.makedirs(OUT, exist_ok=True)

VIEWS = [("desk", 1440, 900), ("wide", 1920, 1080), ("tab", 820, 1100), ("phone", 390, 844)]
LOCAL = ("127.0.0.1" in URL) or ("localhost" in URL)
CHROME_ARGS = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
               "--autoplay-policy=no-user-gesture-required"]
if LOCAL:  # 本地页面必须绕开系统代理，否则截到的是代理错误页
    CHROME_ARGS += ["--proxy-server=direct://", "--proxy-bypass-list=*"]

report = {"url": URL, "views": {}, "problems": []}
bad = report["problems"].append


def static_checks():
    """不依赖浏览器的交付约束：数据契约、HTML 关键点、分享图。"""
    data = json.load(open(f"{ROOT}/data/samples.json", encoding="utf-8"))
    if set(data) != {"updated", "models", "samples"}:
        bad(f"data: 顶层字段异常 {list(data)}")
    samples = data["samples"]
    report["data"] = {"n": len(samples), "models": data["models"],
                      "kinds": {k: sum(1 for s in samples if s["kind"] == k) for k in ("image", "video")}}
    if any("H3 Ref2VA" in m for m in data["models"]):
        bad("data: 模型名出现空格变体（应为 H3-Ref2VA）")
    for s in samples:
        if not s["prompt"].strip():
            bad(f"data: {s['id']} 提示词为空")
        if s["kind"] == "video" and not (s["media"].get("video") and s["media"].get("poster")):
            bad(f"data: {s['id']} 视频缺 video/poster")
        for k in ("thumb", "full"):
            p = s["media"].get(k)
            if p and not os.path.exists(os.path.join(ROOT, p)):
                bad(f"data: {s['id']} 缺文件 {p}")

    html = open(f"{ROOT}/index.html", encoding="utf-8").read()
    if "27 条" in html or ">27<" in html:
        bad("html: 仍有写死的 27 条（条数必须只来自 JSON）")
    if 'content="https://prompt.x7peeps.com/og.jpg"' not in html:
        bad("html: og:image 未指向 og.jpg")
    og = os.path.join(ROOT, "og.jpg")
    if not os.path.exists(og) or os.path.getsize(og) > 300_000:
        bad(f"html: og.jpg 缺失或过大（{os.path.getsize(og)//1024 if os.path.exists(og) else 'missing'}KB）")
    if 'createElement("button")' in html:
        bad("html: 卡片仍用 <button> 承载块级内容")
    if "aria-selected" in html:
        bad("html: 仍有 aria-selected（筛选器应为 aria-pressed）")
    report["static"] = "checked"


static_checks()

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True, args=CHROME_ARGS)
    for name, w, h in VIEWS:
        ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=2, color_scheme="light")
        pg = ctx.new_page()
        errs, reqfail = [], []
        pg.on("pageerror", lambda e: errs.append("pageerror: " + str(e)))
        pg.on("console", lambda m: errs.append("console." + m.type + ": " + m.text) if m.type == "error" else None)
        pg.on("requestfailed", lambda r: reqfail.append(r.url.split("/")[-1] + " :: " + (r.failure or "")))
        pg.goto(URL, wait_until="domcontentloaded", timeout=30000)
        pg.wait_for_function("() => document.querySelectorAll('.s').length > 0", timeout=15000)
        # lazy 图在视口外不加载，只要求首屏可见的已解码
        pg.wait_for_function("""() => {
            const imgs = [...document.querySelectorAll('.s img')];
            const visible = imgs.filter(i => { const r = i.getBoundingClientRect(); return r.top < innerHeight && r.bottom > 0; });
            return visible.length > 0 && visible.filter(i => i.complete && i.naturalWidth > 0).length >= Math.min(4, visible.length);
        }""", timeout=25000)
        pg.wait_for_timeout(600)

        m = pg.evaluate("""() => {
          const de = document.documentElement, bd = document.body;
          const cards = [...document.querySelectorAll('.s')];
          const rects = cards.map(c => c.getBoundingClientRect());
          const go = cards[0] && cards[0].querySelector('.s-go');
          return {
            innerWidth, scrollWidth: de.scrollWidth, bodyScrollWidth: bd.scrollWidth,
            cards: cards.length,
            allAnchor: cards.every(c => c.tagName === 'A'),
            cardsInFirstScreen: rects.filter(r => r.top < innerHeight && r.bottom > 0).length,
            brokenImages: [...document.querySelectorAll('img')].filter(i => i.complete && i.naturalWidth === 0).length,
            h1: (document.querySelector('h1') || {}).textContent.trim(),
            h1Count: document.querySelectorAll('h1').length,
            tabsPressed: document.querySelectorAll('.tabs button[aria-pressed]').length,
            legend: document.getElementById('legend').textContent,
            goPos: go ? getComputedStyle(go).position : null,
            goInMedia: go ? go.parentElement.className : null,
            cardFontSizes: [...new Set([...document.querySelectorAll('.s-title,.s-spec,.s-prompt,.s-no,.lede')]
                            .map(e => getComputedStyle(e).fontSize))],
            overflowEls: [...document.querySelectorAll('body *')]
               .filter(e => { const r = e.getBoundingClientRect(); return r.right > innerWidth + 1 && r.width > 0; })
               .slice(0, 5).map(e => e.className + ' right=' + Math.round(e.getBoundingClientRect().right))
          };
        }""")
        m["errors"], m["requestFailed"] = errs, reqfail
        for key, label in (("scrollWidth", "横向溢出"), ("bodyScrollWidth", "body 横向溢出")):
            if m[key] > m["innerWidth"] + 1:
                bad(f"{name}: {label} {m[key]} > {m['innerWidth']}  {m['overflowEls']}")
        if errs:
            bad(f"{name}: JS 错误 {errs[:2]}")
        if m["brokenImages"]:
            bad(f"{name}: 破图 {m['brokenImages']}")
        if m["cards"] != report["data"]["n"]:
            bad(f"{name}: 卡片数 {m['cards']} ≠ 数据 {report['data']['n']}")
        if not m["allAnchor"]:
            bad(f"{name}: 存在非 <a> 卡片")
        if not m["h1"] or str(report["data"]["n"]) not in m["h1"]:
            bad(f"{name}: H1 条数与数据不一致 -> {m['h1']}")
        if m["tabsPressed"] != 3:
            bad(f"{name}: 筛选按钮 aria-pressed 数 {m['tabsPressed']} ≠ 3")
        if not all(x in m["legend"] for x in report["data"]["models"]):
            bad(f"{name}: 图例未覆盖全部模型 -> {m['legend']}")
        if m["goPos"] != "absolute" or "s-media" not in (m["goInMedia"] or ""):
            bad(f"{name}: 「打开」浮标未浮在图上 -> {m['goPos']} / {m['goInMedia']}")
        if len(set(m["cardFontSizes"])) > 5:
            bad(f"{name}: 卡片字号 {len(set(m['cardFontSizes']))} 档 > 5  {m['cardFontSizes']}")
        report["views"][name] = m

        pg.screenshot(path=f"{OUT}/{name}.png", full_page=False)
        pg.screenshot(path=f"{OUT}/{name}-full.png", full_page=True)

        if name in ("desk", "phone"):
            pg.click(".s")
            pg.wait_for_selector("#viewer[open]", timeout=5000)
            pg.wait_for_timeout(900)
            d = pg.evaluate("""() => {
              const v = document.getElementById('viewer');
              const pre = document.getElementById('v-prompt'), pr = pre.getBoundingClientRect();
              const copy = document.getElementById('v-copy').getBoundingClientRect();
              const stage = document.querySelector('.v-stage').getBoundingClientRect();
              return {open: v.hasAttribute('open'), promptChars: pre.textContent.length,
                      promptTop: Math.round(pr.top), stageH: Math.round(stage.height),
                      copyH: Math.round(copy.height), specRows: document.querySelectorAll('#v-spec div').length,
                      inert: document.querySelector('header').hasAttribute('inert'),
                      sealBottom: getComputedStyle(document.getElementById('seal')).bottom};
            }""")
            report["views"][name + "-detail"] = d
            if not d["open"] or d["promptChars"] < 50:
                bad(f"{name}: 详情未打开或提示词为空")
            if d["specRows"] != 6:
                bad(f"{name}: 参数格数 {d['specRows']} ≠ 6（会有空白格）")
            if not d["inert"]:
                bad(f"{name}: 模态未给背景加 inert")
            if not d["sealBottom"].startswith("-"):
                bad(f"{name}: 印章不在框外（会压复制按钮）")
            if name == "phone":
                if d["promptTop"] >= 844:
                    bad(f"phone: 提示词在折叠线外 top={d['promptTop']}")
                if d["specRows"] < 6 or d["copyH"] < 44:
                    bad(f"phone: 触控目标 {d['copyH']}px < 44px")
            pg.screenshot(path=f"{OUT}/{name}-detail.png", full_page=False)
            pg.click("#v-copy")
            pg.wait_for_timeout(500)
            c = pg.evaluate("""() => ({label: document.getElementById('v-copy').textContent,
                                      seal: document.getElementById('seal').classList.contains('on')})""")
            if "已复制" not in c["label"] or "字符" not in c["label"]:
                bad(f"{name}: 复制反馈异常 -> {c['label']}")
            if not c["seal"]:
                bad(f"{name}: 复制后印章未响应")
            pg.screenshot(path=f"{OUT}/{name}-detail-copied.png", full_page=False)
            pg.keyboard.press("Escape")
            pg.wait_for_timeout(300)
            if pg.evaluate("() => document.getElementById('viewer').hasAttribute('open') || document.querySelector('header').hasAttribute('inert')"):
                bad(f"{name}: ESC 未关闭或未解除 inert")

        ctx.close()
    b.close()

print(json.dumps(report, ensure_ascii=False, indent=1))
print("\n=== PROBLEMS ===")
print("\n".join(report["problems"]) or "none")
sys.exit(1 if report["problems"] else 0)
