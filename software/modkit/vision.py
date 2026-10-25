"""M3 视觉第一步：在纯色桌面上找一个色块，换算成桌面坐标。

为什么不用 OpenCV：
  · 现在只需要"找最大色块 + 仿射变换"，numpy 足够；
  · 少一个 60MB 依赖，树莓派/笔记本都好装；
  · 算法边界清楚，能用合成图逐项测。

依赖：numpy、Pillow（可选装 `pip install -e .[vision]`）。
"""

from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import dataclass
from pathlib import Path

try:
    import numpy as np
except ImportError as e:  # pragma: no cover
    raise ImportError("视觉需要 numpy：pip install -e .[vision]") from e

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


@dataclass
class Detection:
    cx: float          # 像素
    cy: float
    area: int          # 像素数
    bbox: tuple[int, int, int, int]

    @property
    def size(self) -> tuple[int, int]:
        x0, y0, x1, y1 = self.bbox
        return x1 - x0 + 1, y1 - y0 + 1


def load_rgb(path: str | Path) -> np.ndarray:
    if Image is None:  # pragma: no cover
        raise ImportError("读图需要 Pillow：pip install -e .[vision]")
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.int16)


def detect_color(rgb: np.ndarray, target: tuple[int, int, int],
                 tol: int = 50, min_area: int = 200) -> Detection | None:
    """找与 target 颜色距离 ≤tol 的最大连通块。rgb 形状 (H, W, 3)。"""
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("需要 H×W×3 的 RGB 数组")
    diff = rgb.astype(np.int32) - np.array(target, dtype=np.int32)
    mask = (diff * diff).sum(axis=2) <= tol * tol
    h, w = mask.shape
    seen = np.zeros((h, w), dtype=bool)
    best: Detection | None = None

    for y0 in range(h):
        for x0 in range(w):
            if not mask[y0, x0] or seen[y0, x0]:
                continue
            q = deque([(x0, y0)])
            seen[y0, x0] = True
            n = 0
            sx = sy = 0
            minx = maxx = x0
            miny = maxy = y0
            while q:
                x, y = q.popleft()
                n += 1
                sx += x
                sy += y
                if x < minx: minx = x
                if x > maxx: maxx = x
                if y < miny: miny = y
                if y > maxy: maxy = y
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < w and 0 <= ny < h and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        q.append((nx, ny))
            if n >= min_area and (best is None or n > best.area):
                best = Detection(sx / n, sy / n, n, (minx, miny, maxx, maxy))
    return best


@dataclass
class TableCalib:
    """像素 → 桌面毫米的仿射：x = a·u + b·v + c，y = d·u + e·v + f。"""
    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 0.0
    e: float = 1.0
    f: float = 0.0

    def apply(self, u: float, v: float) -> tuple[float, float]:
        return self.a * u + self.b * v + self.c, self.d * u + self.e * v + self.f

    def to_json(self) -> dict:
        return {"a": self.a, "b": self.b, "c": self.c,
                "d": self.d, "e": self.e, "f": self.f}

    @classmethod
    def from_json(cls, data: dict) -> "TableCalib":
        return cls(**{k: float(data[k]) for k in "abcdef"})

    @classmethod
    def from_points(cls, pixels: list[tuple[float, float]],
                    table_mm: list[tuple[float, float]]) -> "TableCalib":
        """四点标定：最小二乘拟合仿射（至少 3 点）。"""
        if len(pixels) != len(table_mm) or len(pixels) < 3:
            raise ValueError("需要 ≥3 组一一对应的点")
        A = np.array([[u, v, 1.0] for u, v in pixels])
        bx = np.array([p[0] for p in table_mm])
        by = np.array([p[1] for p in table_mm])
        cx, _, _, _ = np.linalg.lstsq(A, bx, rcond=None)
        cy, _, _, _ = np.linalg.lstsq(A, by, rcond=None)
        return cls(*map(float, (*cx, *cy)))


def load_calib(path: str | Path) -> TableCalib:
    return TableCalib.from_json(json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass
class PickPlan:
    """抓取位姿：桌面上方 → 抓取高度 → 抬起。坐标是臂基座系（mm）。"""
    x: float
    y: float
    z_table: float
    above_z: float
    grasp_z: float
    joints_above: tuple[float, float, float]
    joints_grasp: tuple[float, float, float]

    def as_dict(self) -> dict:
        return {
            "x": round(self.x, 1), "y": round(self.y, 1),
            "z_table": self.z_table,
            "above_z": self.above_z, "grasp_z": self.grasp_z,
            "joints_above": [round(v, 1) for v in self.joints_above],
            "joints_grasp": [round(v, 1) for v in self.joints_grasp],
        }


def plan_pick(calib: TableCalib, det: Detection, arm,
              z_table: float = 0.0, clearance: float = 60.0,
              grasp_z: float = 25.0, yaw_offset: float = 0.0) -> PickPlan:
    """像素检测 + 标定 → 抓取点 → 逆解。够不到会抛 ValueError。"""
    from . import kinematics as kin

    x, y = calib.apply(det.cx, det.cy)
    x += yaw_offset * 0  # 预留给相机安装偏置（当前未用）
    above = kin.inverse(arm, kin.Pose(x, y, z_table + clearance))
    grasp = kin.inverse(arm, kin.Pose(x, y, z_table + grasp_z))
    return PickPlan(x, y, z_table, z_table + clearance, z_table + grasp_z, above, grasp)
