"""M2 导航第一步：把"去某个点"做成可测试的控制器。

为什么先做这个：
  · 里程计标定完（docs/29）只知道"走了多远"，还不知道"怎么走过去"；
  · 视觉/抓取之前必须能稳定到达工位，否则每次都要人摆；
  · 控制器是纯函数 + 单轮车模型，可以在没有硬件时把边界跑完。

坐标：x 向前、y 向左、theta 逆时针为正（度）；单位 mm、mm/s、deg/s。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import kinematics as kin


def wrap(deg: float) -> float:
    """把角度折到 (-180, 180]。"""
    d = (deg + 180.0) % 360.0 - 180.0
    return 180.0 if d == -180.0 else d


@dataclass
class Pose:
    x: float = 0.0
    y: float = 0.0
    theta: float = 0.0          # 度

    def distance_to(self, other: "Pose") -> float:
        return math.hypot(other.x - self.x, other.y - self.y)

    def heading_to(self, other: "Pose") -> float:
        return math.degrees(math.atan2(other.y - self.y, other.x - self.x))


@dataclass
class NavConfig:
    v_max: float = 150.0        # mm/s
    w_max: float = 90.0         # deg/s
    k_rot: float = 2.5          # 1/s
    k_lat: float = 2.0          # 横向修正增益
    pos_tol: float = 8.0        # mm
    ang_tol: float = 3.0        # 度
    slow_radius: float = 120.0  # mm，进入后线性减速
    rotate_first: float = 50.0  # 度，误差大于它就原地转


def goto_step(pose: Pose, goal: Pose, cfg: NavConfig | None = None) -> tuple[float, float, bool]:
    """返回 (v, w, done)。到点后 v=w=0。"""
    cfg = cfg or NavConfig()
    dist = pose.distance_to(goal)
    err = wrap(goal.theta - pose.theta)
    if dist < cfg.pos_tol and abs(err) < cfg.ang_tol:
        return 0.0, 0.0, True

    if dist < cfg.pos_tol:
        # 位置到了，只修朝向
        w = max(-cfg.w_max, min(cfg.w_max, cfg.k_rot * err))
        return 0.0, w, abs(err) < cfg.ang_tol

    bearing = wrap(pose.heading_to(goal) - pose.theta)
    if abs(bearing) > cfg.rotate_first:
        w = max(-cfg.w_max, min(cfg.w_max, cfg.k_rot * bearing))
        return 0.0, w, False

    # 边走边修：横向误差用 bearing 的一阶项
    v = cfg.v_max
    if dist < cfg.slow_radius:
        v = max(25.0, cfg.v_max * dist / cfg.slow_radius)
    v *= max(0.25, math.cos(math.radians(bearing)))
    w = max(-cfg.w_max, min(cfg.w_max, cfg.k_lat * bearing))
    return v, w, False


@dataclass
class Unicycle:
    """理想单轮车：测试控制器用，不掺电机/打滑。"""
    pose: Pose = field(default_factory=Pose)

    def step(self, v: float, w: float, dt: float) -> Pose:
        rad = math.radians(self.pose.theta)
        self.pose.x += v * math.cos(rad) * dt
        self.pose.y += v * math.sin(rad) * dt
        self.pose.theta = wrap(self.pose.theta + w * dt)
        return self.pose


@dataclass
class NavResult:
    trace: list[Pose]
    final: Pose
    seconds: float
    error_mm: float
    error_deg: float
    ok: bool


def drive_to(start: Pose, goal: Pose, cfg: NavConfig | None = None,
             dt: float = 0.02, max_seconds: float = 60.0) -> NavResult:
    cfg = cfg or NavConfig()
    plant = Unicycle(Pose(start.x, start.y, start.theta))
    trace = [Pose(start.x, start.y, start.theta)]
    t = 0.0
    done = False
    while t < max_seconds:
        v, w, done = goto_step(plant.pose, goal, cfg)
        if done:
            break
        plant.step(v, w, dt)
        trace.append(Pose(plant.pose.x, plant.pose.y, plant.pose.theta))
        t += dt
    err_mm = plant.pose.distance_to(goal)
    err_deg = abs(wrap(goal.theta - plant.pose.theta))
    ok = err_mm <= max(cfg.pos_tol, 10.0) and err_deg <= max(cfg.ang_tol, 5.0)
    return NavResult(trace, plant.pose, t, err_mm, err_deg, ok)


def follow(start: Pose, waypoints: list[Pose], cfg: NavConfig | None = None,
           dt: float = 0.02, max_seconds: float = 120.0) -> tuple[list[NavResult], bool]:
    """依次到每个点；任何一段失败就停。"""
    pose = Pose(start.x, start.y, start.theta)
    results: list[NavResult] = []
    used = 0.0
    for wp in waypoints:
        res = drive_to(pose, wp, cfg, dt, max_seconds - used)
        results.append(res)
        pose = res.final
        used += res.seconds
        if not res.ok:
            return results, False
    return results, True


def square_waypoints(size: float = 300.0, start: Pose | None = None) -> list[Pose]:
    """边长 size 的正方形，回到起点。朝向沿边。"""
    s = start or Pose()
    return [
        Pose(s.x + size, s.y, 0.0),
        Pose(s.x + size, s.y + size, 90.0),
        Pose(s.x, s.y + size, 180.0),
        Pose(s.x, s.y, 270.0),
    ]


def to_wheels(v_mm_s: float, w_deg_s: float,
              geom: kin.DriveGeometry | None = None) -> tuple[float, float]:
    """给真机用：线速度/角速度 → 左右轮线速度（mm/s）。"""
    return kin.wheel_speeds(v_mm_s, w_deg_s, geom or kin.DriveGeometry())
