"""抓取动作序列（不含绘图依赖）：GIF 和网页播放器共用同一份轨迹。"""

from __future__ import annotations

import model as M
from modkit import kinematics as kin


def ik_or_fail(x: float, y: float, z: float, jaw: float = 1.0) -> M.RobotState:
    yaw, sh, el = kin.inverse(M.arm_geometry(), kin.Pose(x, y, z), elbow_up=False)
    return M.RobotState(yaw=yaw, shoulder=sh, elbow=el, jaw=jaw)


def keyframes() -> list[dict]:
    """9 个关键姿态；网页按时间插值，GIF 按帧插值。"""
    seq = [
        (M.RobotState(yaw=0, shoulder=35, elbow=-55, jaw=1.0), "待机"),
        (ik_or_fail(200, 0, 120, 1.0), "移到方块上方"),
        (ik_or_fail(200, 0, 62, 1.0), "下降抓取"),
        (ik_or_fail(200, 0, 62, 0.0), "夹爪闭合"),
        (ik_or_fail(200, 0, 170, 0.0), "抬起"),
        (ik_or_fail(150, 110, 150, 0.0), "转到托盘上方"),
        (ik_or_fail(150, 110, 70, 0.0), "下降到托盘"),
        (ik_or_fail(150, 110, 70, 1.0), "松开"),
        (M.RobotState(yaw=0, shoulder=35, elbow=-55, jaw=1.0), "回到待机"),
    ]
    return [
        {"yaw": s.yaw, "shoulder": s.shoulder, "elbow": s.elbow, "jaw": s.jaw, "label": lbl}
        for s, lbl in seq
    ]
