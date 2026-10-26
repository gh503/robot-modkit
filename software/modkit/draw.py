"""离线绘图路径：逆解 → CSV/SVG；仿真或带安全策略回放。

为什么单独做：阶段 1/3 买回来最想验证的是“能不能按坐标动”。
先把路径、关节角、限位和回放跑通，硬件到了只需要确认方向和零位。

边界：
  · 3 自由度臂（yaw+shoulder+elbow）默认 `--mode arm`，可画方/圆/三角；
  · 2 自由度极坐标臂（yaw+shoulder，固定上臂）只能画圆弧，`--mode polar`；
  · 回放默认仿真；真机必须显式 `--port ... --yes`，并走 SafetyPolicy；
  · 不控制抬笔/落笔，不补偿笔尖偏置/纸面倾斜。
"""

from __future__ import annotations

import csv
import io
import math
import pathlib
import time
from dataclasses import dataclass
from typing import Iterable

from . import kinematics as kin
from . import protocol as p
from . import safety


class DrawError(ValueError):
    pass


@dataclass(frozen=True)
class DrawPoint:
    x: float
    y: float
    z: float
    yaw: float
    shoulder: float
    elbow: float | None
    mode: str

    def as_dict(self) -> dict:
        return {"x": round(self.x, 2), "y": round(self.y, 2), "z": round(self.z, 2),
                "yaw": round(self.yaw, 2), "shoulder": round(self.shoulder, 2),
                "elbow": None if self.elbow is None else round(self.elbow, 2),
                "mode": self.mode}


def _polyline(points: Iterable[tuple[float, float]], step: float,
              closed: bool = False) -> list[tuple[float, float]]:
    pts = list(points)
    if closed and pts and pts[0] != pts[-1]:
        pts.append(pts[0])
    out: list[tuple[float, float]] = []
    for a, b in zip(pts, pts[1:]):
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(math.ceil(d / max(0.5, step))))
        for i in range(n):
            t = i / n
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    if pts:
        out.append(pts[-1])
    # 去掉连续重复点
    clean = []
    for q in out:
        if not clean or math.hypot(q[0] - clean[-1][0], q[1] - clean[-1][1]) > 1e-6:
            clean.append(q)
    return clean


def _vertices(shape: str, size: float, cx: float, cy: float) -> list[tuple[float, float]]:
    h = size / 2.0
    if shape == "square":
        return [(cx - h, cy - h), (cx + h, cy - h), (cx + h, cy + h), (cx - h, cy + h)]
    if shape == "triangle":
        return [(cx, cy + h), (cx - h * 0.866, cy - h / 2), (cx + h * 0.866, cy - h / 2)]
    if shape == "line":
        return [(cx - h, cy), (cx + h, cy)]
    raise DrawError(f"未知形状：{shape}")


def build_path(shape: str = "square", *, mode: str = "arm", size: float = 100.0,
               z: float = 150.0, cx: float = 150.0, cy: float = 0.0,
               radius: float = 50.0, sweep: float = 240.0, step: float = 5.0,
               l1: float = 120.0, l2: float = 110.0, base_h: float = 90.0) -> list[DrawPoint]:
    """生成路径；arm 用 3DOF 逆解，polar 用固定半径圆弧。"""
    if step <= 0:
        raise DrawError("step 必须 >0")
    if mode == "polar":
        if shape != "arc":
            raise DrawError("polar 模式只支持 --shape arc")
        if not (0 < sweep <= 240.0):
            raise DrawError("sweep 必须在 (0,240]；yaw 设计限位 ±120°")
        if not (0 < radius <= l1):
            raise DrawError(f"radius 必须在 (0,{l1}]")
        shoulder = math.degrees(math.acos(max(-1.0, min(1.0, radius / l1))))
        zz = base_h + l1 * math.sin(math.radians(shoulder))
        n = max(8, int(math.ceil(math.radians(sweep) * radius / max(1.0, step))))
        out = []
        for i in range(n + 1):
            yaw = -sweep / 2 + sweep * i / n
            out.append(DrawPoint(radius * math.cos(math.radians(yaw)),
                                 radius * math.sin(math.radians(yaw)),
                                 zz, yaw, shoulder, None, "polar"))
        return out
    if mode != "arm":
        raise DrawError("mode 只能是 arm 或 polar")
    if shape == "arc":
        raise DrawError("arc 只支持 --mode polar")
    if shape == "circle":
        n = max(24, int(math.ceil(2 * math.pi * radius / max(1.0, step))))
        pts = [(cx + radius * math.cos(2 * math.pi * i / n),
                cy + radius * math.sin(2 * math.pi * i / n)) for i in range(n + 1)]
    else:
        pts = _polyline(_vertices(shape, size, cx, cy), step, closed=shape != "line")
    geom = kin.ArmGeometry(l1=l1, l2=l2, base_h=base_h)
    out = []
    for x, y in pts:
        try:
            yaw, shoulder, elbow = kin.inverse(geom, kin.Pose(x, y, z))
        except kin.UnreachableError as e:
            raise DrawError(f"点 ({x:.1f},{y:.1f},{z:.1f}) 不可达：{e}") from e
        out.append(DrawPoint(x, y, z, yaw, shoulder, elbow, "arm"))
    return out


def stats(points: list[DrawPoint]) -> dict:
    if not points:
        raise DrawError("空路径")
    names = ("yaw", "shoulder", "elbow")
    maxd = {k: 0.0 for k in names}
    for a, b in zip(points, points[1:]):
        for k in names:
            va, vb = getattr(a, k), getattr(b, k)
            if va is not None and vb is not None:
                maxd[k] = max(maxd[k], abs(vb - va))
    path_len = sum(math.hypot(b.x - a.x, b.y - a.y) for a, b in zip(points, points[1:]))
    return {"points": len(points), "mode": points[0].mode,
            "x": [round(min(p.x for p in points), 1), round(max(p.x for p in points), 1)],
            "y": [round(min(p.y for p in points), 1), round(max(p.y for p in points), 1)],
            "z": [round(min(p.z for p in points), 1), round(max(p.z for p in points), 1)],
            "path_mm": round(path_len, 1),
            "max_delta_deg": {k: round(v, 2) for k, v in maxd.items()},
            "max_step_ok": all(v <= 8.0 for v in maxd.values()),
            "elbow_used": any(p.elbow is not None for p in points)}


def to_csv(points: list[DrawPoint]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["i", "x_mm", "y_mm", "z_mm", "yaw_deg", "shoulder_deg", "elbow_deg",
                "yaw_ticks", "shoulder_ticks", "elbow_ticks", "mode"])
    for i, q in enumerate(points):
        ticks = kin.joint_ticks(kin.ArmGeometry(), q.yaw, q.shoulder,
                                q.elbow if q.elbow is not None else 0.0)
        w.writerow([i, f"{q.x:.2f}", f"{q.y:.2f}", f"{q.z:.2f}", f"{q.yaw:.2f}",
                    f"{q.shoulder:.2f}", "" if q.elbow is None else f"{q.elbow:.2f}",
                    ticks[0], ticks[1], "" if q.elbow is None else ticks[2], q.mode])
    return "\ufeff" + buf.getvalue()


def to_svg(points: list[DrawPoint], width: int = 620, height: int = 520) -> str:
    xs = [p.x for p in points] + [0.0]
    ys = [p.y for p in points] + [0.0]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    span = max(1.0, maxx - minx, maxy - miny)
    scale = min((width - 80) / span, (height - 80) / span)
    ox = 40 - minx * scale
    oy = height - 40 + miny * scale

    def sx(x: float) -> float: return ox + x * scale
    def sy(y: float) -> float: return oy - y * scale

    path = " ".join(f"{sx(p.x):.1f},{sy(p.y):.1f}" for p in points)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}" font-family="sans-serif">',
           '<rect width="100%" height="100%" fill="#f7f6f2"/>',
           f'<text x="24" y="28" font-size="16" font-weight="bold">绘图路径 · {points[0].mode}</text>',
           f'<text x="24" y="48" font-size="11" fill="#666">{len(points)} 点 · '
           f'{stats(points)["path_mm"]:.0f}mm</text>',
           f'<line x1="{sx(0):.1f}" y1="40" x2="{sx(0):.1f}" y2="{height-20}" stroke="#ddd"/>',
           f'<line x1="20" y1="{sy(0):.1f}" x2="{width-20}" y2="{sy(0):.1f}" stroke="#ddd"/>',
           f'<polyline points="{path}" fill="none" stroke="#c0392b" stroke-width="2"/>',
           f'<circle cx="{sx(points[0].x):.1f}" cy="{sy(points[0].y):.1f}" r="4" fill="#2b7a4b"/>',
           f'<circle cx="{sx(points[-1].x):.1f}" cy="{sy(points[-1].y):.1f}" r="4" fill="#2b4c7a"/>',
           f'<text x="{sx(points[0].x)+6:.1f}" y="{sy(points[0].y)-6:.1f}" font-size="10" fill="#2b7a4b">start</text>',
           f'<text x="{sx(points[-1].x)+6:.1f}" y="{sy(points[-1].y)+14:.1f}" font-size="10" fill="#2b4c7a">end</text>',
           '</svg>']
    return "\n".join(out)


def play(points: list[DrawPoint], *, port: str | None = None, sim: bool = True,
         speed: int = 150, settle: float = 0.25, yes: bool = False,
         calibration: str | None = None) -> dict:
    """回放路径；默认仿真。真机必须 port + yes。"""
    if not sim and not port:
        raise DrawError("真机回放需要 --port；没有 port 请用 --sim")
    if not sim and not yes:
        raise DrawError("真机回放必须显式 --yes（先空载/低速/手放急停）")
    from . import bus
    from .robot import Robot

    ids = sorted({1, 2} | ({3} if any(p.elbow is not None for p in points) else set()))
    link = bus.SimLink(ids) if sim else bus.SerialLink(port).open()
    robot = Robot(link)
    used = ["yaw", "shoulder"] + (["elbow"] if any(p.elbow is not None for p in points) else [])
    policy = (safety.SafetyPolicy.from_calibration(calibration)
              if calibration else safety.SafetyPolicy.defaults())
    # 只保留本次用到的轴：默认策略含 gripper/elbow，缺对应舵机时 preflight 会拒绝。
    policy.joints = {n: policy.joints[n] for n in used if n in policy.joints}
    policy.calibrated_joints &= set(policy.joints)
    policy.speed = speed
    def current(name: str) -> float:
        try:
            fb = robot.feedback(policy.joint(name).servo_id)
            return policy.joint(name).from_servo_deg(fb.position_deg)
        except Exception:
            return 0.0

    def send(name: str, target: float) -> None:
        if "elbow" in policy.joints:
            robot.goto_checked(name, target, policy, speed=speed)
            return
        # 2DOF 极坐标模式没有 elbow；Robot._assert_path 固定检查三轴，
        # 这里只做 guard_motion + 单轴下发，避免要求不存在的舵机。
        d = policy.guard_motion(robot, {name: target})
        if not d.ok:
            raise ValueError(f"{d.code}: {d.message}")
        j = policy.joint(name)
        policy.apply_limits(robot, [j.servo_id])
        robot.goto(j.servo_id, j.to_servo_deg(target), speed=speed, acc=policy.acc)

    def approach(name: str, target: float) -> None:
        """从当前角分步到首点，避免首点跳变触发 max_step 拒绝。"""
        cur = current(name)
        lim = max(0.5, policy.joint(name).max_step * 0.8)
        while abs(target - cur) > 1e-6:
            step = max(-lim, min(lim, target - cur))
            cur += step
            send(name, cur)
            if settle > 0:
                time.sleep(settle)

    sent = 0
    try:
        first = points[0]
        for name in ("yaw", "shoulder", "elbow"):
            val = getattr(first, name)
            if val is not None:
                approach(name, val)
        for q in points:
            send("yaw", q.yaw)
            send("shoulder", q.shoulder)
            if q.elbow is not None:
                send("elbow", q.elbow)
            sent += 1
            if settle > 0:
                time.sleep(settle)
    finally:
        if not sim and hasattr(link, "close"):
            link.close()
    return {"played": sent, "sim": sim, "port": port, "speed": speed,
            "ids": ids, "calibrated": bool(policy.calibrated)}


__all__ = ["DrawError", "DrawPoint", "build_path", "stats", "to_csv", "to_svg", "play"]
