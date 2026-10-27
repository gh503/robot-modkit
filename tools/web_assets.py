#!/usr/bin/env python3
"""校验 GitHub Pages 静态资产：Service Worker 壳、HTML 引用、JSON 数据、版本一致性。

Pages 直接上传 web/，没有构建步骤；资产缺失/版本漂移不会让 CI 自动红。
本脚本在 CI/Pages 上传前跑，失败就阻断部署。

用法：python tools/web_assets.py [web目录]
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _arrays(js: str, name: str) -> list[str]:
    m = re.search(r"var\s+" + re.escape(name) + r"\s*=\s*\[(.*?)\];", js, re.S)
    if not m:
        raise ValueError(f"sw.js 缺少 {name} 数组")
    return re.findall(r'"([^"]+)"', m.group(1))


def check(web: pathlib.Path) -> list[str]:
    bad: list[str] = []
    sw_path = web / "sw.js"
    if not sw_path.is_file():
        return ["web/sw.js 不存在"]
    sw = sw_path.read_text(encoding="utf-8")
    try:
        shell = _arrays(sw, "SHELL")
        models = _arrays(sw, "MODELS")
    except ValueError as e:
        return [str(e)]
    for raw in shell + models:
        rel = raw[2:] if raw.startswith("./") else raw
        p = web / rel
        if not p.exists():
            bad.append(f"Service Worker 资产缺失：{raw}")
    # HTML 同源引用（src/href），排除锚点/外链/data
    for html in sorted(web.glob("*.html")):
        text = html.read_text(encoding="utf-8", errors="ignore")
        for raw in re.findall(r'(?:src|href)="([^"]+)"', text):
            if raw.startswith(("http://", "https://", "#", "data:", "mailto:", "javascript:")):
                continue
            target = raw.split("#", 1)[0].split("?", 1)[0]
            if not target:
                continue
            p = (html.parent / target).resolve()
            if not p.exists():
                bad.append(f"{html.relative_to(web)} 引用缺失：{raw}")
    # 世界数据必须能解析，且 schema 为 v2
    for p in sorted((web / "data").glob("world-*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            bad.append(f"{p.name} JSON 解析失败：{e}")
            continue
        if d.get("schema") != "modkit.world/2":
            bad.append(f"{p.name}: schema={d.get('schema')}，应为 modkit.world/2")
    # 版本一致性
    init = ROOT / "software" / "modkit" / "__init__.py"
    if init.is_file():
        m = re.search(r'__version__\s*=\s*"([^"]+)"', init.read_text())
        if m:
            ver = m.group(1)
            if f"modkit-shell-v{ver}" not in sw:
                bad.append(f"sw.js CACHE 未同步到 v{ver}")
            world_js = (web / "world.js").read_text(encoding="utf-8")
            wm = re.search(r'var VERSION = "([^"]+)"', world_js)
            if wm and wm.group(1) != ver:
                bad.append(f"world.js VERSION={wm.group(1)}，包版本={ver}")
    return bad


def main() -> int:
    web = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "web").resolve()
    bad = check(web)
    if bad:
        print(f"Pages 资产校验失败（{len(bad)}）：")
        for x in bad:
            print("  -", x)
        return 1
    print(f"Pages 资产校验 PASS：{web}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
