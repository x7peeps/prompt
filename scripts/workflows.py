#!/usr/bin/env python3
"""可复用工作流库：出图前先查这里，别每次重搭。

用法:
  python3 scripts/workflows.py list                 # 列出全部工作流
  python3 scripts/workflows.py show <id>            # 看工作流详情（含参数说明）
  python3 scripts/workflows.py run <id> --prompt "..." [--seed N] [--w 1024] [--h 1024]
                                                       [--steps 20] [--cfg 4.0] [--name out]
  python3 scripts/workflows.py check <id>           # 目标机是否有该工作流依赖的模型

设计原则（老大 2026-11-21 定）:
  1. 每次出图前必须先 list + check 有没有可复用的工作流，没有才新建；
  2. 新建的工作流跑通后必须回写进 workflows/ 并在 catalog.json 登记；
  3. 工作流用 API 格式存（可直接 POST /prompt），元信息写在 _meta 里。
"""
import argparse, json, os, subprocess, sys, time, urllib.request, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF_DIR = os.path.join(ROOT, "workflows")
CATALOG = os.path.join(WF_DIR, "catalog.json")
DEFAULT_HOST = "http://192.168.3.7:8190"


def load_catalog():
    if os.path.exists(CATALOG):
        return json.load(open(CATALOG, encoding="utf-8"))
    return {}


def wf_path(wid):
    return os.path.join(WF_DIR, f"{wid}.json")


def cmd_list(args):
    cat = load_catalog()
    if not cat:
        print("工作流库是空的")
        return
    print(f"{'ID':32s} {'标题':40s} 目标机")
    print("-" * 100)
    for wid, meta in sorted(cat.items()):
        p = wf_path(wid)
        ok = "✓" if os.path.exists(p) else "缺文件"
        print(f"{wid:32s} {meta.get('title',''):40s} {meta.get('host', DEFAULT_HOST)}  [{ok}]")
    print(f"\n共 {len(cat)} 条。用 `show <id>` 看细节，`run <id> --prompt ...` 直接跑。")


def cmd_show(args):
    p = wf_path(args.id)
    if not os.path.exists(p):
        print(f"找不到工作流：{args.id}")
        sys.exit(1)
    wf = json.load(open(p, encoding="utf-8"))
    meta = wf.get("_meta", {})
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print("\n--- 节点 ---")
    for nid, node in wf.items():
        if nid.startswith("_"):
            continue
        ct = node.get("class_type")
        ins = {k: v for k, v in node.get("inputs", {}).items()
               if k in ("unet_name", "ckpt_name", "vae_name", "clip_name", "weight_dtype",
                        "type", "seed", "steps", "cfg", "sampler_name", "scheduler",
                        "width", "height", "filename_prefix")}
        if ins:
            print(f"  {nid}: {ct}  {json.dumps(ins, ensure_ascii=False)}")


def _model_refs(wf):
    """抽出工作流依赖的模型文件名，用于 check。"""
    keys = ("unet_name", "ckpt_name", "vae_name", "clip_name", "clip_name1", "clip_name2")
    refs = []
    for nid, node in wf.items():
        if nid.startswith("_") or not isinstance(node, dict):
            continue
        for k in keys:
            v = node.get("inputs", {}).get(k)
            if isinstance(v, str):
                refs.append((k, v))
    return refs


def cmd_check(args):
    host = args.host
    try:
        info = json.load(urllib.request.urlopen(host + "/object_info", timeout=20))
    except Exception as e:
        print(f"连不上 {host}: {e}")
        sys.exit(2)
    wf = json.load(open(wf_path(args.id), encoding="utf-8"))
    refs = _model_refs(wf)
    print(f"检查 {args.id} @ {host}")
    bad = 0
    for kind, fname in refs:
        found = False
        for node, data in info.items():
            req = (data.get("input") or {}).get("required") or {}
            for k, opts in req.items():
                if isinstance(opts, list) and opts and isinstance(opts[0], list) and fname in opts[0]:
                    found = True
        print(f"  {'OK ' if found else 'MISS'} {kind}: {fname}")
        if not found:
            bad += 1
    print("\n结论:", "全部就位" if bad == 0 else f"{bad} 个模型缺失")
    sys.exit(1 if bad else 0)


def cmd_run(args):
    p = wf_path(args.id)
    if not os.path.exists(p):
        print(f"找不到工作流：{args.id}")
        sys.exit(1)
    wf = json.load(open(p, encoding="utf-8"))
    meta = wf.get("_meta", {})
    host = args.host or meta.get("host") or DEFAULT_HOST

    prompt = args.prompt
    if prompt.startswith("@"):
        prompt = open(prompt[1:], encoding="utf-8").read().strip()
    if not prompt:
        print("必须给 --prompt（可用 @file.txt 读文件）")
        sys.exit(1)

    changed = 0
    for nid, node in wf.items():
        if nid.startswith("_") or not isinstance(node, dict):
            continue
        ins = node.get("inputs", {})
        if node.get("class_type") == "CLIPTextEncode" and "text" in ins:
            ins["text"] = prompt
            changed += 1
        if node.get("class_type") == "KSampler":
            if args.seed is not None:
                ins["seed"] = args.seed
            if args.steps is not None:
                ins["steps"] = args.steps
            if args.cfg is not None:
                ins["cfg"] = args.cfg
        if node.get("class_type") in ("EmptySD3LatentImage", "EmptyLatentImage", "EmptyHunyuanLatentVideo"):
            if args.w:
                ins["width"] = args.w
            if args.h:
                ins["height"] = args.h
        if node.get("class_type") == "SaveImage":
            ins["filename_prefix"] = args.name or ins.get("filename_prefix", "prompt-site/out")

    payload = {k: v for k, v in wf.items() if not k.startswith("_")}
    req = urllib.request.Request(host + "/prompt", data=json.dumps({"prompt": payload}).encode(),
                                 headers={"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=60))
    pid = r["prompt_id"]
    print(f"[{args.id}] submitted {pid} -> {host}  (提示词已写入 {changed} 个节点)")

    t0 = time.time()
    while time.time() - t0 < args.timeout:
        time.sleep(5)
        h = json.load(urllib.request.urlopen(host + f"/history/{pid}", timeout=30))
        if pid in h:
            outs = h[pid].get("outputs", {})
            got = []
            for nid, o in outs.items():
                for f in (o.get("images") or []):
                    got.append((f.get("filename"), f.get("subfolder")))
                    url = (host + "/view?filename=" + urllib.parse.quote(f.get("filename", ""))
                           + "&subfolder=" + urllib.parse.quote(f.get("subfolder") or "")
                           + "&type=" + f.get("type", "output"))
                    print(f"  OUT {f.get('filename')}  {url}")
            if got:
                print(f"完成，用时 {int(time.time()-t0)}s")
                return
    print("超时")
    sys.exit(3)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    s = sub.add_parser("show"); s.add_argument("id")
    s = sub.add_parser("check"); s.add_argument("id"); s.add_argument("--host", default=DEFAULT_HOST)
    s = sub.add_parser("run"); s.add_argument("id"); s.add_argument("--prompt", required=True)
    s.add_argument("--seed", type=int); s.add_argument("--steps", type=int); s.add_argument("--cfg", type=float)
    s.add_argument("--w", type=int); s.add_argument("--h", type=int); s.add_argument("--name")
    s.add_argument("--host"); s.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()
    {"list": cmd_list, "show": cmd_show, "check": cmd_check, "run": cmd_run}[args.cmd](args)


if __name__ == "__main__":
    main()
