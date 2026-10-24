#!/usr/bin/env python3
"""来料（打印件）检验表：每个零件量什么、允许多少、抽多少。

Q1 的通用清单在 docs/18；这里给的是**逐件可测量的数字**，直接照着填。

产物：docs/35-来料检验表.md
用法：python tools/incoming.py
"""

from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).parent.parent
MFG = ROOT / "cad" / "out" / "manufacturing.json"
DOCS = ROOT / "docs"

TOL_MM = 0.3          # 外形尺寸允许偏差
MASS_TOL = 0.12       # 克重 ±12%
CRITICAL = {
    "chassis_left": "平面度 <1mm；对接孔 Ø3.6 通规",
    "chassis_right": "平面度 <1mm；对接孔 Ø3.6 通规",
    "chassis_joiner": "孔距 ±0.2；与两半能自由对接",
    "joint_base": "舵机座 Ø25.1 塞规；角柱孔 Ø4.2",
    "joint_lid": "与 joint_base 合拢无台阶",
    "jaw_fixed": "夹持面平面度 <0.3",
    "jaw_moving": "与定爪闭合间隙 <1mm",
    "output_disc": "花键中心孔；4×M3 孔位",
    "link_bar": "两端孔距 100±0.2；直线度 <0.5",
    "wheel_hub": "与舵盘花键配合不晃",
    "drive_bracket": "两腿平行度 <0.5",
    "camera_mount": "55° 角；M3 孔通",
}


def main() -> int:
    if not MFG.exists():
        raise SystemExit("缺 manufacturing.json，先跑 cad/manufacture.py")
    mfg = json.loads(MFG.read_text(encoding="utf-8"))

    rows = []
    for name, m in mfg.items():
        if m.get("tooling"):
            continue
        bb = m["bbox"]
        rows.append((name, m, bb))

    total = sum(m["qty"] for _, m, _ in rows)
    lines = [
        "# 35 · 来料检验表（自动生成）",
        "",
        f"> 由 `tools/incoming.py` 从可制造性报告生成；共 **{total} 件**（不含工装）。",
        f"> 外形允许 ±{TOL_MM}mm、克重 ±{MASS_TOL*100:.0f}%；孔用通止规/塞规，不靠卡尺估。",
        "",
        "## 1. 抽检规则",
        "",
        "| 批次 | 首件 | 后续 |",
        "|---|---|---|",
        "| ≤5 台 | 全检 | 全检 |",
        "| 6–20 台 | 全检 | 每 5 台抽 1 套 |",
        "| >20 台 | 全检 | 每 10 台抽 1 套 |",
        "",
        "抽检不合格 → 加倍抽样；仍不合格 → 整批全检并查打印机。",
        "",
        "## 2. 逐件表",
        "",
        "| 零件 | 数量 | 目标尺寸 X×Y×Z | 允许 | 克重 | 关键检查项 |",
        "|---|---:|---|---:|---:|---|",
    ]
    for name, m, bb in rows:
        dims = f"{bb[0]:.1f}×{bb[1]:.1f}×{bb[2]:.1f}"
        lines.append(f"| {name} | {m['qty']} | {dims} | ±{TOL_MM} | "
                     f"{m['mass_g']:.0f} g | {CRITICAL.get(name, '无特殊')} |")

    lines += [
        "",
        "## 3. 通用检查（每件都看）",
        "",
        "- [ ] 无层裂、无翘曲（平板玻璃上间隙 <0.5mm）",
        "- [ ] 孔内无支撑残留（Ø3.4 螺丝能自由穿过）",
        "- [ ] 关键面毛刺已去（手摸不刮）",
        "- [ ] 克重偏差 >12% → 查挤出/填充设置",
        "",
        "## 4. 记录",
        "",
        "每批一张表，填实测值（不是打勾）；不合格件贴红标单独放。",
        "记录与 `records/<serial>.json` 的 Q1 关联，返修时可追到具体件。",
        "",
        "## 5. 为什么用通止规",
        "",
        "卡尺量孔只能量到孔口，孔内缩口量不出来；Ø3.4/Ø3.6 通止规（或钻头柄）",
        "一插就知道能不能装，比卡尺快 5 倍。",
        "",
    ]
    (DOCS / "35-来料检验表.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(rows)} 种零件 / {total} 件；写出 docs/35-来料检验表.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
