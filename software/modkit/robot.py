"""机器人高层 API：面向"动作"而不是"字节"。

接线（真机）见 docs/06-调试与测试.md；不接硬件时用 SimLink 跑同样流程：
    from modkit.bus import SimLink
    from modkit.robot import Robot
    bot = Robot(SimLink([1, 2, 3, 4]))
    bot.scan()
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from . import kinematics as kin
from . import protocol as p


@dataclass
class Feedback:
    position_deg: float
    speed: int
    load: int
    voltage: float
    temp_c: int
    status: int = 0

    @property
    def faults(self) -> list[str]:
        return p.status_bits(self.status)


class Robot:
    def __init__(self, link, arm: kin.ArmGeometry | None = None,
                 drive: kin.DriveGeometry | None = None, speed_unit: float = 1.0):
        self.link = link
        self.arm = arm or kin.ArmGeometry()
        self.drive = drive or kin.DriveGeometry()
        # 速度寄存器 1 LSB 对应多少 deg/s：默认 1.0 是占位，真机必须先按 docs/06 标定
        self.speed_unit = speed_unit
        self.odom = kin.OdomState()

    # ------------------------------------------------------------ 发现
    def scan(self, lo: int = 0, hi: int = 20) -> list[int]:
        found = []
        for sid in range(lo, hi + 1):
            try:
                self.link.transact(p.encode(sid, p.PING), sid, timeout=0.02)
                found.append(sid)
            except Exception:
                continue
        return found

    # ------------------------------------------------------------ 读
    def feedback(self, sid: int, timeout: float = 0.05) -> Feedback:
        f = self.link.transact(
            p.encode(sid, p.READ, bytes([p.REG_PRESENT_POS, 8])), sid, timeout
        )
        raw = f.params
        if len(raw) < 8:
            raise ValueError(f"反馈长度异常：{len(raw)}")
        return Feedback(
            position_deg=p.ticks_to_deg(p.u16(raw[0], raw[1])),
            speed=p.i16(raw[2], raw[3]),
            load=p.i16(raw[4], raw[5]),
            voltage=raw[6] / 10.0,
            temp_c=raw[7],
        )

    def status(self, sid: int) -> int:
        f = self.link.transact(
            p.encode(sid, p.READ, bytes([p.REG_STATUS, 1])), sid, 0.05
        )
        return f.params[0] if f.params else 0

    def position_ticks(self, sid: int) -> int:
        f = self.link.transact(
            p.encode(sid, p.READ, bytes([p.REG_PRESENT_POS, 2])), sid, 0.05
        )
        return p.u16(f.params[0], f.params[1])

    # ------------------------------------------------------------ 写
    def set_torque(self, sid: int, on: bool) -> None:
        self.link.transact(
            p.encode(sid, p.WRITE, bytes([p.REG_TORQUE_ENABLE, 1 if on else 0])), sid, 0.05
        )

    def goto(self, sid: int, deg: float, speed: int = 400, acc: int = 20) -> None:
        ticks = p.deg_to_ticks(deg)
        payload = bytes(
            [p.REG_GOAL_POS, ticks & 0xFF, ticks >> 8, 0, 0, speed & 0xFF, speed >> 8]
        )
        self.link.transact(p.encode(sid, p.WRITE, payload), sid, 0.05)
        self.link.transact(
            p.encode(sid, p.WRITE, bytes([p.REG_ACC, acc])), sid, 0.05
        )

    def sync_goto(self, mapping: dict[int, float], speed: int = 400) -> None:
        payloads = {}
        for sid, deg in mapping.items():
            t = p.deg_to_ticks(deg)
            payloads[sid] = bytes([t & 0xFF, t >> 8, 0, 0, speed & 0xFF, speed >> 8])
        frame = p.encode_sync_write(p.REG_GOAL_POS, payloads)
        self.link.transact(frame, p.BROADCAST_ID, 0.02)

    def home_all(self, ids: list[int] | None = None) -> None:
        ids = ids or list(getattr(self.link, "mem", {}).keys())
        for sid in ids:
            self.set_torque(sid, False)
        self.sync_goto({sid: 180.0 for sid in ids}, speed=200)

    # ------------------------------------------------------------ 臂
    def move_pose(self, x: float, y: float, z: float, speed: int = 300) -> tuple[float, float, float]:
        """末端到点：逆解 → 三个关节同步动。返回实际采用的角度。"""
        yaw, shoulder, elbow = kin.inverse(self.arm, kin.Pose(x, y, z))
        t1, t2, t3 = kin.joint_ticks(self.arm, yaw, shoulder, elbow)
        self.sync_goto(
            {
                1: p.ticks_to_deg(t1),
                2: p.ticks_to_deg(t2),
                3: p.ticks_to_deg(t3),
            },
            speed=speed,
        )
        return yaw, shoulder, elbow

    def gripper(self, opening: float) -> None:
        """夹爪：0.0 全闭，1.0 全开。"""
        opening = max(0.0, min(1.0, opening))
        deg = 180.0 - 60.0 * opening + 0.0
        self.goto(4, deg, speed=300, acc=10)

    # ------------------------------------------------------------ 底盘
    def set_mode(self, sid: int, mode: int) -> None:
        """0=位置伺服，1=恒速（轮子）。"""
        self.link.transact(
            p.encode(sid, p.WRITE, bytes([p.REG_MODE, mode & 0xFF])), sid, 0.05
        )

    def set_speed_raw(self, sid: int, lsb: int) -> None:
        """直接写速度寄存器（标定用），单位是 LSB，BIT15 方向。"""
        val = min(abs(int(lsb)), 0x7FFF) | (0x8000 if lsb < 0 else 0)
        self.link.transact(
            p.encode(sid, p.WRITE, bytes([p.REG_GOAL_SPEED, val & 0xFF, val >> 8])),
            sid, 0.05,
        )

    def set_wheel_speed(self, sid: int, mm_s: float,
                        geom: kin.DriveGeometry | None = None,
                        speed_unit: float | None = None) -> None:
        """轮子恒速模式：写 0x2E，BIT15 为方向位。"""
        geom = geom or self.drive
        unit = self.speed_unit if speed_unit is None else speed_unit
        deg_s = math.degrees(mm_s / geom.wheel_r)
        mag = min(int(round(abs(deg_s) / max(unit, 1e-6))), 0x7FFF)
        val = mag | (0x8000 if mm_s < 0 else 0)
        payload = bytes([p.REG_GOAL_SPEED, val & 0xFF, val >> 8])
        self.link.transact(p.encode(sid, p.WRITE, payload), sid, 0.05)

    def drive_speed(self, v_mm_s: float, w_deg_s: float,
              left_id: int = 5, right_id: int = 6) -> tuple[float, float]:
        """车体速度 → 左右轮；返回实际下发的两个轮速。"""
        left, right = kin.wheel_speeds(v_mm_s, w_deg_s, self.drive)
        self.set_wheel_speed(left_id, left)
        self.set_wheel_speed(right_id, right)
        return left, right

    def stop_wheels(self, left_id: int = 5, right_id: int = 6) -> None:
        self.set_wheel_speed(left_id, 0.0)
        self.set_wheel_speed(right_id, 0.0)

    def update_odom(self, left_id: int = 5, right_id: int = 6) -> kin.OdomState:
        return kin.update_odom(
            self.drive, self.odom,
            self.position_ticks(left_id), self.position_ticks(right_id),
        )