"""夹持接触的最简模型：摩擦锥够不够，而不是"夹爪闭上就算抓住"。

只回答两个问题：
  · 给定夹持力/摩擦系数，能不能扛住方块重量 + 加速度？
  · 扛不住时是滑落，不是"任务失败但物体消失"。

不建接触力场、不做变形；参数都要在真机上标定（docs/47）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

G = 9.81


@dataclass(frozen=True)
class GraspSpec:
    mass_kg: float = 0.05       # 40mm 方块（PLA 实心约 45g）
    mu: float = 0.4             # 橡胶爪 ↔ PLA
    grip_force_n: float = 4.0   # 单侧法向力（舵机夹紧估算）
    safety: float = 1.5         # 抗扰动余量

    @property
    def friction_capacity_n(self) -> float:
        """两侧摩擦上限：2·μ·N。"""
        return 2.0 * self.mu * self.grip_force_n

    def required_n(self, accel_m_s2: float = 0.0) -> float:
        return self.mass_kg * math.hypot(G, accel_m_s2) * self.safety

    def holds(self, accel_m_s2: float = 0.0) -> bool:
        return self.friction_capacity_n >= self.required_n(accel_m_s2)

    @property
    def max_accel_m_s2(self) -> float:
        """不掉的最大竖直加速度；负值表示静止都夹不住。"""
        cap = self.friction_capacity_n / (self.mass_kg * self.safety)
        return math.sqrt(max(0.0, cap * cap - G * G)) if cap >= G else -1.0
