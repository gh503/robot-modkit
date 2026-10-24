"""整机几何模型：给可视化和仿真用的"可动模型"。

原则：
1. 尺寸只从 cad/params.py 读，不在这里写第二份 —— 图纸改了，仿真自动跟着变。
2. 正解复用 software/modkit/kinematics.py，动画和上位机用的是同一套数学。
3. 画出来的是运动学骨架（连杆 + 关节 + 轮子 + 夹爪），不是 STL 网格：
   它保证"角度 → 位姿"绝对正确，代价是外形简化。要看真实外形用 cad/out 的 STL。
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
# 注意用 append：sim/ 目录必须保持在 sys.path 最前，
# 否则 cad/render.py 会盖住 sim 里的模块（踩过一次）。
sys.path.append(str(_ROOT / "cad"))
sys.path.append(str(_ROOT / "software"))

import params as P  # noqa: E402  cad/params.py：唯一尺寸源
from modkit import kinematics as kin  # noqa: E402  已安装的 modkit 包

# 整机在底盘坐标系下的关键点
ARM_X = P.ARM_ORIGIN_X
ARM_Y = 0.0
CHASSIS_TOP = 0.0
GROUND = P.SERVO_Z - P.WHEEL_R   # 轮子触地面（轮轴在 SERVO_Z，半径 WHEEL_R）


@dataclass
class RobotState:
    """一帧的完整状态。所有可视化/仿真都只吃这个结构。"""

    yaw: float = 0.0
    shoulder: float = 30.0
    elbow: float = -60.0
    jaw: float = 1.0          # 1 = 全开，0 = 全闭
    x: float = 0.0            # 底盘位姿（里程计）
    y: float = 0.0
    heading: float = 0.0


def arm_geometry() -> kin.ArmGeometry:
    return kin.ArmGeometry(base_h=90.0, l1=120.0, l2=110.0)


def joint_points(st: RobotState) -> dict[str, tuple[float, float, float]]:
    """返回 base/shoulder/elbow/wrist/tip 五个点（底盘坐标系，mm）。"""
    g = arm_geometry()
    sh = math.radians(st.shoulder)
    el = math.radians(st.shoulder + st.elbow)
    yaw = math.radians(st.yaw)

    shoulder = (ARM_X, ARM_Y, CHASSIS_TOP + g.base_h)
    ex = g.l1 * math.cos(sh)
    ez = g.l1 * math.sin(sh)
    wx = ex + g.l2 * math.cos(el)
    wz = ez + g.l2 * math.sin(el)

    def rot(x: float, z: float) -> tuple[float, float, float]:
        return (shoulder[0] + x * math.cos(yaw), shoulder[1] + x * math.sin(yaw), shoulder[2] + z)

    return {
        "base": shoulder,
        "shoulder": shoulder,
        "elbow": rot(ex, ez),
        "wrist": rot(wx, wz),
        "tip": rot(wx + 40.0, wz - 10.0),   # 指尖大致位置（爪长 60 + 掌 10）
    }


def gap_mm(jaw: float) -> float:
    """夹爪内距：jaw=1 全开，jaw=0 全闭（与 CAD 的 40→27mm 一致）。"""
    return P.JAW_GAP_OPEN * jaw + kin_jaw_closed() * (1.0 - jaw)


def kin_jaw_closed() -> float:
    return P.JAW_GAP_OPEN / 2 * (1 + math.cos(math.radians(P.JAW_SWING)))


@dataclass
class Block:
    """被抓的方块（40mm 立方体）。"""

    x: float
    y: float
    z: float = 20.0
    size: float = 40.0
    held: bool = False


def make_robot_state_from_pose(target: kin.Pose) -> RobotState:
    """给定末端目标（底盘坐标系），逆解出关节角。"""
    yaw, sh, el = kin.inverse(arm_geometry(), target, elbow_up=False)
    return RobotState(yaw=yaw, shoulder=sh, elbow=el)


@dataclass
class Scene:
    """一个仿真场景：机器人 + 桌面 + 方块 + 轨迹。"""

    state: RobotState = field(default_factory=RobotState)
    blocks: list[Block] = field(default_factory=list)
    trail: list[tuple[float, float]] = field(default_factory=list)

    def add_block(self, x: float, y: float, z: float = 20.0) -> Block:
        b = Block(x, y, z)
        self.blocks.append(b)
        return b
