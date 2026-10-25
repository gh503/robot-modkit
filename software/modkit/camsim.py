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
    yaw_deg: float = 0.0    # 相机绕 z 的朝向（随机身转）
    k1: float = 0.0         # 径向畸变
    k2: float = 0.0
    p1: float = 0.0         # 切向畸变
    p2: float = 0.0

    def _distort(self, x: float, y: float) -> tuple[float, float]:
        r2 = x * x + y * y
        radial = 1.0 + self.k1 * r2 + self.k2 * r2 * r2
        xd = x * radial + 2.0 * self.p1 * x * y + self.p2 * (r2 + 2.0 * x * x)
        yd = y * radial + self.p1 * (r2 + 2.0 * y * y) + 2.0 * self.p2 * x * y
        return xd, yd

    def _undistort(self, xd: float, yd: float, iters: int = 12) -> tuple[float, float]:
        x, y = xd, yd
        for _ in range(iters):
            r2 = x * x + y * y
            radial = 1.0 + self.k1 * r2 + self.k2 * r2 * r2
            if abs(radial) < 1e-9:
                break
            dx = 2.0 * self.p1 * x * y + self.p2 * (r2 + 2.0 * x * x)
            dy = self.p1 * (r2 + 2.0 * y * y) + 2.0 * self.p2 * x * y
            x, y = (xd - dx) / radial, (yd - dy) / radial
        return x, y

    def project(self, X: float, Y: float, Z: float) -> tuple[float, float] | None:
        """世界点（桌面 z=0）→ 像素；在相机背后返回 None。"""
        dz = self.z - Z
        if dz <= 1e-6:
            return None
        a = math.radians(-self.yaw_deg)
        dx, dy = X - self.x, Y - self.y
        lx = dx * math.cos(a) - dy * math.sin(a)
        ly = dx * math.sin(a) + dy * math.cos(a)
        xd, yd = self._distort(lx / dz, ly / dz)
        return self.cx + self.fx * xd, self.cy + self.fy * yd

    def unproject(self, u: float, v: float, Z: float = 0.0) -> tuple[float, float]:
        dz = self.z - Z
        x, y = self._undistort((u - self.cx) / self.fx, (v - self.cy) / self.fy)
        lx, ly = x * dz, y * dz
        a = math.radians(self.yaw_deg)
        return (self.x + lx * math.cos(a) - ly * math.sin(a),
                self.y + lx * math.sin(a) + ly * math.cos(a))

    def table_calib(self, z_obj: float = 0.0):
        """像素 → 桌面 mm 的仿射。

        注意：看的是**物体顶面**时传 z_obj=方块高度，否则透视会把中心往画面外推
        （40mm 方块在 800mm 高、200mm 偏置下大约偏 10mm）。
        """
        from .vision import TableCalib
        if self.k1 or self.k2 or self.p1 or self.p2:
            # 有畸变时像素→桌面不是严格仿射；在视野中心做局部拟合，
            # 给四点标定/旧接口用，精确反投影请用 unproject。
            pts, world = [], []
            for gx in (-150.0, 0.0, 150.0):
                for gy in (-150.0, 0.0, 150.0):
                    X, Y = self.x + gx, self.y + gy
                    p = self.project(X, Y, z_obj)
                    if p is not None:
                        pts.append(p)
                        world.append((X, Y))
            if len(pts) >= 3:
                return TableCalib.from_points(pts, world)
        sx, sy = (self.z - z_obj) / self.fx, (self.z - z_obj) / self.fy
        a = math.radians(self.yaw_deg)
        ca, sa = math.cos(a), math.sin(a)
        aa, bb = ca * sx, -sa * sy
        dd, ee = sa * sx, ca * sy
        return TableCalib(a=aa, b=bb, c=self.x - aa * self.cx - bb * self.cy,
                          d=dd, e=ee, f=self.y - dd * self.cx - ee * self.cy)


@dataclass
class Cube:
    x: float
    y: float
    size: float = 40.0
    color: tuple[int, int, int] = (200, 60, 40)
    yaw_deg: float = 0.0


@dataclass
class Marker:
    """平放在桌面上的机器人标记：主体矩形 + 前向小圆点（定朝向）。"""
    x: float
    y: float
    yaw_deg: float = 0.0
    length: float = 80.0
    width: float = 50.0
    color: tuple[int, int, int] = (200, 40, 200)
    dot_color: tuple[int, int, int] = (0, 180, 220)
    dot_offset: float = 45.0
    dot_r: float = 9.0


def _centroid(img, color, tol: int):
    from . import vision
    mask = vision.color_mask(img, color, tol)
    ys, xs = np.nonzero(mask)
    if len(xs) < 10:
        return None
    return float(xs.mean()), float(ys.mean())


def localize_marker(img, cam: Camera, m: Marker, tol: int = 45):
    """从图里找标记：主体质心 → 桌面 x/y，主体→前向点 → 偏航。

    只找两个颜色块，不用连通域（画面里没有同色干扰），几十微秒。
    """
    body = _centroid(img, m.color, tol)
    dot = _centroid(img, m.dot_color, tol)
    if body is None or dot is None:
        return None
    x, y = cam.unproject(*body, Z=0.0)
    dx, dy = cam.unproject(*dot, Z=0.0)
    yaw = math.degrees(math.atan2(dy - y, dx - x))
    return x, y, yaw


def _poly(cam: Camera, pts: list[tuple[float, float, float]]) -> list[tuple[float, float]]:
    out = []
    for X, Y, Z in pts:
        p = cam.project(X, Y, Z)
        if p is None:
            return []
        out.append(p)
    return out


def render(cam: Camera, cubes: list[Cube], bg: tuple[int, int, int] = (232, 230, 224),
           noise: float = 2.0, seed: int = 0,
           markers: list[Marker] | None = None,
           texture: bool = True) -> np.ndarray:
    img = Image.new("RGB", (cam.width, cam.height), bg)
    d = ImageDraw.Draw(img)
    rng = np.random.default_rng(seed)

    # 桌面轻纹理
    if texture:
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

    for m in markers or []:
        a = math.radians(m.yaw_deg)
        ca, sa = math.cos(a), math.sin(a)
        hl, hw = m.length / 2, m.width / 2

        def corner(dx, dy):
            return (m.x + dx * ca - dy * sa, m.y + dx * sa + dy * ca, 0.0)

        quad = _poly(cam, [corner(-hl, -hw), corner(hl, -hw),
                           corner(hl, hw), corner(-hl, hw)])
        if quad:
            d.polygon(quad, fill=m.color)
        dot = _poly(cam, [(m.x + m.dot_offset * ca,
                           m.y + m.dot_offset * sa, 0.0)])
        if dot:
            u, v = dot[0]
            r = max(2, int(round(m.dot_r * cam.fx / cam.z)))
            d.ellipse([u - r, v - r, u + r, v + r], fill=m.dot_color)

    arr = np.asarray(img, dtype=np.int16)
    if noise:
        arr = np.clip(arr + rng.normal(0, noise, arr.shape), 0, 255)
    img = Image.fromarray(arr.astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))
    return np.asarray(img, dtype=np.int16)
