#!/usr/bin/env python3
"""导出网页设计器所需的组件数据、预设装配和零件 STEP。

为什么不直接让浏览器读 cad/out：Pages 只发布 web/；而且静态页没有
Python/build123d。这里把"可读的组件元数据 + 已生成的 STEP"固化到 web/，
网页端只做装配求解、预览和导出，不在浏览器里假装跑 CAD 内核。

用法：
    python tools/export_web_design.py
    python tools/export_web_design.py --skip-models
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "software"))

from modkit import components as C  # noqa: E402

WEB = ROOT / "web"
DATA = WEB / "data"
MODELS = WEB / "models"


def safe(cid: str) -> str:
    return cid.replace(".", "_").replace("/", "_")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-models", action="store_true")
    args = ap.parse_args(argv)
    DATA.mkdir(parents=True, exist_ok=True)
    MODELS.mkdir(parents=True, exist_ok=True)

    comps = {}
    for c in C.by_category():
        d = c.as_dict()
        step_src = ROOT / "cad" / "out" / "components" / f"{safe(c.id)}.step"
        step_dst = MODELS / f"{safe(c.id)}.step"
        rel = f"models/{safe(c.id)}.step"
        if step_src.is_file() and not args.skip_models:
            shutil.copy2(step_src, step_dst)
        # 已有提交的 STEP 时保留；没有 CAD 输出的干净 checkout 也能生成数据。
        d["cad_file"] = rel if step_dst.is_file() else None
        comps[c.id] = d
    (DATA / "components.js").write_text(
        "window.MODKIT_COMPONENTS = " + json.dumps(comps, ensure_ascii=False, indent=1) + ";\n",
        encoding="utf-8")

    assemblies = {}
    for path in sorted((ROOT / "assemblies").glob("*.json")):
        assemblies[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    (DATA / "assemblies.js").write_text(
        "window.MODKIT_ASSEMBLIES = " + json.dumps(assemblies, ensure_ascii=False, indent=1) + ";\n",
        encoding="utf-8")

    print(f"组件 {len(comps)} → {DATA/'components.js'}")
    print(f"预设 {len(assemblies)} → {DATA/'assemblies.js'}")
    if not args.skip_models:
        print(f"STEP → {MODELS}（{len(list(MODELS.glob('*.step')))} 个）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
