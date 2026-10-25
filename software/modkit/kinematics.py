"""运动学：4 自由度臂（偏航 + 肩 + 肘 + 夹爪）与差速底盘里程计。

为什么单独一个模块：运动学是"能用"和"乱撞"的分界线，而且它**完全不需要硬件**
就能验证。先让数学对上，再让电机动。

坐标与角度约定（全项目统一，写进 docs/02-接口规范.md）：

    底盘：x 向前，y 向左，z 向上，右手系；yaw 逆时针为正
    臂  ：θ1 = 底座偏航（绕 z 轴，0° 指向 +x）
          α  = 肩角，水平向前为 0°，向上为正
          β  = 肘角，相对上臂的偏转角，向内（肘部朝下）为负
    长度单位 mm，角度单位度（对外），内部弧度。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from . import protocol as _p


class UnreachableError(ValueError):
    """目标点超出工作空间。"""


# ---------------------------------------------------------------- 臂
@dataclass(frozen=True)
class ArmGeometry:
    base_h: float = 90.0    # 偏航轴到地面的高度
    l1: float = 120.0       # 肩→肘
    l2: float = 110.0       # 肘→腕
    yaw_limit: float = 120.0     # ±度
    shoulder_min: float = -25.0
    shoulder_max: float = 100.0
    elbow_min: float = -150.0
    elbow_max: float = 5.0

    @property
    def reach_max(self) -> float:
        return self.l1 + self.l2

    @property
    def reach_min(self) -> float:
        return abs(self.l1 - self.l2)


@dataclass(frozen=True)
class Pose:
    x: float
    y: float
    z: float


def forward(geom: ArmGeometry, yaw_deg: float, shoulder_deg: float, elbow_deg: float) -> Pose:
    """关节角 → 末端位置（机器人坐标系）。"""
    yaw = math.radians(yaw_deg)
    a = math.radians(shoulder_deg)
    b = math.radians(elbow_deg)

    d = geom.l1 * math.cos(a) + geom.l2 * math.cos(a + b)
    z = geom.base_h + geom.l1 * math.sin(a) + geom.l2 * math.sin(a + b)
    return Pose(d * math.cos(yaw), d * math.sin(yaw), z)


def inverse(geom: ArmGeometry, target: Pose, elbow_up: bool = False) -> tuple[float, float, float]:
    """末端位置 → 关节角（度）。不可达时抛 UnreachableError。

    两解：肘上 / 肘下。默认"肘下"（β 为负，符合常见桌面臂姿态）。
    """
    d = math.hypot(target.x, target.y)
    if d < 1e-6:
        yaw = 0.0
    else:
        yaw = math.degrees(math.atan2(target.y, target.x))
    if abs(yaw) > geom.yaw_limit + 1e-9:
        raise UnreachableError(f"偏航 {yaw:.1f}° 超出 ±{geom.yaw_limit}°")

    u = d
    v = target.z - geom.base_h
    r2 = u * u + v * v
    r = math.sqrt(r2)

    # 腕点够不到，或太近（收进自己的肩里）
    if r > geom.reach_max + 1e-6:
        raise UnreachableError(f"距离 {r:.1f}mm 超出最大臂展 {geom.reach_max:.1f}mm")
    if r < geom.reach_min - 1e-6:
        raise UnreachableError(f"距离 {r:.1f}mm 小于最小臂展 {geom.reach_min:.1f}mm")

    cos_elbow = (r2 - geom.l1**2 - geom.l2**2) / (2 * geom.l1 * geom.l2)
    cos_elbow = max(-1.0, min(1.0, cos_elbow))
    elbow_mag = math.degrees(math.acos(cos_elbow))
    elbow = elbow_mag if elbow_up else -elbow_mag

    # 肩角闭式解：φ = α + atan2(l2·sinβ, l1 + l2·cosβ)  ⇒  α = φ − atan2(...)
    # 不要用 φ ± 三角形内角：肘上/肘下两种解的符号会反，是这类实现最常见的 bug。
    # 这个符号当初写反过一次，靠 test_forward_ik_roundtrip 抓出来的。
    phi = math.degrees(math.atan2(v, u))
    beta = math.radians(elbow)
    shoulder = phi - math.degrees(
        math.atan2(geom.l2 * math.sin(beta), geom.l1 + geom.l2 * math.cos(beta))
    )

    _check(geom, yaw, shoulder, elbow)
    return yaw, shoulder, elbow


def _check(geom: ArmGeometry, yaw: float, shoulder: float, elbow: float) -> None:
    if abs(yaw) > geom.yaw_limit + 0.5:
        raise UnreachableError(f"偏航 {yaw:.1f}° 超限")
    if not geom.shoulder_min - 0.5 <= shoulder <= geom.shoulder_max + 0.5:
        raise UnreachableError(f"肩角 {shoulder:.1f}° 超出 [{geom.shoulder_min}, {geom.shoulder_max}]")
    if not geom.elbow_min - 0.5 <= elbow <= geom.elbow_max + 0.5:
        raise UnreachableError(f"肘角 {elbow:.1f}° 超出 [{geom.elbow_min}, {geom.elbow_max}]")


def joint_ticks(geom: ArmGeometry, yaw: float, shoulder: float, elbow: float) -> tuple[int, int, int]:
    """关节角（度）→ 舵机计数。零位定义见 docs/05-装配手册.md 的标定流程。

    约定：舵机 0°（计数 2048）对应"臂完全水平向前、肘伸直"，因此：
        肩舵机计数 = 2048 + shoulder_deg / DEG_PER_TICK
        肘舵机计数 = 2048 - elbow_deg / DEG_PER_TICK   （肘角向内为负 → 计数变大）
        偏航计数   = 2048 + yaw_deg / DEG_PER_TICK
    """
    k = 1.0 / _p.DEG_PER_TICK

    def to_ticks(v: float) -> int:
        return max(0, min(_p.TICKS_PER_REV - 1, round(v)))

    return (
        to_ticks(2048 + yaw * k),
        to_ticks(2048 + shoulder * k),
        to_ticks(2048 - elbow * k),
    )


def ticks_to_joints(yaw_ticks: int, shoulder_ticks: int, elbow_ticks: int) -> tuple[float, float, float]:
    k = _p.DEG_PER_TICK
    return (
        (yaw_ticks - 2048) * k,
        (shoulder_ticks - 2048) * k,
        -(elbow_ticks - 2048) * k,
    )


# ---------------------------------------------------------------- 差速底盘
@dataclass(frozen=True)
class DriveGeometry:
    wheel_r: float = 32.5      # 轮半径（65mm 轮）
    track: float = 150.0       # 左右轮距
    ticks_per_rev: int = 4096

    @property
    def mm_per_tick(self) -> float:
        return 2 * math.pi * self.wheel_r / self.ticks_per_rev


@dataclass
class OdomState:
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0     # 度
    left_ticks: int = 0
    right_ticks: int = 0


def tick_delta(new: int, old: int, ticks_per_rev: int = 4096) -> int:
    """位置计数是 0..4095 循环的，直接相减会在过零时跳 4096。"""
    return (new - old + ticks_per_rev // 2) % ticks_per_rev - ticks_per_rev // 2


def update_odom(geom: DriveGeometry, st: OdomState, left_ticks: int, right_ticks: int) -> OdomState:
    """增量式里程计（中点法）。输入是舵机反馈的累计位置计数。

    注意：轮子用"恒速模式"驱动时，位置计数仍然可读 —— 这正是用总线舵机当驱动轮的
    最大好处：不需要额外编码器。
    """
    dl = tick_delta(left_ticks, st.left_ticks, geom.ticks_per_rev) * geom.mm_per_tick
    dr = tick_delta(right_ticks, st.right_ticks, geom.ticks_per_rev) * geom.mm_per_tick
    ds = (dl + dr) / 2.0
    dyaw = math.degrees((dr - dl) / geom.track)

    yaw_mid = math.radians(st.yaw + dyaw / 2.0)
    st.x += ds * math.cos(yaw_mid)
    st.y += ds * math.sin(yaw_mid)
    st.yaw = (st.yaw + dyaw + 180.0) % 360.0 - 180.0
    st.left_ticks = left_ticks
    st.right_ticks = right_ticks
    return st


def wheel_speeds(v_mm_s: float, w_deg_s: float, geom: DriveGeometry) -> tuple[float, float]:
    """车体速度 → 左右轮线速度（mm/s）。w 逆时针为正。"""
    half = math.radians(w_deg_s) * geom.track / 2.0
    return v_mm_s - half, v_mm_s + half