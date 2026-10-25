"""离线几何包络：在发指令之前排除"数学可达但机械上不该去"的姿态。

这里只做**保守近似**，不是完整碰撞检测：
- 末端低于桌面 / 伸进底座圆柱 / 超出臂展；
- 肩肘折叠到可能夹住底座的区域。

它不能替代真机手转一圈和限位标定，但能把最常见的自碰撞指令挡在上位机侧。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from . import kinematics as kin


@dataclass(frozen=True)
class Envelope:
    table_z: float = 12.0          # 指尖最低高度 mm
    base_clear_r: float = 72.0     # 底座/立柱避让半径 mm
    base_clear_z: float = 130.0    # 低于这个高度时检查避让
    gripper_len: float = 60.0      # 腕→指尖；与 web/viewer.js 的 gripperLen 同源
    max_reach: float = 300.0       # l1 + l2 + gripper_len + 10
    min_reach: float = 8.0


def check_pose(geom: kin.ArmGeometry, yaw: float, shoulder: float, elbow: float,
               env: Envelope | None = None) -> list[str]:
    """返回问题列表；空列表表示通过。角度为关节角（度）。"""
    env = env or Envelope()
    problems: list[str] = []

    if abs(yaw) > geom.yaw_limit + 0.5:
        problems.append(f"偏航 {yaw:.1f}° 超出 ±{geom.yaw_limit:.0f}°")
    if not geom.shoulder_min - 0.5 <= shoulder <= geom.shoulder_max + 0.5:
        problems.append(f"肩 {shoulder:.1f}° 超出 [{geom.shoulder_min:.0f}, {geom.shoulder_max:.0f}]")
    if not geom.elbow_min - 0.5 <= elbow <= geom.elbow_max + 0.5:
        problems.append(f"肘 {elbow:.1f}° 超出 [{geom.elbow_min:.0f}, {geom.elbow_max:.0f}]")

    p = kin.forward(geom, yaw, shoulder, elbow)
    # forward() 给的是腕点；夹爪沿前臂再伸出 gripper_len，安全检查要按指尖算。
    g = math.radians(shoulder + elbow)
    tip_x = p.x + env.gripper_len * math.cos(g) * math.cos(math.radians(yaw))
    tip_y = p.y + env.gripper_len * math.cos(g) * math.sin(math.radians(yaw))
    tip_z = p.z + env.gripper_len * math.sin(g)
    d = math.hypot(tip_x, tip_y)
    if tip_z < env.table_z:
        problems.append(f"指尖高度 {tip_z:.1f}mm 低于桌面安全线 {env.table_z:.0f}mm")
    if d > env.max_reach:
        problems.append(f"水平伸展 {d:.1f}mm 超出安全臂展 {env.max_reach:.0f}mm")
    if tip_z < env.base_clear_z and d < env.base_clear_r:
        problems.append(f"末端进入底座避让区（r={d:.1f}mm < {env.base_clear_r:.0f}mm, z={tip_z:.1f}mm）")

    # 折叠过深时，上臂/肘部容易扫到立柱。用保守角度组合拦，不做完整连杆距离。
    if elbow < -140 and shoulder < 10 and d < 95:
        problems.append("肩肘折叠过深，可能夹住底座立柱")
    return problems


def check_joint_target(geom: kin.ArmGeometry, name: str, value: float,
                       env: Envelope | None = None) -> list[str]:
    """单关节预检；无法判断整体姿态时只查该轴限位。"""
    out: list[str] = []
    if name == "yaw" and abs(value) > geom.yaw_limit + 0.5:
        out.append(f"偏航 {value:.1f}° 超限")
    if name == "shoulder" and not geom.shoulder_min - 0.5 <= value <= geom.shoulder_max + 0.5:
        out.append(f"肩 {value:.1f}° 超限")
    if name == "elbow" and not geom.elbow_min - 0.5 <= value <= geom.elbow_max + 0.5:
        out.append(f"肘 {value:.1f}° 超限")
    return out
