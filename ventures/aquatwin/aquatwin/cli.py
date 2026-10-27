"""AquaTwin CLI：list / validate / study / roi / new。"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from . import __version__
from . import batch as bt
from . import calibrate as cb
from . import model
from . import report
from .measurements import MeasurementError, MeasurementSet
from .scenario import ScenarioError, Study


def _fmt(v, n=1):
    return "—" if v is None else f"{v:.{n}f}"


def _load(path: str) -> Study:
    try:
        return Study.load(path)
    except (OSError, ScenarioError) as e:
        sys.exit(f"读取场景失败：{e}")


def cmd_list(args) -> int:
    rows = sorted(pathlib.Path(args.dir).glob("*.json"))
    if not rows:
        print(f"{args.dir} 下没有场景")
        return 1
    for p in rows:
        try:
            s = Study.load(p)
            print(f"{p.name:28} {s.name:24} {s.pool.length_m:g}×{s.pool.width_m:g}m")
        except Exception as e:
            print(f"{p.name:28} 读取失败：{e}")
    return 0


def cmd_validate(args) -> int:
    s = _load(args.scenario)
    v = s.validate()
    if args.json:
        print(json.dumps(v, ensure_ascii=False, indent=2))
    else:
        print("PASS" if v["ok"] else "FAIL")
        for x in v["errors"]:
            print("  ✗ " + x)
        for x in v["warnings"]:
            print("  ! " + x)
    return 0 if v["ok"] else 2


def cmd_study(args) -> int:
    s = _load(args.scenario)
    calibration = None
    measurements = None
    if args.measurements:
        try:
            measurements = MeasurementSet.load(args.measurements)
            calibration = cb.calibrate(s, measurements)
        except (OSError, MeasurementError, cb.CalibrationError) as e:
            print(f"校准失败：{e}")
            return 2
    elif args.calibration:
        try:
            calibration = cb.load(args.calibration)
        except (OSError, cb.CalibrationError) as e:
            print(f"读取校准失败：{e}")
            return 2
    try:
        result = model.run(s, calibration=calibration)
    except ValueError as e:
        print(f"运行失败：{e}")
        return 2
    if args.out:
        paths = report.write(s, result, args.out, calibration=calibration,
                             measurements=measurements)
        result["outputs"] = paths
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    r = result["results"]
    print(f"AquaTwin · {s.name}")
    print(f"  单次 {r['total_time_min']:.1f} min（补电 {r['charge_time_min']:.1f}）；"
          f"覆盖 {r['coverage_pct']:.1f}%；能耗 {r['energy_wh']:.1f} Wh")
    print(f"  运行成本 ¥{r['operating_cost_cny']:.2f}；含折旧 ¥{r['cost_per_cleaning_cny']:.2f}；"
          f"单次节省 ¥{r['savings_per_cleaning_cny']:.2f}")
    print(f"  回收期（节省）{_fmt(r['payback_savings_months'])} 个月；"
          f"1 年 ROI {_fmt(r['roi_1y_pct'])}%")
    if result.get("warnings"):
        for x in result["warnings"]:
            print("  ! " + x)
    if calibration:
        print(f"  校准：time×{calibration['factors']['time_scale']:.3f}，"
              f"setup {calibration['factors']['setup_min']:.1f}min，"
              f"energy×{calibration['factors']['energy_scale']:.3f}，"
              f"pressure×{calibration['factors']['pressure_scale']:.3f}")
    if args.out:
        print(f"输出：{args.out}/report.md、metrics.json、coverage.svg、dashboard.html、quote.html")
    return 0


def cmd_roi(args) -> int:
    s = _load(args.scenario)
    try:
        r = model.run(s)["results"]
    except ValueError as e:
        print(f"运行失败：{e}")
        return 2
    d = {k: r[k] for k in ("cost_per_cleaning_cny", "operating_cost_cny",
                           "savings_per_cleaning_cny", "annual_net_after_depreciation_cny",
                           "payback_service_months", "payback_savings_months", "roi_1y_pct")}
    if args.json:
        print(json.dumps(d, ensure_ascii=False, indent=2))
    else:
        print(f"单次成本 ¥{d['cost_per_cleaning_cny']:.2f}；运行 ¥{d['operating_cost_cny']:.2f}")
        print(f"相对人工节省 ¥{d['savings_per_cleaning_cny']:.2f}/次")
        print(f"回收期：服务利润 {_fmt(d['payback_service_months'])} 个月；"
              f"节省 {_fmt(d['payback_savings_months'])} 个月")
        print(f"1 年 ROI {_fmt(d['roi_1y_pct'])}%")
    return 0


def cmd_new(args) -> int:
    s = Study("新泳池研究", description="从模板生成；先改 pool/robot/filter/economics")
    p = s.save(args.out)
    print(f"已生成 {p}；下一步：aquatwin study --scenario {p} --out out/study")
    return 0


def cmd_measurements(args) -> int:
    try:
        if str(args.file).lower().endswith(".csv"):
            ms = MeasurementSet.from_csv(args.file, study=getattr(args, "study", "") or "",
                                         source=getattr(args, "source", "field"))
        else:
            ms = MeasurementSet.load(args.file)
    except (OSError, MeasurementError) as e:
        print(f"读取测量失败：{e}")
        return 2
    v = ms.validate()
    if args.json:
        print(json.dumps({"validation": v, "data": ms.to_dict()}, ensure_ascii=False, indent=2))
    else:
        print("PASS" if v["ok"] else "FAIL")
        for x in v["errors"]:
            print("  ✗ " + x)
        for x in v["warnings"]:
            print("  ! " + x)
        print(f"  {v['n_runs']} 条 run；source={ms.source}")
    return 0 if v["ok"] else 2


def cmd_calibrate(args) -> int:
    s = _load(args.scenario)
    try:
        if str(args.measurements).lower().endswith(".csv"):
            ms = MeasurementSet.from_csv(args.measurements, study=s.name,
                                         source=getattr(args, "source", "field"))
        else:
            ms = MeasurementSet.load(args.measurements)
        cal = cb.calibrate(s, ms)
    except (OSError, MeasurementError, cb.CalibrationError) as e:
        print(f"校准失败：{e}")
        return 2
    paths = cb.save(cal, args.out, s, ms) if args.out else {}
    if args.json:
        print(json.dumps({"calibration": cal, "outputs": paths}, ensure_ascii=False, indent=2))
        return 0
    f, m = cal["factors"], cal["metrics"]
    print(f"AquaTwin 校准 · {s.name}（{cal['source']}，{cal['n_runs']} runs）")
    print(f"  time_scale={f['time_scale']:.3f}  setup={f['setup_min']:.2f} min  "
          f"energy_scale={f['energy_scale']:.3f}  pressure_scale={f['pressure_scale']:.3f}")
    print(f"  MAPE：时间 {_fmt(m['time_mape_pct'], 1)}% / 能耗 {_fmt(m['energy_mape_pct'], 1)}% / "
          f"压力 {_fmt(m['pressure_mape_pct'], 1)}%")
    conf = cal.get("confidence_90", {})
    if conf:
        print("  90% bootstrap：" + "，".join(f"{k} {v['low']:.2f}–{v['high']:.2f}"
                                             for k, v in conf.items()))
    for x in cal["caveats"]:
        print("  ! " + x)
    if args.out:
        print(f"输出：{args.out}/calibration.json、validation.md")
    return 0


def cmd_batch(args) -> int:
    files = sorted(pathlib.Path(args.dir).glob("*.json"))
    if not files:
        print(f"{args.dir} 下没有场景")
        return 1
    calibration = None
    if args.calibration:
        try:
            calibration = cb.load(args.calibration)
        except (OSError, cb.CalibrationError) as e:
            print(f"读取校准失败：{e}")
            return 2
    summary = bt.run_batch(files, args.out, calibration=calibration)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"批量：{summary['n']} 成功，{summary['n_errors']} 失败")
        for r in summary["studies"]:
            print(f"  {r['study']:24} {r['time_min']:6.1f} min  ¥{r['cost_cny']:.2f}  "
                  f"覆盖 {r['coverage_pct']:.1f}%")
        for e in summary["errors"]:
            print(f"  ✗ {e['file']}: {e['error']}")
        print(f"输出：{args.out}/portfolio.md、portfolio.json、portfolio.html")
    return 0 if not summary["n_errors"] else 2


def cmd_quote(args) -> int:
    s = _load(args.scenario)
    calibration = None
    if args.calibration:
        try:
            calibration = cb.load(args.calibration)
        except (OSError, cb.CalibrationError) as e:
            print(f"读取校准失败：{e}")
            return 2
    try:
        result = model.run(s, calibration=calibration)
    except ValueError as e:
        print(f"运行失败：{e}")
        return 2
    p = pathlib.Path(args.out)
    p.mkdir(parents=True, exist_ok=True)
    (p / "quote.html").write_text(report.quote(s, result, customer=args.customer,
                                               valid_days=args.valid_days), encoding="utf-8")
    print(f"已生成 {p / 'quote.html'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="aquatwin", description="AquaTwin 泳池机器人数字孪生")
    ap.add_argument("--version", action="version", version=f"aquatwin {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    li = sub.add_parser("list", help="列出场景")
    li.add_argument("--dir", default="scenarios")
    li.set_defaults(func=cmd_list)

    va = sub.add_parser("validate", help="校验场景")
    va.add_argument("--scenario", required=True)
    va.add_argument("--json", action="store_true")
    va.set_defaults(func=cmd_validate)

    st = sub.add_parser("study", help="跑研究并输出报告")
    st.add_argument("--scenario", required=True)
    st.add_argument("--out")
    st.add_argument("--calibration")
    st.add_argument("--measurements")
    st.add_argument("--json", action="store_true")
    st.set_defaults(func=cmd_study)

    roi = sub.add_parser("roi", help="只看经济性")
    roi.add_argument("--scenario", required=True)
    roi.add_argument("--json", action="store_true")
    roi.set_defaults(func=cmd_roi)

    nw = sub.add_parser("new", help="生成场景模板")
    nw.add_argument("--out", default="scenarios/new.json")
    nw.set_defaults(func=cmd_new)

    me = sub.add_parser("measurements", help="校验实测数据（JSON/CSV）")
    me.add_argument("--file", required=True)
    me.add_argument("--study", default="", help="CSV 没有 study 列时指定场景名")
    me.add_argument("--source", default="field", choices=("field", "lab", "vendor", "synthetic"))
    me.add_argument("--json", action="store_true")
    me.set_defaults(func=cmd_measurements)

    ca = sub.add_parser("calibrate", help="用实测数据拟合校准因子")
    ca.add_argument("--scenario", required=True)
    ca.add_argument("--measurements", required=True)
    ca.add_argument("--source", default="field", choices=("field", "lab", "vendor", "synthetic"))
    ca.add_argument("--out")
    ca.add_argument("--json", action="store_true")
    ca.set_defaults(func=cmd_calibrate)

    ba = sub.add_parser("batch", help="批量跑目录下所有场景")
    ba.add_argument("--dir", default="scenarios")
    ba.add_argument("--out", required=True)
    ba.add_argument("--calibration")
    ba.add_argument("--json", action="store_true")
    ba.set_defaults(func=cmd_batch)

    qu = sub.add_parser("quote", help="生成可打印报价页")
    qu.add_argument("--scenario", required=True)
    qu.add_argument("--out", required=True)
    qu.add_argument("--customer", default="")
    qu.add_argument("--valid-days", type=int, default=30)
    qu.add_argument("--calibration")
    qu.set_defaults(func=cmd_quote)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
