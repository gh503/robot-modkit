"""从 BOM 生成可下单清单：数量、单价、小计、链接、货期、预算差额。

价格是估算，下单前以供应商页面为准；脚本只保证"数量与档位"和 BOM 一致。
"""

from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
BOM = ROOT / "hardware" / "bom.json"
SPARE = 0.08


def build(tier: str | None = None, budget: float = 1000.0) -> dict:
    b = json.loads(BOM.read_text(encoding="utf-8"))
    items = {x["id"]: x for x in b["items"]}
    tiers = b["tiers"]
    names = [tier] if tier else list(tiers)
    rows = []
    for name in names:
        if name not in tiers:
            raise SystemExit(f"没有这个档位：{name}\n可选：{', '.join(tiers)}")
        detail = []
        material = 0.0
        lead = 0
        for iid in tiers[name]:
            it = items[iid]
            sub = it["qty"] * it["price"][0]
            material += sub
            lead = max(lead, it.get("lead_days", 0))
            detail.append({**it, "subtotal": sub})
        shipping = material * SPARE
        rows.append({
            "tier": name, "items": detail, "material": round(material, 2),
            "spare": round(shipping, 2),
            "total": round(material + shipping, 2),
            "over_budget": round(material + shipping - budget, 2),
            "lead_days": lead,
        })
    return {"budget": budget, "tiers": rows}


def markdown(r: dict) -> str:
    lines = [f"# 下单清单（预算 ¥{r['budget']:.0f}）", "",
             "> 价格来自 `hardware/bom.json` 估算，下单前以供应商页面为准；",
             "> 含 8% 备件/运费余量；不含 3D 打印耗材与人工。", ""]
    lines += ["| 档位 | 物料 | 含 8% 余量 | 与预算差 | 最长货期 |",
              "|---|---:|---:|---:|---:|"]
    for t in r["tiers"]:
        diff = "超" if t["over_budget"] > 0 else "余"
        lines.append(f"| {t['tier']} | ¥{t['material']:.0f} | ¥{t['total']:.0f} | "
                     f"{diff} ¥{abs(t['over_budget']):.0f} | {t['lead_days']} 天 |")
    lines.append("")
    for t in r["tiers"]:
        lines += [f"## {t['tier']}", "",
                  "| 物料 | 规格 | 数量 | 单价 | 小计 | 供应商 | 货期 |",
                  "|---|---|---:|---:|---:|---|---:|"]
        for it in t["items"]:
            lines.append(f"| {it['name']} | {it['spec']} | {it['qty']} | "
                         f"¥{it['price'][0]} | ¥{it['subtotal']:.0f} | "
                         f"{it['supplier']} | {it.get('lead_days', 0)} 天 |")
        lines += ["", f"物料 ¥{t['material']:.0f} + 8% 余量 ¥{t['spare']:.0f} = "
                  f"**¥{t['total']:.0f}**", ""]
    lines += ["## 预算判断", "",
              "- B 推荐整机是「能跑导航+视觉+任务」的完整配置；",
              "- E 是压到 ¥1000 内的降配：舵机换省钱型号、ESP32 换 SuperMini、",
              "  电池换省钱组，**力矩/堵转余量未实测**，必须先做台架；",
              "- A 是最小可动，USB 供电、无树莓派/相机，只能做底盘与臂的基础调试。",
              "",
              "选购与替代判据见 [24-采购与供应链](24-采购与供应链.md)。", ""]
    return "\n".join(lines)


def main(tier: str | None = None, budget: float = 1000.0,
         out: str | None = None) -> int:
    r = build(tier, budget)
    text = markdown(r)
    if out:
        pathlib.Path(out).write_text(text, encoding="utf-8")
        print(f"已写入 {out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier")
    ap.add_argument("--budget", type=float, default=1000.0)
    ap.add_argument("--out")
    a = ap.parse_args()
    raise SystemExit(main(a.tier, a.budget, a.out))
