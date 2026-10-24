"""里程计标定：把"走了 1m，里程计说 0.93m"这一步算成系数。

为什么要标定：
  · 轮子实际直径受打印/磨损影响（65mm 轮可能只有 64.2mm）；
  · 轮距受装配公差影响，转弯角度会系统性偏；
  · 这两个误差都会随距离累积，视觉/导航之前必须先修。

方法（两点法）：
  1. 直线：地上量 1000mm，直行，读左右轮 tick 增量 → straight_scale
  2. 原地转：转 90°，读左右轮反向 tick → turn_scale
  3. 写回 DriveGeometry 的 wheel_r / track

用法：
    modkit odomcal --action straight --ticks 3900 --distance 1000
    modkit odomcal --action turn --left-ticks 512 --right-ticks -500 --deg 90
"""

from __future__ import annotations

import json
import math
import pathlib
from dataclasses import asdict, dataclass

from . import kinematics as kin


class OdomCalError(RuntimeError):
    pass


@dataclass
class OdomCal:
    wheel_r_mm: float = 32.5
    track_mm: float = 150.0
    ticks_per_rev: int = 4096
    straight_scale: float = 1.0      # 实测 / 理论
    turn_scale: float = 1.0
    measured_distance_mm: float = 0.0
    measured_turn_deg: float = 0.0

    # ---------------------------------------------------------------- 计算
    def predicted_distance(self, ticks: float) -> float:
        return ticks * 2 * math.pi * self.wheel_r_mm / self.ticks_per_rev

    def apply_straight(self, ticks: float, measured_mm: float) -> float:
        """返回新的 straight_scale，并按比例修正轮半径。"""
        if ticks <= 0:
            raise OdomCalError("tick 增量必须为正（先让它向前走）")
        if measured_mm <= 0:
            raise OdomCalError("实测距离必须为正")
        pred = self.predicted_distance(ticks)
        self.straight_scale = measured_mm / pred
        self.measured_distance_mm = measured_mm
        self.wheel_r_mm = self.wheel_r_mm * self.straight_scale
        return self.straight_scale

    def apply_turn(self, left_ticks: float, right_ticks: float, measured_deg: float) -> float:
        """原地转：理论转角 = (dr-dl)/track，实测角反推有效轮距。"""
        if measured_deg <= 0:
            raise OdomCalError("实测转角必须为正")
        dl = left_ticks * 2 * math.pi * self.wheel_r_mm / self.ticks_per_rev
        dr = right_ticks * 2 * math.pi * self.wheel_r_mm / self.ticks_per_rev
        arc = (dr - dl) / 2.0                       # 差速弧长
        if abs(arc) < 1e-6:
            raise OdomCalError("左右轮几乎没差速，检查是不是真的在转")
        theoretical_deg = math.degrees(arc / (self.track_mm / 2.0))
        self.turn_scale = measured_deg / theoretical_deg
        self.measured_turn_deg = measured_deg
        self.track_mm = self.track_mm * self.turn_scale
        return self.turn_scale

    def geometry(self) -> kin.DriveGeometry:
        return kin.DriveGeometry(wheel_r=self.wheel_r_mm, track=self.track_mm,
                                 ticks_per_rev=self.ticks_per_rev)

    # ---------------------------------------------------------------- 存取
    def save(self, path: str | pathlib.Path) -> pathlib.Path:
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: str | pathlib.Path) -> "OdomCal":
        return cls(**json.loads(pathlib.Path(path).read_text(encoding="utf-8")))

    def summary(self) -> str:
        return (f"轮半径 {self.wheel_r_mm:.2f}mm（scale {self.straight_scale:.4f}）、"
                f"轮距 {self.track_mm:.1f}mm（scale {self.turn_scale:.4f}）")
