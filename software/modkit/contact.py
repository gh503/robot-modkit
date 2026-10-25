"""夹持接触的最简模型：摩擦锥够不够，而不是"夹爪闭上就算抓住"。

只回答两个问题：
  · 给定夹持力/摩擦系数，能不能扛住方块重量 + 加速度？
  · 扛不住时是滑落，不是"任务失败但物体消失"。

不建接触力场、不做变形；参数都要在真机上标定（docs/47）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

G = 9.81


@dataclass(frozen=True)
class GraspSpec:
    mass_kg: float = 0.05       # 40mm 方块（PLA 实心约 45g）
    mu: float = 0.4             # 橡胶爪 ↔ PLA
    grip_force_n: float = 4.0   # 单侧法向力（舵机夹紧估算）
    safety: float = 1.5         # 抗扰动余量
    cube_size_mm: float = 40.0  # 方块边长
    max_opening_mm: float = 42.0  # 夹爪有效开口

    def fits(self) -> bool:
        return self.cube_size_mm <= self.max_opening_mm

    @property
    def friction_capacity_n(self) -> float:
        """两侧摩擦上限：2·μ·N。"""
        return 2.0 * self.mu * self.grip_force_n

    def required_n(self, accel_m_s2: float = 0.0) -> float:
        return self.mass_kg * math.hypot(G, accel_m_s2) * self.safety

    def holds(self, accel_m_s2: float = 0.0) -> bool:
        return self.fits() and self.friction_capacity_n >= self.required_n(accel_m_s2)

    @property
    def max_accel_m_s2(self) -> float:
        """不掉的最大竖直加速度；负值表示静止都夹不住。"""
        cap = self.friction_capacity_n / (self.mass_kg * self.safety)
        return math.sqrt(max(0.0, cap * cap - G * G)) if cap >= G else -1.0


@dataclass(frozen=True)
class Wrench:
    """腕部六维力：力 N / 力矩 N·m，基座系。"""
    fx: float = 0.0
    fy: float = 0.0
    fz: float = 0.0
    tx: float = 0.0
    ty: float = 0.0
    tz: float = 0.0

    @property
    def force_n(self) -> float:
        return math.sqrt(self.fx ** 2 + self.fy ** 2 + self.fz ** 2)

    @property
    def torque_nm(self) -> float:
        return math.sqrt(self.tx ** 2 + self.ty ** 2 + self.tz ** 2)

    def to_dict(self) -> dict:
        return {"fx": round(self.fx, 4), "fy": round(self.fy, 4),
                "fz": round(self.fz, 4), "tx": round(self.tx, 5),
                "ty": round(self.ty, 5), "tz": round(self.tz, 5)}


@dataclass
class GraspDynamics:
    """带柔性/滑动的夹持：法向 N，切向先弹簧、超摩擦锥后动摩擦滑移。

    坐标约定：夹爪沿 ±X 夹紧，重力沿 -Z；切向负载来自 Y/Z 加速度。
    不是有限元：只给"滑了多少毫米、掉没掉、腕部受力多少"。
    """
    spec: GraspSpec = field(default_factory=GraspSpec)
    mu_k: float | None = None          # 动摩擦，默认 0.8×静摩擦
    stiffness_n_per_mm: float = 40.0   # 切向柔度
    slip_limit_mm: float = 18.0        # 方块半长 20mm，滑出即掉
    slip_mm: float = 0.0
    slip_velocity_mm_s: float = 0.0
    dropped: bool = False
    state: str = "hold"
    wrench: Wrench = field(default_factory=Wrench)

    def __post_init__(self):
        if self.mu_k is None:
            self.mu_k = 0.8 * self.spec.mu

    @property
    def static_capacity_n(self) -> float:
        return 2.0 * self.spec.mu * self.spec.grip_force_n

    @property
    def kinetic_capacity_n(self) -> float:
        return 2.0 * self.mu_k * self.spec.grip_force_n

    def update(self, dt: float, ax: float = 0.0, ay: float = 0.0,
               az: float = 0.0) -> "GraspDynamics":
        m = self.spec.mass_kg
        load = m * math.hypot(ay, G + az)
        # 腕部感受到的支撑力 + 方块质心在腕下 30mm 的力矩
        fx, fy, fz = m * ax, m * ay, m * (G + az)
        r_z = -0.030
        tx, ty = -r_z * fy, r_z * fx
        self.wrench = Wrench(fx, fy, fz, tx, ty, 0.0)

        if not self.spec.fits():
            self.dropped = True
            self.state = "drop"
            return self
        if load <= self.static_capacity_n:
            self.state = "hold"
            self.slip_velocity_mm_s = 0.0
            self.slip_mm = min(load / self.stiffness_n_per_mm, self.slip_limit_mm)
            return self

        # 超过静摩擦：动摩擦 + 相对加速度，滑移累积
        self.state = "slip"
        excess = load - self.kinetic_capacity_n
        # m/s² → mm/s，别把单位混了
        self.slip_velocity_mm_s += max(0.0, excess / m) * 1000.0 * dt
        self.slip_mm += self.slip_velocity_mm_s * dt
        if self.slip_mm >= self.slip_limit_mm:
            self.slip_mm = self.slip_limit_mm
            self.dropped = True
            self.state = "drop"
        return self

    def to_dict(self) -> dict:
        return {"state": self.state, "slip_mm": round(self.slip_mm, 2),
                "dropped": self.dropped,
                "static_capacity_n": round(self.static_capacity_n, 3),
                "wrench": self.wrench.to_dict()}
