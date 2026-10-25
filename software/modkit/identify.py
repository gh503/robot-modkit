"""从遥测 CSV 反推仿真参数：编码器刻度、电池 OCV/内阻。

这是"仿真参数不是拍脑袋"的入口：真机跑一段，回来拟合，再把值写进 hwsim。
只拟合日志里**真的存在**的量；没有的量（摩擦、回差）不假装能算。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .telemetry import Sample

CURRENT_SCALE = 4.5 / 1000.0   # hwsim/固件：load 1000 ≈ 4.5A
IDLE_A = 0.12


@dataclass
class Fit:
    value: float
    r2: float
    n: int
    unit: str = ""

    def as_dict(self) -> dict:
        return {"value": round(self.value, 5), "r2": round(self.r2, 4),
                "n": self.n, "unit": self.unit}


def _unwrap(delta_deg: float) -> float:
    while delta_deg > 180:
        delta_deg -= 360
    while delta_deg < -180:
        delta_deg += 360
    return delta_deg


def encoder_fit(samples: list[Sample]) -> Fit | None:
    """位置斜率 (deg/s) 对反馈 speed LSB 过原点回归 → 每 LSB 多少 deg。"""
    by: dict[int, list[Sample]] = {}
    for s in samples:
        by.setdefault(s.sid, []).append(s)
    xs, ys = [], []
    for rows in by.values():
        rows.sort(key=lambda r: r.t)
        for a, b in zip(rows, rows[1:]):
            dt = b.t - a.t
            if not (0.01 <= dt <= 0.5):
                continue
            v = _unwrap(b.pos_deg - a.pos_deg) / dt
            reg = (a.speed + b.speed) / 2
            if abs(reg) >= 50 and abs(v) < 1000:
                xs.append(reg)
                ys.append(v)
    if len(xs) < 8:
        return None
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    k = sxy / sxx
    mean = sum(ys) / len(ys)
    ss_tot = sum((y - mean) ** 2 for y in ys)
    ss_res = sum((y - k * x) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-9 else 1.0
    return Fit(k, r2, len(xs), "deg/LSB")


def battery_fit(samples: list[Sample]) -> Fit | None:
    """V = OCV − R·(I + idle)，I 由反馈 load 折算；过最小二乘。"""
    pts = [(abs(s.load) * CURRENT_SCALE + IDLE_A, s.voltage)
           for s in samples if s.voltage > 1.0]
    if len(pts) < 10:
        return None
    n = len(pts)
    mx = sum(x for x, _ in pts) / n
    my = sum(y for _, y in pts) / n
    sxx = sum((x - mx) ** 2 for x, _ in pts)
    if sxx < 1e-9:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in pts)
    r = -sxy / sxx
    ocv = my + r * mx
    ss_tot = sum((y - my) ** 2 for _, y in pts)
    ss_res = sum((y - (ocv - r * x)) ** 2 for x, y in pts)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-9 else 1.0
    return Fit(ocv, r2, n, "V / Ω")


def report(samples: list[Sample]) -> dict:
    enc = encoder_fit(samples)
    bat = battery_fit(samples)
    notes = []
    if enc is None:
        notes.append("编码器：有效样本不足（需要 ≥8 对、|speed|≥50）")
    elif enc.r2 < 0.9:
        notes.append(f"编码器拟合 R²={enc.r2:.2f} 偏低，检查时间戳/打滑")
    if bat is None:
        notes.append("电池：有效样本不足或电压恒定")
    elif bat.r2 < 0.5:
        notes.append(f"电池拟合 R²={bat.r2:.2f} 偏低，负载变化太小")
    return {
        "encoder": enc.as_dict() if enc else None,
        "battery": None if bat is None else {
            **bat.as_dict(), "ocv_v": round(bat.value, 3),
            "resistance_ohm": round(-_slope(samples), 4),
        },
        "notes": notes,
        "samples": len(samples),
    }


def _slope(samples: list[Sample]) -> float:
    """电池拟合的斜率（−R），供报告拆出 OCV 与 R。"""
    pts = [(abs(s.load) * CURRENT_SCALE + IDLE_A, s.voltage)
           for s in samples if s.voltage > 1.0]
    n = len(pts)
    mx = sum(x for x, _ in pts) / n
    my = sum(y for _, y in pts) / n
    sxx = sum((x - mx) ** 2 for x, _ in pts)
    sxy = sum((x - mx) * (y - my) for x, y in pts)
    return sxy / sxx


def synthetic_samples(n: int = 120) -> list[Sample]:
    """给测试/演示：已知 90deg/s、0.0879deg/LSB、12.2V、0.12Ω。"""
    out = []
    for i in range(n):
        t = i * 0.2
        pos = (10 + 90 * t) % 360
        load = int(100 + 500 * (0.5 + 0.5 * math.sin(i / 7)))
        current = load * CURRENT_SCALE + IDLE_A
        v = 12.2 - 0.12 * current
        out.append(Sample(t=t, sid=5, pos_deg=pos, speed=1024,
                          load=load, voltage=round(v, 2), temp_c=30, status=0))
    return out
