"""工序卡：把 7 小时人工拆成可派工的步骤，并和 BOM 的 labor 对账。

为什么需要：
  · "装配 3 小时"没法派工，也没法算瓶颈；
  · 工位/工具/质检点不写清，换个人就做不出同样的东西；
  · 合计和 BOM 对不上，说明成本模型或工序漏了。

产物：docs/30-工序卡.md
用法：cd cad && ../.venv/bin/python routing.py
"""

from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).parent.parent
DATA = ROOT / "hardware" / "routing.json"
BOM = ROOT / "hardware" / "bom.json"
DOCS = ROOT / "docs"


def bom_labor_hours() -> float:
    bom = json.loads(BOM.read_text(encoding="utf-8"))
    return sum(v for k, v in bom["labor"].items()
               if k.endswith("h") and "rate" not in k and isinstance(v, (int, float)))


def main() -> int:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    ops = data["operations"]
    total_min = sum(o["min"] for o in ops)
    total_h = total_min / 60.0
    bom_h = bom_labor_hours()
    diff = abs(total_h - bom_h) / bom_h

    by_station: dict[str, float] = {}
    for o in ops:
        by_station[o["station"]] = by_station.get(o["station"], 0) + o["min"]

    lines = [
        "# 30 · 工序卡（自动生成）",
        "",
        f"> 数据源 `hardware/routing.json`；共 **{len(ops)} 道工序**、"
        f"**{total_min} 分钟（{total_h:.2f} h）**。",
        f"> BOM 人工 **{bom_h:.2f} h**，差异 **{diff*100:.1f}%**（要求 ≤10%）。",
        "> 分钟数是熟练工；新手整体 ×1.5，不要按这个数字承诺交期。",
        "",
        "## 1. 工时分布",
        "",
        "| 工位 | 分钟 | 占比 |",
        "|---|---:|---:|",
    ]
    for st, m in sorted(by_station.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {st} | {m} | {m/total_min*100:.0f}% |")
    lines += [
        "",
        "## 2. 工序表",
        "",
        "| # | 工位 | 工序 | 分钟 | 工具 | 质检点 | 关键 |",
        "|---|---|---|---:|---|---|:--:|",
    ]
    for o in ops:
        lines.append(f"| {o['id']} | {o['station']} | {o['op']} | {o['min']} | "
                     f"{o['tools']} | {o['qc']} | {'★' if o['key'] else ''} |")
    lines += [
        "",
        f"合计 **{total_min} min**（{total_h:.2f} h）。",
        "",
        "## 3. 关键工序（★）",
        "",
        "这些步骤做错，后面全白做 —— 必须由同一人完成并签字：",
        "",
    ]
    for o in ops:
        if o["key"]:
            lines.append(f"- **{o['id']} {o['op']}**（{o['qc']}）")
    lines += [
        "",
        "## 4. 瓶颈与并行",
        "",
        f"- 打印 {by_station.get('打印区', 0)} 分钟人工，但机时 14.3h，**机时才是瓶颈**；",
        "- 装配/电气/测试可串行一人完成；5 台以上建议拆成两个工位（装+电 / 测+包）；",
        "- 烧机 30 分钟无人值守，可与下一台的装配并行。",
        "",
        "## 5. 和成本的关系",
        "",
        "`hardware/bom.json` 的 labor 是成本口径（含返工余量），本表是派工口径；",
        "两者差 ≤10% 视为一致，超了说明有一边漏项。",
        "",
    ]
    (DOCS / "30-工序卡.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"工序 {len(ops)} 道，合计 {total_min} min = {total_h:.2f} h；BOM {bom_h:.2f} h，"
          f"差异 {diff*100:.1f}%")
    print("写出 docs/30-工序卡.md")
    if diff > 0.10:
        print("未通过：工序合计与 BOM 人工差 >10%")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
