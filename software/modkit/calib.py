"""平面手眼标定：估计"相机/标定板坐标 → 臂基座"的相似变换。

真机流程：把标定板放 5 个位置，记录基座坐标与像素坐标，`fit` 出 dx/dy/转角/尺度；
仿真里用同一个 `HandEye` 注入误差，验证标定前后抓取成功率。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class HandEye:
    """把测量坐标映射到基座坐标：p_base = s·R(θ)·p_meas + t。"""
    dx: float = 0.0
    dy: float = 0.0
    dyaw_deg: float = 0.0
    scale: float = 1.0

    def apply(self, x: float, y: float) -> tuple[float, float]:
        a = math.radians(self.dyaw_deg)
        ca, sa = math.cos(a), math.sin(a)
        return (self.scale * (ca * x - sa * y) + self.dx,
                self.scale * (sa * x + ca * y) + self.dy)

    def inverse(self) -> "HandEye":
        s = self.scale if abs(self.scale) > 1e-9 else 1e-9
        a = math.radians(-self.dyaw_deg)
        ca, sa = math.cos(a), math.sin(a)
        # p = (1/s) R(-θ) (q - t)
        dx = -(ca * self.dx - sa * self.dy) / s
        dy = -(sa * self.dx + ca * self.dy) / s
        return HandEye(dx, dy, -self.dyaw_deg, 1.0 / s)

    def residual_mm(self, measured, truth) -> float:
        errs = []
        for (mx, my), (tx, ty) in zip(measured, truth):
            x, y = self.apply(mx, my)
            errs.append(math.hypot(x - tx, y - ty))
        return max(errs) if errs else 0.0

    @classmethod
    def fit(cls, measured, truth) -> "HandEye":
        """Umeyama 2D：measured → truth 的最小二乘相似变换（≥3 点）。"""
        if len(measured) != len(truth) or len(measured) < 3:
            raise ValueError("需要 ≥3 组一一对应的点")
        src = np.asarray(measured, dtype=float)
        dst = np.asarray(truth, dtype=float)
        mu_s, mu_d = src.mean(axis=0), dst.mean(axis=0)
        xs, xd = src - mu_s, dst - mu_d
        cov = xd.T @ xs / len(src)
        u, sv, vt = np.linalg.svd(cov)
        d = np.sign(np.linalg.det(u @ vt))
        rot = u @ np.diag([1.0, d]) @ vt
        var = (xs ** 2).sum() / len(src)
        scale = float((sv * np.array([1.0, d])).sum() / var) if var > 1e-12 else 1.0
        t = mu_d - scale * rot @ mu_s
        return cls(float(t[0]), float(t[1]),
                   math.degrees(math.atan2(rot[1, 0], rot[0, 0])), scale)

    def to_json(self) -> dict:
        return {"dx": round(self.dx, 3), "dy": round(self.dy, 3),
                "dyaw_deg": round(self.dyaw_deg, 3), "scale": round(self.scale, 6)}


def calibration_grid(cx: float = 0.0, cy: float = 0.0,
                     span: float = 60.0) -> list[tuple[float, float]]:
    """标定板 5 点：中心 + 四角。"""
    return [(cx, cy), (cx - span, cy - span), (cx + span, cy - span),
            (cx + span, cy + span), (cx - span, cy + span)]
