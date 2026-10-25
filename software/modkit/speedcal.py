"""速度寄存器标定：0x2E 写 LSB，实测轮子转了多少 deg/s。

为什么必须实测：不同批次/电压/负载下，1 LSB 对应的转速不一样；
`DriveConfig::speed_unit` 默认 1.0 只是占位，docs/06 G7 要求在车上第一件事标定。
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from . import kinematics as kin


@dataclass
class SpeedCalResult:
    sid: int
    lsb: int
    seconds: float
    deg_s: float
    unit: float          # 实测 deg/s ÷ LSB
    ticks: int
    ok: bool
    note: str = ""

    def as_dict(self) -> dict:
        return {"sid": self.sid, "lsb": self.lsb, "seconds": round(self.seconds, 3),
                "deg_s": round(self.deg_s, 2), "unit": round(self.unit, 4),
                "ticks": self.ticks, "ok": self.ok, "note": self.note}


def measure(robot, sid: int = 5, lsb: int = 500, seconds: float = 1.0,
            hz: float = 50.0, clock=time.monotonic,
            sleep=time.sleep) -> SpeedCalResult:
    """恒速模式跑一段时间，用位置计数增量算平均角速度。"""
    if lsb == 0:
        raise ValueError("lsb 不能为 0")
    robot.set_mode(sid, 1)
    robot.set_torque(sid, True)
    robot.set_speed_raw(sid, lsb)

    t0 = clock()
    p0 = robot.position_ticks(sid)
    last = p0
    ticks = 0
    n = max(1, int(round(seconds * hz)))
    try:
        for i in range(n):
            sleep(1.0 / hz)
            now = robot.position_ticks(sid)
            ticks += kin.tick_delta(now, last)
            last = now
    finally:
        robot.set_speed_raw(sid, 0)
    dt = clock() - t0

    deg = ticks * 360.0 / 4096.0
    deg_s = deg / dt if dt > 0 else 0.0
    unit = deg_s / lsb
    ok = dt > 0.05 and abs(deg_s) >= 5.0
    note = ""
    if not ok:
        note = "几乎没转：检查模式/扭矩/电源/轮子是否离地"
    elif (deg_s > 0) != (lsb > 0):
        note = "转向与命令相反：交换两根线或把方向位取反"
        ok = False
    return SpeedCalResult(sid, lsb, dt, deg_s, unit, ticks, ok, note)
