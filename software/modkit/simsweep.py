"""蒙特卡洛：同一场景，随机扰动参数，看通过率与误差分布。

不是"跑一次碰巧过"：每个样本记录扰动值和结果，种子固定可复现。
默认只扰动仿真允许的物理量（打滑/电池/负载/丢帧/舵机力矩），不改场景逻辑。
"""

from __future__ import annotations

import copy
import math
import random
from dataclasses import dataclass

from . import scenario as sn


@dataclass(frozen=True)
class Profile:
    slip: tuple[float, float] = (0.0, 0.05)
    ocv: tuple[float, float] = (11.6, 12.4)
    payload_kg: tuple[float, float] = (0.0, 0.1)
    drop_rate: tuple[float, float] = (0.0, 0.02)
    rated_torque: tuple[float, float] = (2.6, 2.94)


PROFILES = {
    "clean": Profile(slip=(0.0, 0.0), ocv=(12.0, 12.4), payload_kg=(0.0, 0.0),
                     drop_rate=(0.0, 0.0), rated_torque=(2.8, 2.94)),
    "mild": Profile(slip=(0.0, 0.03), drop_rate=(0.0, 0.01)),
    "harsh": Profile(slip=(0.0, 0.30), ocv=(10.2, 12.4), payload_kg=(0.0, 0.3),
                     drop_rate=(0.0, 0.08), rated_torque=(1.8, 2.94)),
}


def _expected_pose(scene: dict) -> tuple[float, float]:
    """从最终断言里读期望位姿；没有就按原点。"""
    ex = ey = 0.0
    for a in scene.get("assert", []):
        if a.get("path") == "pose.x":
            ex = float(a.get("value", 0))
        elif a.get("path") == "pose.y":
            ey = float(a.get("value", 0))
    return ex, ey


def _sample(rng: random.Random, p: Profile) -> dict:
    def u(r):
        return round(rng.uniform(*r), 4)

    return {
        "slip": u(p.slip),
        "ocv": u(p.ocv),
        "payload_kg": u(p.payload_kg),
        "drop_rate": u(p.drop_rate),
        "rated_torque": u(p.rated_torque),
    }


def run_sweep(scene: dict, n: int = 30, seed: int = 0,
              profile: str = "mild") -> dict:
    if n <= 0:
        raise ValueError("n 必须为正")
    if profile not in PROFILES:
        raise ValueError(f"未知 profile：{profile}")
    prof = PROFILES[profile]
    ex, ey = _expected_pose(scene)
    rng = random.Random(seed)
    runs = []
    errors = []
    for i in range(n):
        params = _sample(rng, prof)
        s = copy.deepcopy(scene)
        cfg = s.setdefault("sim", {})
        cfg["slip"] = params["slip"]
        cfg["payload_kg"] = params["payload_kg"]
        cfg["drop_rate"] = params["drop_rate"]
        cfg.setdefault("retries", 3)   # 链路层重试，不让丢帧直接毁掉仿真
        cfg.setdefault("battery", {})["ocv"] = params["ocv"]
        cfg.setdefault("servo", {})["rated_torque"] = params["rated_torque"]
        try:
            r = sn.run_scenario(s)
            err = math.hypot(r["pose"][0] - ex, r["pose"][1] - ey)
            ok = bool(r["ok"])
            why = "" if ok else (r["failures"][0] if r["failures"] else "未知")
        except Exception as e:  # 单次仿真异常不能毁掉整批
            err, ok, why = float("nan"), False, f"{type(e).__name__}: {e}"
        errors.append(err)
        runs.append({"i": i, "params": params, "ok": ok,
                     "error_mm": None if math.isnan(err) else round(err, 2),
                     "why": why})
    good = [e for e in errors if not math.isnan(e)]
    good.sort()

    def pct(q):
        if not good:
            return None
        k = min(len(good) - 1, max(0, int(round(q * (len(good) - 1)))))
        return round(good[k], 2)

    passed = sum(1 for r in runs if r["ok"])
    return {
        "scenario": scene.get("name", ""),
        "profile": profile,
        "seed": seed, "n": n,
        "passed": passed, "pass_rate": round(passed / n, 3),
        "expected": [ex, ey],
        "error_mm": {"p50": pct(0.5), "p95": pct(0.95),
                     "max": round(good[-1], 2) if good else None},
        "runs": runs,
    }
