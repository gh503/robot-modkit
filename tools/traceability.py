#!/usr/bin/env python3
"""需求追溯矩阵：需求 → 设计 → 验证 → 状态，并检查验证文件是否存在。

为什么需要：需求写在计划里，验证散在脚本/测试/文档里，中间最容易断链。
这个脚本把链子串起来，缺一环就报出来。

产物：docs/34-需求追溯.md
用法：python tools/traceability.py
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).parent.parent
DATA = ROOT / "hardware" / "requirements.json"
DOCS = ROOT / "docs"

STATUS = {"verified": "✅ 已验证", "pending": "🟡 待实测", "not_started": "⬜ 未开始"}


def main() -> int:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    reqs = data["requirements"]
    bad = []
    counts = {k: 0 for k in STATUS}

    for r in reqs:
        if r["status"] not in STATUS:
            bad.append(f"{r['id']} 状态非法：{r['status']}")
        else:
            counts[r["status"]] += 1
        if not (ROOT / r["verify"]).exists():
            bad.append(f"{r['id']} 验证文件不存在：{r['verify']}")

    total = len(reqs)
    lines = [
        "# 34 · 需求追溯矩阵（自动生成）",
        "",
        f"> 数据源 `hardware/requirements.json`，共 **{total}** 条需求。",
        f"> 已验证 **{counts['verified']}**、待实测 **{counts['pending']}**、"
        f"未开始 **{counts['not_started']}**。",
        "",
        "## 1. 总表",
        "",
        "| # | 需求 | 设计落点 | 验证 | 方法 | 状态 |",
        "|---|---|---|---|---|---|",
    ]
    for r in reqs:
        lines.append(f"| {r['id']} | {r['req']} | {r['design']} | "
                     f"`{r['verify']}` | {r['method']} | {STATUS[r['status']]} |")

    lines += [
        "",
        "## 2. 待实测的（必须做完才能说\"能生产\"）",
        "",
    ]
    pending = [r for r in reqs if r["status"] == "pending"]
    if pending:
        for r in pending:
            lines.append(f"- **{r['id']}** {r['req']} —— 用 `{r['verify']}` 出数据")
    else:
        lines.append("（无）")

    lines += [
        "",
        "## 3. 未开始的",
        "",
    ]
    todo = [r for r in reqs if r["status"] == "not_started"]
    if todo:
        for r in todo:
            lines.append(f"- **{r['id']}** {r['req']} —— 见 {r['verify']}")
    else:
        lines.append("（无）")

    lines += [
        "",
        "## 4. 怎么维护",
        "",
        "1. 加需求 → 在 `hardware/requirements.json` 加一条，`verify` 必须指向真实文件；",
        "2. 做完实测 → 把 `status` 改 `verified`，并补验证方法；",
        "3. 变更设计 → 检查对应需求是否还成立；",
        "4. 本文件由脚本生成，不要手改。",
        "",
    ]
    (DOCS / "34-需求追溯.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"需求 {total}：已验证 {counts['verified']} / 待实测 {counts['pending']} / "
          f"未开始 {counts['not_started']}")
    print("写出 docs/34-需求追溯.md")
    if bad:
        for b in bad:
            print("  -", b)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
