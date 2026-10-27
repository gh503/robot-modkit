"""平面多边形工具：面积、点内测试、扫描线区间。

坐标约定：泳池局部坐标，原点在左下角，x 沿长度，y 沿宽度；单位 m。
只接受简单多边形（不自交）；不做 GIS 投影。
"""

from __future__ import annotations

import math


class GeometryError(ValueError):
    pass


def _pt(p) -> tuple[float, float]:
    try:
        x, y = float(p[0]), float(p[1])
    except (TypeError, ValueError, IndexError) as e:
        raise GeometryError(f"点必须是 [x,y]：{p!r}") from e
    if not (math.isfinite(x) and math.isfinite(y)):
        raise GeometryError(f"点含 NaN/Inf：{p!r}")
    return x, y


def signed_area(points: list[list[float]]) -> float:
    pts = [_pt(p) for p in points]
    return 0.5 * sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2)
                     in zip(pts, pts[1:] + pts[:1]))


def polygon_area(points: list[list[float]]) -> float:
    pts = [_pt(p) for p in points]
    if len(pts) < 3:
        raise GeometryError("多边形至少需要 3 个点")
    if pts[0] == pts[-1]:
        raise GeometryError("不要重复首点作为闭合点；直接给 N 个顶点")
    return abs(signed_area(points))


def _seg_intersect(a, b, c, d) -> bool:
    def cross(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    def on(p, q, r):
        return (min(p[0], q[0]) - 1e-12 <= r[0] <= max(p[0], q[0]) + 1e-12 and
                min(p[1], q[1]) - 1e-12 <= r[1] <= max(p[1], q[1]) + 1e-12)
    c1, c2 = cross(a, b, c), cross(a, b, d)
    c3, c4 = cross(c, d, a), cross(c, d, b)
    if ((c1 > 1e-12 and c2 < -1e-12) or (c1 < -1e-12 and c2 > 1e-12)) and \
       ((c3 > 1e-12 and c4 < -1e-12) or (c3 < -1e-12 and c4 > 1e-12)):
        return True
    return ((abs(c1) <= 1e-12 and on(a, b, c)) or
            (abs(c2) <= 1e-12 and on(a, b, d)) or
            (abs(c3) <= 1e-12 and on(c, d, a)) or
            (abs(c4) <= 1e-12 and on(c, d, b)))


def validate_polygon(points: list[list[float]]) -> tuple[list[list[float]], float]:
    pts = [_pt(p) for p in points]
    if len(pts) < 3:
        raise GeometryError("多边形至少需要 3 个点")
    if pts[0] == pts[-1]:
        raise GeometryError("不要重复首点作为闭合点")
    if len(set(pts)) < 3:
        raise GeometryError("多边形顶点重复")
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        if a == b:
            raise GeometryError("存在零长度边")
        for j in range(i + 1, n):
            if j == i or (j + 1) % n == i or (i + 1) % n == j:
                continue
            c, d = pts[j], pts[(j + 1) % n]
            if _seg_intersect(a, b, c, d):
                raise GeometryError("多边形自交")
    area = abs(signed_area(points))
    if area < 1e-9:
        raise GeometryError("多边形面积接近 0")
    return [list(p) for p in pts], area


def point_in_polygon(points: list[list[float]], x: float, y: float) -> bool:
    pts = [(float(p[0]), float(p[1])) for p in points]
    inside = False
    j = len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if ((yi > y) != (yj > y)) and \
           (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def scanline_intervals(points: list[list[float]], y: float,
                       xmin: float, xmax: float, eps: float = 1e-9) -> list[tuple[float, float]]:
    """水平线 y 与简单多边形的交区间，合并后按 x 排序。"""
    pts = [(float(p[0]), float(p[1])) for p in points]
    xs = []
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        if abs(y2 - y1) <= eps:
            continue
        lo, hi = (y1, y2) if y1 < y2 else (y2, y1)
        if lo <= y < hi:
            xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
    xs.sort()
    out = []
    for i in range(0, len(xs) - 1, 2):
        a, b = max(xmin, xs[i]), min(xmax, xs[i + 1])
        if b - a > eps:
            if out and a <= out[-1][1] + eps:
                out[-1] = (out[-1][0], max(out[-1][1], b))
            else:
                out.append((a, b))
    return out


__all__ = ["GeometryError", "signed_area", "polygon_area", "validate_polygon",
           "point_in_polygon", "scanline_intervals"]
