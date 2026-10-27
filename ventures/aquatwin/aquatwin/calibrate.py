"""AquaTwin 校准：用导入的实测数据拟合 4 个透明因子。

模型结构不变，只拟合：
  time_scale      作业时间乘子（路径/转向）
  setup_min       每次部署固定时间
  energy_scale    能耗乘子（电池/泵/驱动综合偏差）
  pressure_scale  过滤压升乘子

这是“校准”，不是“证明”。数据不足/非现场数据时报告必须降级。
"""

from __future__ import annotations

import hashlib
import json
import math
import pathlib
import random
from dataclasses import asdict

from . import model
from .measurements import MeasurementSet, study_for_run


class CalibrationError(ValueError):
    pass


def _sha(obj) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _mape(ys: list[float], ps: list[float]) -> float | None:
    vals = []
    for y, p in zip(ys, ps):
        if y is None or p is None:
            continue
        vals.append(abs(p - y) / max(abs(y), 1e-9))
    return 100.0 * sum(vals) / len(vals) if vals else None


def _mae(ys: list[float], ps: list[float]) -> float | None:
    vals = [abs(p - y) for y, p in zip(ys, ps) if y is not None and p is not None]
    return sum(vals) / len(vals) if vals else None


def _fit_ratio(ys: list[float], xs: list[float], lo: float, hi: float) -> float:
    denom = sum(x * x for x in xs)
    if denom <= 0:
        return 1.0
    r = sum(y * x for y, x in zip(ys, xs)) / denom
    return max(lo, min(hi, r))


def _fit_time(ys: list[float], xs: list[float]) -> tuple[float, float, str]:
    """y ≈ a*x + b，约束 a/b；网格搜索避免越界后乱外推。"""
    if len(ys) == 1:
        a = max(0.30, min(3.0, ys[0] / max(xs[0], 1e-9)))
        return a, 0.0, "单条数据：只拟合比例，固定 setup=0；不可靠"
    best = (float("inf"), 1.0, 0.0)
    # 先粗后细；a 0.30..3.00，b 0..30
    for i in range(271):
        a = 0.30 + i * 0.01
        for j in range(121):
            b = j * 0.25
            sse = sum((a * x + b - y) ** 2 for x, y in zip(xs, ys))
            if sse < best[0]:
                best = (sse, a, b)
    _, a0, b0 = best
    for i in range(-20, 21):
        a = max(0.30, min(3.0, a0 + i * 0.001))
        for j in range(-10, 11):
            b = max(0.0, min(30.0, b0 + j * 0.025))
            sse = sum((a * x + b - y) ** 2 for x, y in zip(xs, ys))
            if sse < best[0]:
                best = (sse, a, b)
    return best[1], best[2], ""


def _fit_factors(rows: list[dict]) -> tuple[dict, bool, str]:
    xs = [row["base"]["active_time_min"] for row in rows]
    ys = [row["run"].time_min for row in rows]
    a, b, note = _fit_time(ys, xs)
    energy_scale = _fit_ratio([r["run"].energy_wh for r in rows],
                              [r["base"]["energy_wh"] for r in rows], 0.20, 5.0)
    has_pressure = any(r["run"].pressure_kpa is not None for r in rows)
    if has_pressure:
        pressure_scale = _fit_ratio(
            [r["run"].pressure_kpa or 0.0 for r in rows],
            [r["base"]["filter_pressure_rise_kpa"] for r in rows], 0.10, 5.0)
    else:
        pressure_scale = 1.0
    return ({"time_scale": round(a, 6), "setup_min": round(b, 4),
             "energy_scale": round(energy_scale, 6),
             "pressure_scale": round(pressure_scale, 6)}, has_pressure, note)


def _pct(vals: list[float], q: float) -> float:
    v = sorted(vals)
    if not v:
        return 0.0
    if len(v) == 1:
        return v[0]
    pos = (len(v) - 1) * q
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def _bootstrap(rows: list[dict], n: int = 120, seed: int = 20261001) -> dict:
    """确定性 bootstrap：只给区间，不制造“置信=保证”的错觉。"""
    rng = random.Random(seed)
    samples = {k: [] for k in ("time_scale", "setup_min", "energy_scale", "pressure_scale")}
    for _ in range(n):
        idx = [rng.randrange(len(rows)) for _ in rows]
        if len(set(idx)) < 2:
            continue
        f, _, _ = _fit_factors([rows[i] for i in idx])
        for k in samples:
            samples[k].append(f[k])
    return {k: {"low": round(_pct(v, 0.05), 4), "high": round(_pct(v, 0.95), 4),
                "n": len(v)} for k, v in samples.items() if v}


def calibrate(study, ms: MeasurementSet) -> dict:
    v = study.validate()
    if not v["ok"]:
        raise CalibrationError("场景非法：" + "；".join(v["errors"]))
    mv = ms.validate()
    if not mv["ok"]:
        raise CalibrationError("测量数据非法：" + "；".join(mv["errors"]))
    if ms.study and ms.study != study.name:
        # 名称不一致不阻止，但必须显式记录
        pass

    base_rows = []
    for run in ms.runs:
        s = study_for_run(study, run)
        pred = model.run(s)["results"]
        base_rows.append({"run": run, "study": s, "base": pred})

    factors, has_pressure, note = _fit_factors(base_rows)

    # 用同一组因子重新预测，用于报告
    residuals = []
    for row in base_rows:
        cal = {"factors": factors}
        p = model.run(row["study"], calibration=cal)["results"]
        run = row["run"]
        residuals.append({
            "run_id": run.run_id,
            "measured_time_min": run.time_min,
            "predicted_time_min": p["total_time_min"],
            "time_error_pct": (p["total_time_min"] - run.time_min) / max(run.time_min, 1e-9) * 100,
            "measured_energy_wh": run.energy_wh,
            "predicted_energy_wh": p["energy_wh"],
            "energy_error_pct": (p["energy_wh"] - run.energy_wh) / max(run.energy_wh, 1e-9) * 100,
            "measured_pressure_kpa": run.pressure_kpa,
            "predicted_pressure_kpa": p["filter_pressure_rise_kpa"],
            "measured_coverage_pct": run.coverage_pct,
            "predicted_coverage_pct": p["coverage_pct"],
        })

    mt = _mape([r["measured_time_min"] for r in residuals],
               [r["predicted_time_min"] for r in residuals])
    me = _mape([r["measured_energy_wh"] for r in residuals],
               [r["predicted_energy_wh"] for r in residuals])
    mp = _mape([r["measured_pressure_kpa"] for r in residuals if r["measured_pressure_kpa"] is not None],
               [r["predicted_pressure_kpa"] for r in residuals if r["measured_pressure_kpa"] is not None])
    mc = _mae([r["measured_coverage_pct"] for r in residuals if r["measured_coverage_pct"] is not None],
              [r["predicted_coverage_pct"] for r in residuals if r["measured_coverage_pct"] is not None])

    caveats = [
        "校准只拟合 4 个乘子，不改变覆盖/阻力/泵/过滤模型结构",
        "数据不足以区分多个物理参数；外推到不同池型/机器人需重新验证",
        "synthetic/vendor/lab 数据不能写成 field-validated",
        "时间/能耗 MAPE 只代表本数据集，不代表所有池型",
        "90% 区间是 bootstrap 重采样，不是对新池型的预测区间",
    ]
    if note:
        caveats.append(note)
    if ms.source != "field":
        caveats.append(f"source={ms.source}：非现场实测")
    if len(ms.runs) < 3:
        caveats.append("run 少于 3，参数不可靠")
    if not has_pressure:
        caveats.append("没有压力数据，pressure_scale 固定为 1")

    out = {
        "schema": "aquatwin.calibration/1",
        "model_version": model.MODEL_VERSION,
        "study": study.name,
        "study_sha256": _sha(study.to_dict()),
        "measurements_sha256": ms.sha256(),
        "source": ms.source,
        "n_runs": len(ms.runs),
        "factors": factors,
        "bounds": {k: list(v) for k, v in model.FACTOR_BOUNDS.items()},
        "confidence_90": _bootstrap(base_rows) if len(ms.runs) >= 3 else {},
        "metrics": {"time_mape_pct": mt, "energy_mape_pct": me,
                    "pressure_mape_pct": mp, "coverage_mae_pp": mc},
        "residuals": residuals,
        "caveats": caveats,
        "applied": False,
    }
    return out


def markdown(study, ms: MeasurementSet, cal: dict) -> str:
    f = cal["factors"]
    m = cal["metrics"]
    L = [f"# AquaTwin 校准报告：{study.name}", "",
         f"> 数据来源：**{cal['source']}**；{cal['n_runs']} 条 run；"
         f"模型 `{cal['model_version']}`。", ""]
    if cal["source"] != "field":
        L += [f"> ⚠️ 这不是现场实测数据（source={cal['source']}），不能对外写 field-validated。", ""]
    conf = cal.get("confidence_90", {})
    def _ci(k):
        c = conf.get(k)
        return "—" if not c else f"{c['low']:.2f}–{c['high']:.2f}"
    L += ["## 拟合因子", "",
          "| 因子 | 值 | 90% bootstrap 区间 | 含义 |", "|---|---:|---:|---|",
          f"| `time_scale` | {f['time_scale']:.3f} | {_ci('time_scale')} | 作业时间乘子 |",
          f"| `setup_min` | {f['setup_min']:.2f} min | {_ci('setup_min')} | 每次部署固定时间 |",
          f"| `energy_scale` | {f['energy_scale']:.3f} | {_ci('energy_scale')} | 能耗乘子 |",
          f"| `pressure_scale` | {f['pressure_scale']:.3f} | {_ci('pressure_scale')} | 过滤压升乘子 |",
          "", "## 误差", "",
          "| 指标 | 值 |", "|---|---:|"]
    for k, label in (("time_mape_pct", "时间 MAPE %"), ("energy_mape_pct", "能耗 MAPE %"),
                     ("pressure_mape_pct", "压力 MAPE %"), ("coverage_mae_pp", "覆盖率 MAE pp")):
        v = m.get(k)
        L.append(f"| {label} | {'—' if v is None else f'{v:.2f}'} |")
    L += ["", "## 逐条残差", "",
          "| run | 实测时间 | 预测时间 | 时间误差% | 实测能耗 | 预测能耗 | 能耗误差% |",
          "|---|---:|---:|---:|---:|---:|---:|"]
    for r in cal["residuals"]:
        L.append(f"| {r['run_id']} | {r['measured_time_min']:.2f} | {r['predicted_time_min']:.2f} | "
                 f"{r['time_error_pct']:+.1f} | {r['measured_energy_wh']:.2f} | "
                 f"{r['predicted_energy_wh']:.2f} | {r['energy_error_pct']:+.1f} |")
    L += ["", "## 边界", ""] + [f"- {x}" for x in cal["caveats"]]
    L += ["", "- 校准不等于现场认证；不能替代安全/性能保证。", ""]
    return "\n".join(L)


def save(cal: dict, out: str | pathlib.Path, study, ms: MeasurementSet) -> dict:
    d = pathlib.Path(out)
    d.mkdir(parents=True, exist_ok=True)
    (d / "calibration.json").write_text(json.dumps(cal, ensure_ascii=False, indent=2) + "\n",
                                        encoding="utf-8")
    (d / "validation.md").write_text(markdown(study, ms, cal), encoding="utf-8")
    ms.save(d / "measurements.json")
    return {"calibration": str(d / "calibration.json"),
            "validation": str(d / "validation.md"),
            "measurements": str(d / "measurements.json")}


def load(path: str | pathlib.Path) -> dict:
    try:
        d = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise CalibrationError(f"校准 JSON 解析失败：{e}") from e
    if d.get("schema") != "aquatwin.calibration/1":
        raise CalibrationError("不是 aquatwin.calibration/1")
    return d


__all__ = ["CalibrationError", "calibrate", "markdown", "save", "load"]
