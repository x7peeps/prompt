#!/usr/bin/env python3
"""真实渲染取证：多档视口截图 + 几何/溢出/资源/错误断言。

用法: python3 scripts/probe.py [url] [outdir]
"""
import json, sys, os
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8931/"
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser("~/.hermes/artifacts/prompt-site/shots")
os.makedirs(OUT, exist_ok=True)

VIEWS = [("desk", 1440, 900), ("wide", 1920, 1080), ("tab", 820, 1100), ("phone", 390, 844)]

report = {"url": URL, "views": {}, "problems": []}

LOCAL = ("127.0.0.1" in URL) or ("localhost" in URL)
CHROME_ARGS = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"]
if LOCAL:
    # 本地页面必须绕开系统代理，否则被塞进境外节点，截到的是代理错误页
    CHROME_ARGS += ["--proxy-server=direct://", "--proxy-bypass-list=*"]

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True, args=CHROME_ARGS)
    for name, w, h in VIEWS:
        ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=2,
                            color_scheme="light")
        pg = ctx.new_page()
        errs, reqfail = [], []
        pg.on("pageerror", lambda e: errs.append("pageerror: " + str(e)))
        pg.on("console", lambda m: errs.append("console." + m.type + ": " + m.text) if m.type == "error" else None)
        pg.on("requestfailed", lambda r: reqfail.append(r.url.split("/")[-1] + " :: " + (r.failure or "")))
        pg.goto(URL, wait_until="domcontentloaded", timeout=30000)
        pg.wait_for_function("() => document.querySelectorAll('.s').length > 0", timeout=15000)
        # 等首屏可见的图片真正解码完成（lazy 图在视口外不加载，不能要求全部完成）
        pg.wait_for_function("""() => {
            const imgs = [...document.querySelectorAll('.s img')];
            const visible = imgs.filter(i => { const r = i.getBoundingClientRect(); return r.top < innerHeight && r.bottom > 0; });
            const okCount = visible.filter(i => i.complete && i.naturalWidth > 0).length;
            return visible.length > 0 && okCount >= Math.min(4, visible.length);
        }""", timeout=25000)
        pg.wait_for_timeout(600)

        m = pg.evaluate("""() => {
          const de = document.documentElement, bd = document.body;
          const cards = [...document.querySelectorAll('.s')];
          const rects = cards.map(c => c.getBoundingClientRect());
          const inFirst = rects.filter(r => r.top < innerHeight && r.bottom > 0).length;
          const broken = [...document.querySelectorAll('img')].filter(i => i.complete && i.naturalWidth === 0).length;
          const overflowEls = [...document.querySelectorAll('body *')]
             .filter(e => { const r = e.getBoundingClientRect(); return r.right > innerWidth + 1 && r.width > 0; })
             .slice(0, 5).map(e => e.className + ' right=' + Math.round(e.getBoundingClientRect().right));
          const fs = {};
          [...document.querySelectorAll('.s-title,.s-spec,.s-prompt,.v-title,.v-sub')].forEach(e => {
            const s = getComputedStyle(e).fontSize; fs[s] = (fs[s]||0)+1;
          });
          const h1 = document.querySelector('h1');
          return {
            title: document.title,
            innerWidth, scrollWidth: de.scrollWidth, bodyScrollWidth: bd.scrollWidth,
            cards: cards.length, cardsInFirstScreen: inFirst,
            cols: document.querySelectorAll('.col').length,
            brokenImages: broken,
            h1: h1 ? h1.textContent.trim() : null,
            h1Count: document.querySelectorAll('h1').length,
            firstPromptChars: cards[0] ? (cards[0].querySelector('.s-prompt')||{}).textContent.length : 0,
            gridTop: cards[0] ? Math.round(rects[0].top) : null,
            overflowEls,
            fontSizes: fs
          };
        }""")
        m["errors"] = errs
        m["requestFailed"] = reqfail
        if m["scrollWidth"] > m["innerWidth"] + 1:
            report["problems"].append(f"{name}: 横向溢出 scrollWidth={m['scrollWidth']} > {m['innerWidth']}")
        if m["bodyScrollWidth"] > m["innerWidth"] + 1:
            report["problems"].append(f"{name}: body 横向溢出 {m['bodyScrollWidth']}")
        if errs:
            report["problems"].append(f"{name}: JS 错误 {errs[:2]}")
        if m["brokenImages"]:
            report["problems"].append(f"{name}: 破图 {m['brokenImages']}")
        report["views"][name] = m

        pg.screenshot(path=f"{OUT}/{name}.png", full_page=False)
        pg.screenshot(path=f"{OUT}/{name}-full.png", full_page=True)

        # 详情页取证（桌面 + 手机各一次）
        if name in ("desk", "phone"):
            pg.click(".s")
            pg.wait_for_selector("#viewer[open]", timeout=5000)
            pg.wait_for_timeout(900)
            d = pg.evaluate("""() => {
              const v = document.getElementById('viewer');
              const pre = document.getElementById('v-prompt');
              const side = document.querySelector('.v-side');
              const stage = document.querySelector('.v-stage');
              return {
                open: v.hasAttribute('open'),
                promptChars: pre.textContent.length,
                promptScrollH: pre.scrollHeight, promptClientH: pre.clientHeight,
                sideScrollH: side.scrollHeight, sideClientH: side.clientHeight,
                stageW: Math.round(stage.getBoundingClientRect().width),
                mediaTag: (stage.querySelector('img,video')||{tagName:''}).tagName,
                mediaW: Math.round((stage.querySelector('img,video')||{getBoundingClientRect:()=>({width:0,height:0})}).getBoundingClientRect().width),
                mediaH: Math.round((stage.querySelector('img,video')||{getBoundingClientRect:()=>({width:0,height:0})}).getBoundingClientRect().height),
                title: document.getElementById('v-title').textContent,
                specRows: document.querySelectorAll('#v-spec div').length,
                scrollWidth: document.documentElement.scrollWidth, innerWidth
              };
            }""")
            report["views"][name + "-detail"] = d
            if not d["open"]:
                report["problems"].append(f"{name}: 详情未打开")
            if d["promptChars"] < 50:
                report["problems"].append(f"{name}: 详情提示词为空")
            pg.screenshot(path=f"{OUT}/{name}-detail.png", full_page=False)
            # 复制按钮
            pg.click("#v-copy")
            pg.wait_for_timeout(500)
            c = pg.evaluate("""() => ({label: document.getElementById('v-copy').textContent,
                                      seal: document.getElementById('seal').classList.contains('on')})""")
            report["views"][name + "-copy"] = c
            if "已复制" not in c["label"]:
                report["problems"].append(f"{name}: 复制按钮无反馈 -> {c['label']}")
            pg.screenshot(path=f"{OUT}/{name}-detail-copied.png", full_page=False)
            pg.keyboard.press("Escape")
            pg.wait_for_timeout(300)

        ctx.close()
    b.close()

print(json.dumps(report, ensure_ascii=False, indent=1))
print("\n=== PROBLEMS ===")
print("\n".join(report["problems"]) or "none")
