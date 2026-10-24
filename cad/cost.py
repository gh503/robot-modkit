"""成本模型：把"做一台要多少钱"算成可复现的表，而不是拍脑袋。

输入：
    hardware/bom.json          采购件、三档配置、人工与损耗
    cad/out/manufacturing.json 打印质量与时长（由 manufacture.py 生成）

输出：
    docs/17-成本模型.md
    cad/out/cost.json

用法：cd cad && ../.venv/bin/python cost.py [--qty 1,5,20]
"""

from __future__ import annotations

import argparse
import json
import pathlib

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parent
BOM = ROOT / "hardware" / "bom.json"
OUT = HERE / "out"


def load():
    bom = json.loads(BOM.read_text(encoding="utf-8"))
    mfg = json.loads((OUT / "manufacturing.json").read_text(encoding="utf-8"))
    return bom, mfg


def unit_price(item: dict, qty: int) -> float:
    """按 1/5/20 的阶梯价插值（超过 20 用最低价）。"""
    breaks = item["price"]
    if qty <= 1:
        return breaks[0]
    if qty <= 5:
        return breaks[0] + (breaks[1] - breaks[0]) * (qty - 1) / 4
    if qty <= 20:
        return breaks[1] + (breaks[2] - breaks[1]) * (qty - 5) / 15
    return breaks[2]


def labour_hours(bom: dict) -> float:
    """只统计以 h 结尾的工时项，别把 rate_cny_per_h 也加进去。"""
    return sum(v for k, v in bom["labor"].items()
               if k.endswith(" h") and isinstance(v, (int, float)))


def compute(bom: dict, mfg: dict, tier_ids: list[str], qty: int, learning: float = 0.92) -> dict:
    """先算单台成本，再乘数量；阶梯价按批量取。"""
    items = {i["id"]: i for i in bom["items"]}
    parts_unit = 0.0
    lines = []
    for tid in tier_ids:
        it = items[tid]
        p = unit_price(it, qty) * it["qty"]
        parts_unit += p
        lines.append((it, it["qty"], unit_price(it, qty), p))

    mass = sum(v["mass_g"] * v.get("qty", 1) for v in mfg.values())
    hours = sum(v["hours"] * v.get("qty", 1) for v in mfg.values())
    fil_price = unit_price(items["filament"], qty)
    filament_unit = mass / 1000.0 * fil_price
    machine_unit = hours * bom["machine"]["printer_cny_per_h"]

    rate = bom["labor"]["rate_cny_per_h"]
    base_hours = labour_hours(bom)
    factor = learning ** (max(0, qty - 1).bit_length() - 1) if qty > 1 else 1.0
    labor_unit = base_hours * rate * factor

    overhead = bom["overhead"]
    subtotal = parts_unit + filament_unit + machine_unit + labor_unit
    scrap_unit = subtotal * overhead["scrap_rate"]
    ship_unit = overhead["shipping_per_unit"] + overhead["packaging_per_unit"]
    per_unit = subtotal + scrap_unit + ship_unit
    return {
        "qty": qty,
        "parts_cost": round(parts_unit, 1),
        "filament_g": round(mass, 0),
        "filament_cost": round(filament_unit, 1),
        "print_hours": round(hours, 1),
        "machine_cost": round(machine_unit, 1),
        "labor_hours": round(base_hours * factor, 1),
        "labor_cost": round(labor_unit, 1),
        "scrap": round(scrap_unit, 1),
        "shipping_packaging": round(ship_unit, 1),
        "total": round(per_unit * qty, 0),
        "per_unit": round(per_unit, 0),
        "lines": lines,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--qty", default="1,5,20")
    args = ap.parse_args()
    qtys = [int(x) for x in args.qty.split(",")]

    bom, mfg = load()
    results = {}
    for tier, ids in bom["tiers"].items():
        results[tier] = [compute(bom, mfg, ids, q) for q in qtys]

    # 自己动手版：人工费率设 0，便于和"买套件"对比
    for tier, ids in bom["tiers"].items():
        bom_self = json.loads(json.dumps(bom))
        bom_self["labor"]["rate_cny_per_h"] = 0
        results[tier + "（自己动手）"] = [compute(bom_self, mfg, ids, q) for q in qtys]

    print(f"{'配置':<34}{'数量':>4}{'物料':>9}{'打印':>8}{'人工':>8}{'其他':>8}{'合计':>10}{'单价':>9}")
    for tier, rows in results.items():
        for r in rows:
            other = r["scrap"] + r["shipping_packaging"]
            print(f"{tier:<34}{r['qty']:>4}{r['parts_cost']:>9.0f}{r['machine_cost']:>8.0f}"
                  f"{r['labor_cost']:>8.0f}{other:>8.0f}{r['total']:>10.0f}{r['per_unit']:>9.0f}")

    (OUT / "cost.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    tier_a = results["A 最小可动（USB 供电，无线束）"][0]
    tier_b = results["B 推荐整机（电池 + 树莓派）"][0]
    self_a = results["A 最小可动（USB 供电，无线束）（自己动手）"][0]
    self_b = results["B 推荐整机（电池 + 树莓派）（自己动手）"][0]
    lines = [
        "# 17 · 成本模型（自动生成）",
        "",
        "> 由 `cad/cost.py` 读取 `hardware/bom.json` 与 `cad/out/manufacturing.json` 计算。",
        "> 价格是 2026-10 的国内零售价（含税、不含运费），批量按 1/5/20 阶梯。",
        "",
        "## 结论",
        "",
        f"- **A 档（最小可动）**：约 **¥{tier_a['total']:.0f}**/台，物料 ¥{tier_a['parts_cost']:.0f}"
        f" + 打印 ¥{tier_a['machine_cost']:.0f} + 人工 {tier_a['labor_hours']:.1f}h/¥{tier_a['labor_cost']:.0f}"
        f" + 损耗运费 ¥{tier_a['scrap'] + tier_a['shipping_packaging']:.0f}",
        f"- **B 档（推荐整机）**：约 **¥{tier_b['total']:.0f}**/台",
        f"- 5 台批量：B 档单价约 **¥{results[list(results)[1]][1]['per_unit']:.0f}**"
        f"（物料降 {100 * (1 - results[list(results)[1]][1]['parts_cost'] / (tier_b['parts_cost'])):.0f}%，人工按学习曲线降）",
        "",
        f"- **自己动手**（人工不计）：A 档 **¥{self_a['per_unit']:.0f}**、B 档 **¥{self_b['per_unit']:.0f}**",
        "",
        "> 说明：人工按 ¥60/h 计。自己动手不算钱的话，把 labor 的 rate 改成 0 即可 ——",
        "> 这也是和「买套件」对比的口径：套件卖 ¥2000+ 时，你省下的是人工与试错。",
        "",
        "## 明细",
        "",
        "| 配置 | 数量 | 物料 | 打印机时 | 人工 | 损耗+运费 | 合计 | 单价 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for tier, rows in results.items():
        for r in rows:
            lines.append(
                f"| {tier} | {r['qty']} | ¥{r['parts_cost']:.0f} | ¥{r['machine_cost']:.0f} | "
                f"¥{r['labor_cost']:.0f} | ¥{r['scrap'] + r['shipping_packaging']:.0f} | "
                f"**¥{r['total']:.0f}** | ¥{r['per_unit']:.0f} |")

    lines += ["", "## B 档物料清单（单台）", "", "| 件 | 规格 | 数量 | 单价 | 小计 | 供应商 |", "|---|---|---:|---:|---:|---|"]
    for it, q, p, sub in results[list(results)[1]][0]["lines"]:
        lines.append(f"| {it['name']} | {it['spec']} | {q} | ¥{p:.0f} | ¥{sub:.0f} | {it['supplier']} |")

    lines += [
        "",
        "## 打印成本的口径",
        "",
        f"- 耗材：**{tier_b['filament_g']:.0f} g** PETG → ¥{tier_b['filament_cost']:.0f}"
        f"（按 ¥90/kg；实际含支撑与失败重打）",
        f"- 机时：**{tier_b['print_hours']:.1f} h** × ¥{bom['machine']['printer_cny_per_h']}/h = ¥{tier_b['machine_cost']:.0f}",
        "- 机时按电费+折旧粗算；如果用共享打印店（¥0.5–1/g），按重量算更准："
        f"{tier_b['filament_g']:.0f} g × ¥0.7 ≈ ¥{tier_b['filament_g']*0.7:.0f}",
        "",
        "## 怎么改",
        "",
        "- 换供应商：改 `hardware/bom.json` 里对应条目的 `price` 与 `supplier`",
        "- 加配置：在 `tiers` 里加一个数组，列 item id",
        "- 改人工费率：`labor.rate_cny_per_h`",
        "",
    ]
    (ROOT / "docs" / "17-成本模型.md").write_text("\n".join(lines), encoding="utf-8")
    # 自检：批量单价不能比单件贵；B 档不能比 A 档便宜
    problems = []
    for tier, rows in results.items():
        for a, b in zip(rows, rows[1:]):
            if b["per_unit"] > a["per_unit"] + 1:
                problems.append(f"{tier}: 数量 {b['qty']} 的单价 {b['per_unit']} > {a['qty']} 的 {a['per_unit']}")
    a1 = results["A 最小可动（USB 供电，无线束）"][0]["per_unit"]
    b1 = results["B 推荐整机（电池 + 树莓派）"][0]["per_unit"]
    if b1 <= a1:
        problems.append(f"B 档 {b1} 不高于 A 档 {a1}，配置或价格有问题")

    print("\n写出 docs/17-成本模型.md 与 cad/out/cost.json")
    if problems:
        print("自检失败：")
        for x in problems:
            print("  -", x)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())