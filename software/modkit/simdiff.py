"""场景回归基线：比较两次运行的确定性指标，抓"改动把结果带偏了"。"""

from __future__ import annotations

import json
import math
from pathlib import Path


def metrics(result: dict, name: str = "") -> dict:
    return {
        "scenario": name,
        "ok": bool(result.get("ok")),
        "time": float(result.get("time", 0.0)),
        "voltage": float(result.get("voltage", 0.0)),
        "pose": [float(v) for v in result.get("pose", [0, 0, 0])],
        "frames": len(result.get("trace", [])),
        "failures": list(result.get("failures", [])),
    }


def load(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "pose" not in data and "result" in data:
        data = data["result"]
    return data


def compare(base: dict, cur: dict, time_tol: float = 0.05, volt_tol: float = 0.05,
            pos_tol: float = 5.0, yaw_tol: float = 2.0) -> dict:
    problems = []
    if base.get("ok") != cur.get("ok"):
        problems.append(f"结果不同：基线 {base.get('ok')} → 当前 {cur.get('ok')}")

    def rel(a, b):
        return abs(b - a) / max(1e-9, abs(a))

    if rel(base.get("time", 1), cur.get("time", 0)) > time_tol:
        problems.append(f"用时 {base.get('time')}s → {cur.get('time')}s 超过 {time_tol:.0%}")
    if abs(cur.get("voltage", 0) - base.get("voltage", 0)) > volt_tol:
        problems.append(f"电压 {base.get('voltage')}V → {cur.get('voltage')}V 超过 {volt_tol}V")

    bp, cp = base.get("pose", [0, 0, 0]), cur.get("pose", [0, 0, 0])
    dpos = math.hypot(cp[0] - bp[0], cp[1] - bp[1])
    dyaw = abs((cp[2] - bp[2] + 180) % 360 - 180)
    if dpos > pos_tol:
        problems.append(f"终点偏 {dpos:.1f}mm 超过 {pos_tol}mm")
    if dyaw > yaw_tol:
        problems.append(f"终点偏航 {dyaw:.1f}° 超过 {yaw_tol}°")
    if cur.get("frames", len(cur.get("trace", []))) < 1:
        problems.append("没有 trace 帧")
    return {"ok": not problems, "problems": problems,
            "delta": {"pos_mm": round(dpos, 2), "yaw_deg": round(dyaw, 2),
                      "time_s": round(cur.get("time", 0) - base.get("time", 0), 2),
                      "voltage_v": round(cur.get("voltage", 0) - base.get("voltage", 0), 3)}}


def format_report(r: dict) -> str:
    if r["ok"]:
        return (f"PASS 基线一致（Δpos {r['delta']['pos_mm']}mm，"
                f"Δyaw {r['delta']['yaw_deg']}°，Δtime {r['delta']['time_s']}s）")
    return "FAIL\n" + "\n".join(f"  - {p}" for p in r["problems"])
