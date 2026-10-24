#!/usr/bin/env python3
"""检查 Markdown 里的相对链接/图片是否真的存在。

文档一多，链接腐烂比代码腐烂更快：改了文件名，没人会去翻 20 篇文档。
这个脚本进 CI，坏链接直接红。

用法：python tools/linkcheck.py [根目录]
"""

from __future__ import annotations

import pathlib
import re
import sys

LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
SKIP_PREFIX = ("http://", "https://", "mailto:", "#", "tel:")


def check(root: pathlib.Path) -> tuple[int, list[str]]:
    files = sorted(root.rglob("*.md"))
    bad: list[str] = []
    checked = 0
    for md in files:
        if any(part in (".git", "node_modules", ".venv") for part in md.parts):
            continue
        text = md.read_text(encoding="utf-8", errors="ignore")
        for raw in LINK.findall(text):
            target = raw.split("#", 1)[0].strip()
            if not target or target.startswith(SKIP_PREFIX):
                continue
            checked += 1
            # 去掉行内锚点/引用，处理 %20
            p = (md.parent / target.replace("%20", " ")).resolve()
            if not p.exists():
                bad.append(f"{md.relative_to(root)} → {target}")
    return checked, bad


def main() -> int:
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    checked, bad = check(root)
    print(f"检查 {checked} 个相对链接")
    if bad:
        print(f"坏链接 {len(bad)}：")
        for b in bad:
            print("  -", b)
        return 1
    print("全部存在")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
