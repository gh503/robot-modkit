"""多池/多机器人组合：批量研究 + 组合报告。"""

from __future__ import annotations

import json
import pathlib
from html import escape

from . import model, report
from .scenario import Study


def run_batch(files: list[str | pathlib.Path], out: str | pathlib.Path,
              calibration: dict | None = None) -> dict:
    d = pathlib.Path(out)
    d.mkdir(parents=True, exist_ok=True)
    rows, errors = [], []
    for f in files:
        p = pathlib.Path(f)
        try:
            s = Study.load(p)
            result = model.run(s, calibration=calibration)
            sub = d / p.stem
            paths = report.write(s, result, sub, calibration=calibration)
            r = result["results"]
            rows.append({
                "file": str(p), "study": s.name, "out": str(sub),
                "volume_m3": r["pool_volume_m3"], "time_min": r["total_time_min"],
                "energy_wh": r["energy_wh"], "coverage_pct": r["coverage_pct"],
                "cost_cny": r["cost_per_cleaning_cny"],
                "savings_cny": r["savings_per_cleaning_cny"],
                "payback_months": r["payback_savings_months"],
                "annual_net_cny": r["annual_net_after_depreciation_cny"],
                "inputs": s.to_dict(), "warnings": result.get("warnings", []),
                "paths": paths,
            })
        except Exception as e:
            errors.append({"file": str(p), "error": str(e)})
    summary = {
        "schema": "aquatwin.portfolio/1",
        "model_version": model.MODEL_VERSION,
        "calibrated": calibration is not None,
        "n": len(rows), "n_errors": len(errors),
        "studies": rows, "errors": errors,
        "totals": {
            "volume_m3": sum(r["volume_m3"] for r in rows),
            "time_min": sum(r["time_min"] for r in rows),
            "energy_wh": sum(r["energy_wh"] for r in rows),
            "annual_net_cny": sum(r["annual_net_cny"] for r in rows),
        },
        "means": {
            "time_min": (sum(r["time_min"] for r in rows) / len(rows)) if rows else None,
            "coverage_pct": (sum(r["coverage_pct"] for r in rows) / len(rows)) if rows else None,
            "cost_cny": (sum(r["cost_cny"] for r in rows) / len(rows)) if rows else None,
        },
    }
    (d / "portfolio.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                                      encoding="utf-8")
    (d / "portfolio.md").write_text(markdown(summary), encoding="utf-8")
    (d / "portfolio.html").write_text(html(summary), encoding="utf-8")
    return summary


def markdown(s: dict) -> str:
    L = ["# AquaTwin 组合研究", "",
         f"> {s['n']} 个场景，{s['n_errors']} 个失败；模型 `{s['model_version']}`；"
         f"{'已应用校准' if s['calibrated'] else '未校准'}。", "",
         "| 场景 | 体积 m³ | 时间 min | 能耗 Wh | 覆盖 % | 成本 ¥ | 节省 ¥ | 回收月 |",
         "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in s["studies"]:
        pay = "—" if r["payback_months"] is None else f"{r['payback_months']:.1f}"
        L.append(f"| {r['study']} | {r['volume_m3']:.2f} | {r['time_min']:.1f} | {r['energy_wh']:.1f} | "
                 f"{r['coverage_pct']:.1f} | {r['cost_cny']:.2f} | {r['savings_cny']:.2f} | {pay} |")
    L += ["", f"**合计**：体积 {s['totals']['volume_m3']:.2f} m³；时间 {s['totals']['time_min']:.1f} min；"
          f"能耗 {s['totals']['energy_wh']:.1f} Wh；年化净利 ¥{s['totals']['annual_net_cny']:.0f}。", ""]
    if s["errors"]:
        L += ["## 失败", ""] + [f"- `{e['file']}`：{e['error']}" for e in s["errors"]] + [""]
    L += ["## 边界", "",
          "- 组合汇总只是线性相加，不包含路线/空驶/人员共享等真实调度；",
          "- 价格/工资是场景假设；没有现场实测就不能对外承诺；",
          "- 物理闸门/现场验证：未做。", ""]
    return "\n".join(L)


def html(s: dict) -> str:
    rows = "".join(
        f"<tr><td>{escape(r['study'])}</td><td>{r['volume_m3']:.1f}</td><td>{r['time_min']:.1f}</td>"
        f"<td>{r['coverage_pct']:.1f}%</td><td>¥{r['cost_cny']:.2f}</td>"
        f"<td>¥{r['savings_cny']:.2f}</td></tr>" for r in s["studies"])
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>AquaTwin 组合研究</title>
<style>body{{font:14px/1.6 system-ui,sans-serif;max-width:1000px;margin:30px auto;padding:0 20px;color:#17212b}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:8px;border-bottom:1px solid #e6edf3;text-align:left}}
th{{color:#5b6b7c;font-weight:500}}td:nth-child(n+2){{text-align:right}}.note{{color:#5b6b7c;font-size:12px;margin-top:18px}}</style></head>
<body><h1>AquaTwin 组合研究</h1><p>{s['n']} 个场景；模型 {escape(s['model_version'])}；{'已校准' if s['calibrated'] else '未校准'}。</p>
<table><thead><tr><th>场景</th><th>体积 m³</th><th>时间 min</th><th>覆盖</th><th>成本</th><th>节省</th></tr></thead><tbody>{rows}</tbody></table>
<p class="note">线性汇总，不含路线/空驶/人员共享；不是报价或性能保证。物理闸门/现场验证未做。</p></body></html>'''
