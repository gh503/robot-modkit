#!/usr/bin/env python3
"""跨文件一致性：文档目录、BOM、可制造性报告必须互相对得上。

三类检查：
1. docs/README.md 是否链接了所有编号文档（防止"写了没人找得到"）；
2. BOM 的 tier 是否引用了不存在的件、必配件是否被漏掉、阶梯价是否单调；
3. manufacturing.json 里的零件是否有非零数量与合理克重/时长。

用法：python tools/consistency.py
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).parent.parent
DOCS = ROOT / "docs"
BOM = ROOT / "hardware" / "bom.json"
MFG = ROOT / "cad" / "out" / "manufacturing.json"


def check_doc_index() -> list[str]:
    readme = (DOCS / "README.md").read_text(encoding="utf-8")
    bad = []
    for md in sorted(DOCS.glob("[0-9][0-9]-*.md")):
        name = md.name
        if name.startswith("99"):
            continue
        if name not in readme:
            bad.append(f"docs/README.md 没有链接 {name}")
    return bad


def check_bom() -> list[str]:
    d = json.loads(BOM.read_text(encoding="utf-8"))
    ids = {i["id"] for i in d["items"]}
    tiers = d.get("tiers", {})
    bad = []
    if not tiers:
        bad.append("BOM 没有 tier")
    for tier, members in tiers.items():
        for m in members:
            if m not in ids:
                bad.append(f"tier「{tier}」引用了不存在的件 {m}")
    a_or_b = set(tiers.get("A 最小可动（USB 供电，无线束）", [])) | set(
        tiers.get("B 推荐整机（电池 + 树莓派）", []))
    for it in d["items"]:
        if it.get("essential") and it["id"] not in a_or_b:
            bad.append(f"必配件 {it['id']} 不在 A/B 档里")
    for it in d["items"]:
        p = it.get("price") or []
        if len(p) >= 2 and not (p[0] >= p[1] >= p[-1]):
            bad.append(f"{it['id']} 阶梯价不单调 {p}")
    return bad


def check_manufacturing() -> list[str]:
    if not MFG.exists():
        return ["缺 manufacturing.json（先跑 cad/manufacture.py）"]
    d = json.loads(MFG.read_text(encoding="utf-8"))
    bad = []
    for name, m in d.items():
        if m.get("qty", 0) <= 0:
            bad.append(f"{name} 数量为 0")
        if not (0.5 <= m.get("mass_g", 0) <= 400):
            bad.append(f"{name} 克重异常 {m.get('mass_g')}")
        if not (0.01 <= m.get("hours", 0) <= 12):
            bad.append(f"{name} 时长异常 {m.get('hours')}")
        if len(m.get("bbox", [])) != 3:
            bad.append(f"{name} 缺 bbox")
    return bad


def main() -> int:
    groups = {"文档索引": check_doc_index(), "BOM": check_bom(),
              "可制造性": check_manufacturing()}
    total = 0
    for name, errs in groups.items():
        total += len(errs)
        if errs:
            print(f"[FAIL] {name}")
            for e in errs:
                print("   -", e)
        else:
            print(f"[PASS] {name}")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
