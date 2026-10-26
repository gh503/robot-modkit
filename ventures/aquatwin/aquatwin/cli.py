"""AquaTwin CLI：list / validate / study / roi / new。"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from . import __version__
from . import model
from . import report
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
    try:
        result = model.run(s)
    except ValueError as e:
        print(f"运行失败：{e}")
        return 2
    if args.out:
        paths = report.write(s, result, args.out)
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
    if args.out:
        print(f"输出：{args.out}/report.md、metrics.json、coverage.svg、dashboard.html")
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
    st.add_argument("--json", action="store_true")
    st.set_defaults(func=cmd_study)

    roi = sub.add_parser("roi", help="只看经济性")
    roi.add_argument("--scenario", required=True)
    roi.add_argument("--json", action="store_true")
    roi.set_defaults(func=cmd_roi)

    nw = sub.add_parser("new", help="生成场景模板")
    nw.add_argument("--out", default="scenarios/new.json")
    nw.set_defaults(func=cmd_new)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
