"""AquaTwin 输出：metrics / coverage / report / dashboard。"""

from __future__ import annotations

import json
import pathlib
from html import escape

from . import coverage as cv
from .model import sensitivity
from .scenario import Study


def _f(v, n=2):
    if v is None:
        return "—"
    return f"{v:.{n}f}"


def write(study: Study, result: dict, out: str | pathlib.Path,
          calibration: dict | None = None, measurements=None) -> dict:
    d = pathlib.Path(out)
    d.mkdir(parents=True, exist_ok=True)
    cov = cv.Coverage(**result["coverage"])
    study.save(d / "study.json")
    (d / "metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                     encoding="utf-8")
    cv.write_csv(cov, d / "coverage.csv")
    cv.write_svg(cov, study.pool, d / "coverage.svg")
    (d / "report.md").write_text(markdown(study, result), encoding="utf-8")
    (d / "dashboard.html").write_text(dashboard(study, result), encoding="utf-8")
    (d / "quote.html").write_text(quote(study, result), encoding="utf-8")
    paths = {"metrics": str(d / "metrics.json"), "report": str(d / "report.md"),
             "coverage_csv": str(d / "coverage.csv"), "coverage_svg": str(d / "coverage.svg"),
             "dashboard": str(d / "dashboard.html"), "quote": str(d / "quote.html"),
             "study": str(d / "study.json")}
    if calibration is not None:
        (d / "calibration.json").write_text(json.dumps(calibration, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8")
        paths["calibration"] = str(d / "calibration.json")
    if measurements is not None:
        measurements.save(d / "measurements.json")
        paths["measurements"] = str(d / "measurements.json")
        from . import calibrate as cb
        (d / "validation.md").write_text(cb.markdown(study, measurements, calibration or {}),
                                         encoding="utf-8")
        paths["validation"] = str(d / "validation.md")
    return paths


def markdown(study: Study, result: dict) -> str:
    r = result["results"]
    p, rob, ft, ec = study.pool, study.robot, study.filter, study.economics
    L = [f"# AquaTwin 研究：{study.name}", "",
         study.description or "", "",
         "## 结论（先看这 5 行）", "",
         f"- 单次清洁 **{_f(r['total_time_min'], 1)} min**（其中补电 {_f(r['charge_time_min'],1)} min），"
         f"覆盖率 **{_f(r['coverage_pct'],1)}%**；",
         f"- 能耗 **{_f(r['energy_wh'],1)} Wh**，运行成本 **¥{_f(r['operating_cost_cny'])}**/次；",
         f"- 含折旧成本 **¥{_f(r['cost_per_cleaning_cny'])}**/次；服务价 ¥{_f(r['service_price_cny'])}，"
         f"单次毛利 **¥{_f(r['margin_per_cleaning_cny'])}**；",
         f"- 相对人工节省 **¥{_f(r['savings_per_cleaning_cny'])}**/次；"
         f"设备回收期（按节省）**{_f(r['payback_savings_months'],1)} 个月**；",
         f"- 年化净利（扣折旧）**¥{_f(r['annual_net_after_depreciation_cny'],0)}**；"
         f"1 年 ROI **{_f(r['roi_1y_pct'],1)}%**。", "",
         "> 以上是**场景假设**下的工程/经济模型，不是实测，也不是报价。", "",
         (f"> 已应用校准：`{result['calibration']['time_scale']:.3f}` / "
          f"`{result['calibration']['energy_scale']:.3f}` / "
          f"`{result['calibration']['pressure_scale']:.3f}`；模型 `{result.get('model_version','—')}`。"
          if result.get("calibration", {}).get("applied")
          else "> 未应用实测校准；结论仅代表模型假设。"), "",
         "## 输入", "",
         "| 输入 | 值 |", "|---|---|",
         f"| 泳池 | {p.length_m:g}×{p.width_m:g}×{p.depth_m:g} m；面积 {p.area_m2:.2f} m²；"
         f"{p.water_temp_c:g}°C；{p.salinity_ppt:g} ppt |",
         f"| 水体积 | {_f(r['pool_volume_m3'])} m³；{_f(r['water_mass_kg'],0)} kg；ρ={_f(r['water_density_kg_m3'],1)} kg/m³ |",
         f"| 机器人 | 宽 {rob.swath_m:g} m（重叠 {rob.overlap*100:g}%）；速度 {rob.speed_m_s:g} m/s；电池 {rob.battery_wh:g} Wh |",
         f"| 泵 | {rob.pump_flow_m3_s*1000:g} L/s；扬程 {rob.pump_head_m:g} m；效率 {rob.pump_efficiency:g} |",
         f"| 过滤 | 捕获 {ft.capture_efficiency*100:g}%；容量 {ft.capacity_g:g} g；反冲洗 ¥{ft.backwash_cost_cny:g}/次 |",
         f"| 经济 | 电 ¥{ec.electricity_cny_kwh:g}/kWh；人工 ¥{ec.labor_cny_h:g}/h；"
         f"设备 ¥{ec.robot_capex_cny:g}；{ec.cleanings_per_week:g} 次/周 |", "",
         "## 覆盖与时间", "",
         "| 指标 | 值 |", "|---|---|",
         f"| 有效清洁宽度 | {_f(r['effective_swath_m'],3)} m |",
         f"| lane 数 / 转向 | {r['lanes']} / {r['turns']} |",
         f"| 路径长度 | {_f(r['path_length_m'],1)} m |",
         f"| 覆盖率 | {_f(r['coverage_pct'],1)}% |",
         f"| 纯作业 / 总时间 | {_f(r['active_time_min'],1)} / **{_f(r['total_time_min'],1)} min** |",
         f"| 补电次数 | {r['charges']}（{_f(r['charge_time_min'],1)} min） |", "",
         "## 流体/动力", "",
         "| 指标 | 值 |", "|---|---|",
         f"| 阻力（{rob.speed_m_s:g} m/s） | {_f(r['drag_n'],3)} N |",
         f"| 驱动+刷+电子 | {_f(r['drive_power_w'],1)} W |",
         f"| 泵水力/轴功率 | {_f(r['pump_hydraulic_w'],1)} / {_f(r['pump_shaft_w'],1)} W |",
         f"| 总功率 | {_f(r['total_power_w'],1)} W |",
         f"| 能耗 | {_f(r['energy_wh'],1)} Wh（{_f(r['energy_kwh'],3)} kWh） |", "",
         "## 过滤", "",
         "| 指标 | 值 |", "|---|---|",
         f"| 碎屑捕集 | {_f(r['debris_captured_g'],1)} g |",
         f"| 过滤循环/反冲洗 | {_f(r['filter_cycles'],2)} 次 |",
         f"| 压升 | {_f(r['filter_pressure_rise_kpa'],1)} kPa |",
         f"| 反冲洗水 | {_f(r['backwash_water_l'],0)} L |", "",
         "## 成本与回收", "",
         "| 指标 | 值 |", "|---|---|",
         f"| 电费/反冲洗/监管/维护 | ¥{_f(r['energy_cost_cny'])} / ¥{_f(r['backwash_cost_cny'])} / "
         f"¥{_f(r['supervision_cost_cny'])} / ¥{_f(r['maintenance_per_cleaning_cny'])} |",
         f"| 运行成本 / 含折旧 | ¥{_f(r['operating_cost_cny'])} / **¥{_f(r['cost_per_cleaning_cny'])}** |",
         f"| 人工对照 | ¥{_f(r['manual_cost_cny'])}/次 |",
         f"| 单次节省 | ¥{_f(r['savings_per_cleaning_cny'])} |",
         f"| 年清洁次数 | {_f(r['annual_cleanings'],0)} |",
         f"| 年收入/年运行利润 | ¥{_f(r['annual_revenue_cny'],0)} / ¥{_f(r['annual_profit_cny'],0)} |",
         f"| 回收期（服务利润/节省） | {_f(r['payback_service_months'],1)} / "
         f"{_f(r['payback_savings_months'],1)} 个月 |",
         f"| 1 年 ROI（扣折旧） | {_f(r['roi_1y_pct'],1)}% |", "",
         "## 敏感性", "",
         "| 变体 | 时间 min | 能耗 Wh | 成本 ¥ | 覆盖 % |", "|---|---:|---:|---:|---:|"]
    for row in sensitivity(study):
        L.append(f"| {row['variant']} | {_f(row['time_min'],1)} | {_f(row['energy_wh'],1)} | "
                 f"{_f(row['cost_cny'])} | {_f(row['coverage_pct'],1)} |")
    if result.get("calibration", {}).get("applied"):
        c = result["calibration"]
        L += ["", "## 校准因子", "",
              "| 因子 | 值 |", "|---|---:|",
              f"| time_scale | {_f(c['time_scale'],3)} |",
              f"| setup_min | {_f(c['setup_min'],2)} min |",
              f"| energy_scale | {_f(c['energy_scale'],3)} |",
              f"| pressure_scale | {_f(c['pressure_scale'],3)} |"]
    if result.get("warnings"):
        L += ["", "## 警告", ""] + [f"- {x}" for x in result["warnings"]]
    L += ["", "## 模型与边界", ""] + [f"- {x}" for x in result.get("assumptions", [])]
    L += ["", "- 物理闸门/现场验证：**未做**；本报告不能作为性能保证、报价或安全认证。", ""]
    return "\n".join(L)


def dashboard(study: Study, result: dict) -> str:
    """自包含 HTML：给销售/客户看的单页；不依赖网络。"""
    r = result["results"]
    p = study.pool
    cards = [
        ("单次时间", f"{_f(r['total_time_min'],1)} min", "含补电"),
        ("覆盖率", f"{_f(r['coverage_pct'],1)}%", f"{r['lanes']} lanes"),
        ("能耗", f"{_f(r['energy_wh'],1)} Wh", "单次"),
        ("单次成本", f"¥{_f(r['cost_per_cleaning_cny'])}", "含折旧"),
        ("单次节省", f"¥{_f(r['savings_per_cleaning_cny'])}", "相对人工"),
        ("回收期", f"{_f(r['payback_savings_months'],1)} 月", "按节省"),
    ]
    card_html = "".join(
        f'<div class="card"><span>{escape(k)}</span><strong>{escape(v)}</strong><em>{escape(s)}</em></div>'
        for k, v, s in cards)
    # 成本条：运行 vs 折旧 vs 人工
    total = max(1.0, r["manual_cost_cny"])
    op = r["operating_cost_cny"] / total * 100
    dep = r["depreciation_per_cleaning_cny"] / total * 100
    lab = r["manual_cost_cny"] / total * 100
    bars = (f'<div class="bar"><span>运行</span><i style="width:{min(100,op):.1f}%"></i>'
            f'<b>¥{_f(r["operating_cost_cny"])}</b></div>'
            f'<div class="bar"><span>折旧</span><i style="width:{min(100,dep):.1f}%"></i>'
            f'<b>¥{_f(r["depreciation_per_cleaning_cny"])}</b></div>'
            f'<div class="bar manual"><span>人工</span><i style="width:{min(100,lab):.1f}%"></i>'
            f'<b>¥{_f(r["manual_cost_cny"])}</b></div>')
    data = json.dumps(result, ensure_ascii=False).replace("</", "<\\/")
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AquaTwin · {escape(study.name)}</title>
<style>
:root{{--bg:#071018;--panel:#0d1a24;--line:#1d3445;--text:#e8f3fb;--muted:#8fa8ba;--aqua:#47c9e5;--ok:#3ddc97;--warn:#f0b35b}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(900px 420px at 15% -10%,#12384a,transparent 60%),var(--bg);color:var(--text);font:14px/1.5 system-ui,-apple-system,"Noto Sans CJK SC",sans-serif}}
header{{padding:22px 28px;border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:baseline;flex-wrap:wrap}}
h1{{font-size:20px;margin:0}}header span{{color:var(--muted);font-size:12px}}main{{max-width:1100px;margin:0 auto;padding:22px 28px 50px}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}@media(max-width:800px){{.grid{{grid-template-columns:1fr 1fr}}}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px}}
.card span{{display:block;color:var(--muted);font-size:12px}}.card strong{{display:block;font-size:24px;margin:6px 0 2px;color:var(--aqua)}}.card em{{font-style:normal;color:var(--muted);font-size:11px}}
h2{{font-size:13px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin:26px 0 10px}}
.bar{{display:grid;grid-template-columns:70px 1fr 80px;gap:10px;align-items:center;margin:7px 0;font-size:12px}}
.bar i{{display:block;height:10px;border-radius:5px;background:var(--aqua);min-width:2px}}.bar.manual i{{background:var(--warn)}}
.bar b{{text-align:right;font-weight:500;color:var(--muted)}}.note{{color:var(--muted);font-size:12px;margin-top:18px;border-top:1px solid var(--line);padding-top:12px}}
</style></head><body>
<header><h1>AquaTwin · {escape(study.name)}</h1><span>{p.length_m:g}×{p.width_m:g}×{p.depth_m:g} m · {p.water_temp_c:g}°C · {p.salinity_ppt:g} ppt</span></header>
<main>
<div class="grid">{card_html}</div>
<h2>单次成本对照</h2>{bars}
<h2>结论</h2><p>覆盖率 {_f(r['coverage_pct'],1)}%，路径 {_f(r['path_length_m'],1)} m；
过滤压升 {_f(r['filter_pressure_rise_kpa'],1)} kPa；年化净利（扣折旧）
¥{_f(r['annual_net_after_depreciation_cny'],0)}。</p>
<p class="note">这是场景假设下的降阶模型，不是现场实测、报价或性能保证。模型 {escape(result.get('model_version','—'))}；{'已校准（仅该数据集）' if result.get('calibration',{}).get('applied') else '未校准'}。
完整输入/公式/敏感性见 <code>report.md</code>；机器可读结果见 <code>metrics.json</code>。</p>
</main>
<script type="application/json" id="result">{data}</script>
</body></html>'''


def quote(study: Study, result: dict, customer: str = "", valid_days: int = 30) -> str:
    """可打印的客户报价页；不是合同，不承诺性能。"""
    r = result["results"]
    rows = [
        ("单次清洁时间", f"{_f(r['total_time_min'],1)} min"),
        ("单次运行成本", f"¥{_f(r['operating_cost_cny'])}"),
        ("含折旧成本", f"¥{_f(r['cost_per_cleaning_cny'])}"),
        ("建议服务价", f"¥{_f(r['service_price_cny'])}"),
        ("单次毛利", f"¥{_f(r['margin_per_cleaning_cny'])}"),
        ("相对人工节省", f"¥{_f(r['savings_per_cleaning_cny'])}"),
        ("设备回收期（按节省）", f"{_f(r['payback_savings_months'],1)} 个月"),
        ("覆盖率", f"{_f(r['coverage_pct'],1)}%"),
    ]
    tr = "".join(f"<tr><th>{escape(k)}</th><td>{escape(v)}</td></tr>" for k, v in rows)
    calibrated = result.get("calibration", {}).get("applied")
    cal_note = ("<b>已应用校准，但仅适用于本数据集覆盖的池型/机器人。</b>"
                if calibrated else "<b>本报价未应用实测校准。</b>")
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AquaTwin 报价 · {escape(study.name)}</title>
<style>
body{{font:14px/1.6 system-ui,-apple-system,"Noto Sans CJK SC",sans-serif;color:#17212b;max-width:820px;margin:32px auto;padding:0 24px}}
h1{{font-size:24px;margin:0 0 4px}}h2{{font-size:15px;margin:24px 0 8px;border-bottom:1px solid #d8e0e8;padding-bottom:4px}}
.meta{{color:#5b6b7c;font-size:12px}}table{{width:100%;border-collapse:collapse;margin:8px 0}}
th,td{{text-align:left;padding:8px;border-bottom:1px solid #e6edf3}}th{{width:42%;color:#5b6b7c;font-weight:500}}
.notice{{background:#fff8e6;border:1px solid #f0d48a;padding:12px;border-radius:8px;font-size:12px;margin-top:20px}}
.sign{{display:flex;gap:40px;margin-top:36px}}.sign div{{flex:1;border-top:1px solid #9aa8b6;padding-top:6px;font-size:12px;color:#5b6b7c}}
@media print{{body{{margin:0}} .no-print{{display:none}}}}
</style></head><body>
<div class="no-print" style="text-align:right"><button onclick="window.print()">打印/PDF</button></div>
<h1>AquaTwin 清洁方案报价</h1>
<div class="meta">客户：{escape(customer or '（待填）')} · 场景：{escape(study.name)} · 有效期：{valid_days} 天 · 模型：{escape(result.get('model_version','—'))}</div>
<h2>方案输入</h2>
<table><tr><th>泳池</th><td>{study.pool.length_m:g}×{study.pool.width_m:g}×{study.pool.depth_m:g} m；面积 {study.pool.area_m2:.2f} m²；{study.pool.water_temp_c:g}°C；{study.pool.salinity_ppt:g} ppt</td></tr>
<tr><th>机器人</th><td>清洁宽度 {study.robot.swath_m:g} m；速度 {study.robot.speed_m_s:g} m/s；电池 {study.robot.battery_wh:g} Wh</td></tr>
<tr><th>过滤</th><td>捕获 {study.filter.capture_efficiency*100:g}%；容量 {study.filter.capacity_g:g} g</td></tr></table>
<h2>结果与商务</h2><table>{tr}</table>
<h2>说明</h2>
<p>本报价基于场景假设与降阶模型，不含空驶、补人、失败重洗、维修/耗材、税费与现场安全措施；实际价格以现场勘察与合同为准。
{cal_note}
</p>
<div class="notice">边界：这不是性能保证、投资建议或安全认证。物理闸门/现场验证：未做。报价有效期 {valid_days} 天。</div>
<div class="sign"><div>客户确认</div><div>AquaTwin</div></div>
</body></html>'''
