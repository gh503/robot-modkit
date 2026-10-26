"""采购清单与“落地成本”估算。

BOM 里的单价是组件库的保守估算，不含运费/备件/线材端子；本模块把这些
显式加上，避免把 ¥968 的 BOM 当成 ¥1000 就能落地。

这是**规划模型**，不是供应商报价：价格、运费、税率都可由命令行覆盖；
写入文档时必须保留假设。
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Iterable

from .assembly import Report

DEFAULT_SHIPPING_CNY = 30.0
DEFAULT_SPARES_RATE = 0.08
DEFAULT_WIRE_CNY = 25.0
DEFAULT_TAX_RATE = 0.0


@dataclass(frozen=True)
class Landed:
    parts_cny: float
    spares_cny: float
    shipping_cny: float
    wire_cny: float
    tax_cny: float
    total_cny: float
    budget_cny: float | None
    spares_rate: float
    tax_rate: float
    target_bom_cny: float | None

    @property
    def over_cny(self) -> float:
        if self.budget_cny is None:
            return 0.0
        return max(0.0, self.total_cny - self.budget_cny)

    @property
    def within_budget(self) -> bool | None:
        if self.budget_cny is None:
            return None
        return self.total_cny <= self.budget_cny + 1e-9

    def as_dict(self) -> dict:
        return {
            "parts_cny": round(self.parts_cny, 1),
            "spares_cny": round(self.spares_cny, 1),
            "shipping_cny": round(self.shipping_cny, 1),
            "wire_cny": round(self.wire_cny, 1),
            "tax_cny": round(self.tax_cny, 1),
            "total_cny": round(self.total_cny, 1),
            "budget_cny": None if self.budget_cny is None else round(self.budget_cny, 1),
            "over_cny": round(self.over_cny, 1),
            "within_budget": self.within_budget,
            "spares_rate": self.spares_rate,
            "tax_rate": self.tax_rate,
            "target_bom_cny": None if self.target_bom_cny is None else round(self.target_bom_cny, 1),
        }


def estimate(report: Report, *, shipping: float = DEFAULT_SHIPPING_CNY,
             spares: float = DEFAULT_SPARES_RATE, wire: float = DEFAULT_WIRE_CNY,
             tax: float = DEFAULT_TAX_RATE) -> Landed:
    """BOM + 备件 + 运费 + 线材/端子 + 税。

    `target_bom_cny` 是反推：想让落地价 ≤ 预算，BOM 最多能到多少。
    打印件成本已经在 BOM 内（按耗材/工时估算），不再重复加。
    """
    if shipping < 0 or wire < 0 or not (0 <= spares < 1) or not (0 <= tax < 1):
        raise ValueError("运费/线材/税率不能为负，备件率必须在 [0,1)")
    parts = max(0.0, float(report.total_cost_cny))
    spares_cny = parts * spares
    tax_cny = (parts + spares_cny) * tax
    total = parts + spares_cny + shipping + wire + tax_cny
    budget = report.raw.get("budget_cny") if report.raw else None
    budget_f = float(budget) if budget is not None else None
    target = None
    if budget_f is not None:
        denom = (1.0 + spares) * (1.0 + tax)
        target = max(0.0, (budget_f - shipping - wire) / denom)
    return Landed(parts, spares_cny, shipping, wire, tax_cny, total,
                  budget_f, spares, tax, target)


def purchase_rows(report: Report, *, spares: float = DEFAULT_SPARES_RATE) -> list[dict]:
    """按 BOM 行生成**实际采购/打印数量**。

    备件率是预算里的现金储备，不是每一行都买双份：把 ¥5 的保险丝也翻倍
    会让清单变得不可执行。这里只给真实用量；备件预算在 `estimate()` 单列。
    """
    rows: list[dict] = []
    for b in report.bom:
        qty = int(b.qty)
        rows.append({
            "category": b.category,
            "name": b.name,
            "spec": b.spec,
            "qty": qty,
            "buy_qty": qty,
            "spare_qty": 0,
            "unit_cost": round(float(b.unit_cost), 2),
            "cost": round(float(b.unit_cost) * qty, 2),
            "note": "采购" if b.category == "purchased" else "打印/自制",
        })
    return rows


def to_markdown(report: Report, *, shipping: float = DEFAULT_SHIPPING_CNY,
                spares: float = DEFAULT_SPARES_RATE, wire: float = DEFAULT_WIRE_CNY,
                tax: float = DEFAULT_TAX_RATE) -> str:
    e = estimate(report, shipping=shipping, spares=spares, wire=wire, tax=tax)
    rows = purchase_rows(report, spares=spares)
    out = [f"# 采购与落地成本 · {report.name}", "",
           "## 成本",
           "",
           "| 项 | 金额 |",
           "|---|---:|",
           f"| BOM 物料 | ¥{e.parts_cny:.1f} |",
           f"| 备件 {e.spares_rate*100:.0f}% | ¥{e.spares_cny:.1f} |",
           f"| 运费 | ¥{e.shipping_cny:.1f} |",
           f"| 线材/端子/扎带 | ¥{e.wire_cny:.1f} |",
           f"| 税 {e.tax_rate*100:.0f}% | ¥{e.tax_cny:.1f} |",
           f"| **落地合计** | **¥{e.total_cny:.1f}** |", ""]
    if e.budget_cny is not None:
        if e.within_budget:
            out += [f"预算 ¥{e.budget_cny:.0f}：**余 ¥{e.budget_cny - e.total_cny:.1f}**。", ""]
        else:
            out += [f"预算 ¥{e.budget_cny:.0f}：**超 ¥{e.over_cny:.1f}**。",
                    f"要让落地价 ≤ ¥{e.budget_cny:.0f}，BOM 需 ≤ **¥{e.target_bom_cny:.1f}**"
                    f"（当前 ¥{e.parts_cny:.1f}，还要降 ¥{max(0.0, e.parts_cny - (e.target_bom_cny or 0)):.1f}）。", ""]
    out += ["## 采购件", "",
            "| 物料 | 规格 | 用量 | 采购量 | 单价 | 小计 |",
            "|---|---|---:|---:|---:|---:|"]
    for r in rows:
        if r["category"] != "purchased":
            continue
        out.append(f"| {r['name']} | {r['spec']} | {r['qty']} | {r['buy_qty']} | "
                   f"¥{r['unit_cost']:.2f} | ¥{r['cost']:.2f} |")
    out += ["", "## 打印/自制件", "",
            "| 物料 | 规格 | 数量 | 单价估算 | 小计 |",
            "|---|---|---:|---:|---:|"]
    for r in rows:
        if r["category"] != "printed":
            continue
        out.append(f"| {r['name']} | {r['spec']} | {r['qty']} | "
                   f"¥{r['unit_cost']:.2f} | ¥{r['cost']:.2f} |")
    out += ["", "## 假设与边界", "",
            "- BOM 单价是组件库保守估算，不是供应商实时报价；下单前按实际链接/库存复核。",
            "- 打印件成本已在 BOM 内（耗材/工时估算）；不含打印机折旧、失败重打。",
            "- 运费按单次合并下单估算；分多家/多次下单会增加。",
            "- 线材/端子/扎带按 ¥25 小包估算；线束长度未实测。",
            "- 采购量=BOM 实用量；备件按 8% 现金储备单列，不强制每行买双份。",
            "- 这是规划模型；物理闸门仍 0/5。", ""]
    return "\n".join(out)


def to_csv(report: Report, *, spares: float = DEFAULT_SPARES_RATE) -> str:
    rows = purchase_rows(report, spares=spares)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["类别", "物料", "规格", "用量", "采购/打印量", "备件", "单价", "小计", "备注"])
    for r in rows:
        w.writerow([r["category"], r["name"], r["spec"], r["qty"], r["buy_qty"],
                    r["spare_qty"], f"{r['unit_cost']:.2f}", f"{r['cost']:.2f}", r["note"]])
    return "\ufeff" + buf.getvalue()


def write_outputs(report: Report, out_dir: str, *, shipping: float = DEFAULT_SHIPPING_CNY,
                  spares: float = DEFAULT_SPARES_RATE, wire: float = DEFAULT_WIRE_CNY,
                  tax: float = DEFAULT_TAX_RATE) -> dict[str, str]:
    import pathlib
    d = pathlib.Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    md = d / "procure.md"
    csvp = d / "procure.csv"
    md.write_text(to_markdown(report, shipping=shipping, spares=spares, wire=wire, tax=tax),
                  encoding="utf-8")
    csvp.write_text(to_csv(report, spares=spares), encoding="utf-8")
    return {"markdown": str(md), "csv": str(csvp)}
