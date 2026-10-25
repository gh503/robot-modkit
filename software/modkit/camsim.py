"""相机仿真：俯视针孔相机 + 桌面方块，生成能被 vision.detect_color 识别的图。

用途：视觉链在没有相机时也能端到端调——检测、四点标定、抓取逆解都吃真实像素。
模型故意简单（平面、漫反射、无镜头畸变），但像素坐标和几何是同一套投影。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


@dataclass
class Camera:
    width: int = 640
    height: int = 480
    fx: float = 600.0
    fy: float = 600.0
    cx: float = 320.0
    cy: float = 240.0
    x: float = 0.0          # 相机光心（mm）
    y: float = 0.0
    z: float = 800.0        # 离桌面高度

    def project(self, X: float, Y: float, Z: float) -> tuple[float, float] | None:
        """世界点（桌面 z=0）→ 像素；在相机背后返回 None。"""
        dz = self.z - Z
        if dz <= 1e-6:
            return None
        u = self.cx + self.fx * (X - self.x) / dz
        v = self.cy + self.fy * (Y - self.y) / dz
        return u, v

    def unproject(self, u: float, v: float, Z: float = 0.0) -> tuple[float, float]:
        dz = self.z - Z
        return (self.x + (u - self.cx) * dz / self.fx,
                self.y + (v - self.cy) * dz / self.fy)

    def table_calib(self, z_obj: float = 0.0):
        """像素 → 桌面 mm 的仿射。

        注意：看的是**物体顶面**时传 z_obj=方块高度，否则透视会把中心往画面外推
        （40mm 方块在 800mm 高、200mm 偏置下大约偏 10mm）。
        """
        from .vision import TableCalib
        sx, sy = (self.z - z_obj) / self.fx, (self.z - z_obj) / self.fy
        return TableCalib(a=sx, b=0.0, c=self.x - self.cx * sx,
                          d=0.0, e=sy, f=self.y - self.cy * sy)


@dataclass
class Cube:
    x: float
    y: float
    size: float = 40.0
    color: tuple[int, int, int] = (200, 60, 40)
    yaw_deg: float = 0.0


def _poly(cam: Camera, pts: list[tuple[float, float, float]]) -> list[tuple[float, float]]:
    out = []
    for X, Y, Z in pts:
        p = cam.project(X, Y, Z)
        if p is None:
            return []
        out.append(p)
    return out


def render(cam: Camera, cubes: list[Cube], bg: tuple[int, int, int] = (232, 230, 224),
           noise: float = 2.0, seed: int = 0) -> np.ndarray:
    img = Image.new("RGB", (cam.width, cam.height), bg)
    d = ImageDraw.Draw(img)
    rng = np.random.default_rng(seed)

    # 桌面轻纹理
    for _ in range(400):
        u = rng.uniform(0, cam.width)
        v = rng.uniform(0, cam.height)
        c = int(rng.uniform(-6, 6))
        d.point((u, v), fill=tuple(max(0, min(255, x + c)) for x in bg))

    for cube in sorted(cubes, key=lambda c: c.y):
        h = cube.size
        a = math.radians(cube.yaw_deg)
        ca, sa = math.cos(a), math.sin(a)
        half = h / 2

        def corner(dx: float, dy: float, z: float):
            X = cube.x + dx * ca - dy * sa
            Y = cube.y + dx * sa + dy * ca
            return X, Y, z

        bottom = [_poly(cam, [corner(-half, -half, 0), corner(half, -half, 0),
                              corner(half, half, 0), corner(-half, half, 0)])]
        top = _poly(cam, [corner(-half, -half, h), corner(half, -half, h),
                          corner(half, half, h), corner(-half, half, h)])
        if not top:
            continue
        # 影子
        shadow = [(u + 6, v + 6) for u, v in top]
        d.polygon(shadow, fill=(210, 208, 202))
        # 侧面（简单用顶面外扩一圈暗色）
        side = [(u * 1.04 - cam.cx * 0.04, v * 1.04 - cam.cy * 0.04) for u, v in top]
        d.polygon(side, fill=tuple(int(c * 0.65) for c in cube.color))
        d.polygon(top, fill=cube.color)
        # 顶面高光
        d.line(top + [top[0]], fill=tuple(min(255, int(c * 1.15)) for c in cube.color), width=2)

    arr = np.asarray(img, dtype=np.int16)
    if noise:
        arr = np.clip(arr + rng.normal(0, noise, arr.shape), 0, 255)
    img = Image.fromarray(arr.astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))
    return np.asarray(img, dtype=np.int16)
