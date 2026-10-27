"""矩形泳池的 boustrophedon 覆盖路径（工程近似）。

不是全向覆盖规划器：不处理障碍/斜池/水流；输出 lane 数、路径长度、覆盖率、
转向次数，供时间和成本模型使用。
"""

from __future__ import annotations

import csv
import math
import pathlib
from dataclasses import dataclass

from . import geometry as geo
from .scenario import Pool, Robot


@dataclass
class Coverage:
    lanes: int
    effective_swath_m: float
    path_length_m: float
    coverage_pct: float
    turns: int
    lane_segments: list[tuple[float, float, float, float]]

    def to_rows(self) -> list[dict]:
        return [{"lane": i + 1, "x1": a, "y1": b, "x2": c, "y2": d}
                for i, (a, b, c, d) in enumerate(self.lane_segments)]


def plan(pool: Pool, robot: Robot) -> Coverage:
    eff = robot.effective_swath
    if eff <= 0:
        raise ValueError("有效清洁宽度必须 >0")
    if pool.shape == "polygon" and pool.footprint:
        return _plan_polygon(pool, robot, eff)
    lanes = max(1, int(math.ceil(pool.width_m / eff - 1e-12)))
    # 每条 lane 沿 length 方向；横向步进 eff；到边界时 clamp
    segs = []
    y = min(eff / 2.0, pool.width_m / 2.0)
    for i in range(lanes):
        y0 = min(max(y, 0.0), pool.width_m)
        # 交替方向，形成连续 boustrophedon（视觉/CSV 用）
        if i % 2 == 0:
            segs.append((0.0, y0, pool.length_m, y0))
        else:
            segs.append((pool.length_m, y0, 0.0, y0))
        y += eff
    # 覆盖面积：每条 lane 的有效带宽 * 池长；最后一条可能超出池宽，按池宽截断
    coverage_area = 0.0
    for i in range(lanes):
        y0 = min(i * eff, pool.width_m)
        y1 = min((i + 1) * eff, pool.width_m)
        coverage_area += max(0.0, y1 - y0) * pool.length_m
    coverage = 100.0 * min(1.0, coverage_area / (pool.length_m * pool.width_m))
    # 路径：lane 长度 + 相邻 lane 的横向连接（近似）
    path = lanes * pool.length_m + max(0, lanes - 1) * eff
    return Coverage(lanes, eff, path, coverage, max(0, lanes - 1), segs)


def _plan_polygon(pool: Pool, robot: Robot, eff: float) -> Coverage:
    """扫描线 boustrophedon：支持 L 形/凹多边形/多个区间。

    每个 lane 取 y=eff/2+i*eff；求多边形交区间；区间之间走直线（travel），
    路径长度包含 travel；覆盖率按 区间长×有效宽度 / 多边形面积 截断。
    """
    pts = pool.footprint or []
    area = geo.polygon_area(pts)
    n_lanes = max(1, int(math.ceil(pool.width_m / eff - 1e-12)))
    segs: list[tuple[float, float, float, float]] = []
    prev = None
    path = 0.0
    lanes_used = 0
    for i in range(n_lanes):
        y = min(pool.width_m - 1e-9, eff / 2.0 + i * eff)
        if y <= 0:
            continue
        ints = geo.scanline_intervals(pts, y, 0.0, pool.length_m)
        if not ints:
            continue
        lanes_used += 1
        if i % 2 == 1:
            ints = list(reversed(ints))
        for (a, b) in ints:
            if i % 2 == 1:
                a, b = b, a
            if prev is not None:
                path += math.hypot(a - prev[0], y - prev[1])
            segs.append((a, y, b, y))
            path += abs(b - a)
            prev = (b, y)
    covered = 0.0
    for (a, _, b, _) in segs:
        covered += abs(b - a) * eff
    coverage = 100.0 * min(1.0, covered / area) if area else 0.0
    return Coverage(lanes_used, eff, path, coverage, max(0, len(segs) - 1), segs)


def write_csv(cov: Coverage, path: str | pathlib.Path) -> pathlib.Path:
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["lane", "x1", "y1", "x2", "y2"])
        w.writeheader()
        w.writerows(cov.to_rows())
    return p


def write_svg(cov: Coverage, pool: Pool, path: str | pathlib.Path) -> pathlib.Path:
    """俯视图：池体 + lane；不依赖外部库。"""
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    s = 50.0
    w, h = pool.length_m * s + 80, pool.width_m * s + 80
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" viewBox="0 0 {w:.0f} {h:.0f}">',
           '<rect width="100%" height="100%" fill="#0b1017"/>']
    if pool.shape == "polygon" and pool.footprint:
        pts = " ".join(f"{40+x*s:.2f},{40+y*s:.2f}" for x, y in pool.footprint)
        out.append(f'<polygon points="{pts}" fill="#12324a" stroke="#4da3ff" stroke-width="2"/>')
    else:
        out.append(f'<rect x="40" y="40" width="{pool.length_m*s:.2f}" height="{pool.width_m*s:.2f}" '
                   'fill="#12324a" stroke="#4da3ff" stroke-width="2"/>')
    out.append('<text x="40" y="28" fill="#e9f0f7" font-family="sans-serif" font-size="14">'
               f'AquaTwin coverage · {pool.area_m2:.1f}m² · '
               f'{cov.lanes} lanes · {cov.coverage_pct:.1f}%</text>')
    for i, (x1, y1, x2, y2) in enumerate(cov.lane_segments):
        out.append(f'<line x1="{40+x1*s:.2f}" y1="{40+y1*s:.2f}" '
                   f'x2="{40+x2*s:.2f}" y2="{40+y2*s:.2f}" '
                   f'stroke="#7bd1ff" stroke-width="2" opacity="0.85"/>')
        out.append(f'<text x="{40+x1*s+4:.2f}" y="{40+y1*s-3:.2f}" fill="#94a5b8" '
                   f'font-family="monospace" font-size="9">{i+1}</text>')
    out.append('</svg>')
    p.write_text("\n".join(out) + "\n", encoding="utf-8")
    return p


__all__ = ["Coverage", "plan", "write_csv", "write_svg"]
