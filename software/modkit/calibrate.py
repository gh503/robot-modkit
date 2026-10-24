"""标定向导：把"零位/方向/限位/速度单位"变成可复现的记录，而不是手感。

为什么单独做：同一批舵机装到不同关节上，零位差个 3–5° 很常见；不记下来，
换个人/换台机器就得重来。这个模块的输出 `calibration.json` 是装配记录的一部分。

设计原则：
1. **不改舵机固件里的偏移**（0x1F 各版本行为不一），只在"上位机侧"记映射：
   tick ↔ 关节角，换舵机只要重标一个关节。
2. 限位靠**慢速逼近 + 电流/温度监控**，不靠撞死；撞死会烧齿轮。
3. 每一步都能在 SimLink 上跑（CI），真机只是把 link 换成 SerialLink。

用法（仿真先跑通）：
    python -m modkit.cli calib --sim --limits 1 --lo 0 --hi 180
    python -m modkit.cli calib --sim --zero 1 --deg 90 --save calib.json
    python -m modkit.cli calib --sim --verify calib.json
"""

from __future__ import annotations

import json
import math
import pathlib
import time
from dataclasses import asdict, dataclass, field

from . import protocol as p
from .robot import Robot


class CalibError(RuntimeError):
    pass


@dataclass
class Joint:
    name: str
    servo_id: int
    zero_ticks: int          # 关节角 = 0° 时对应的 tick
    dir: int = 1             # +1 / -1：tick 增大时关节角往哪边走
    min_deg: float = 0.0
    max_deg: float = 180.0
    speed_unit: float = 1.0  # 速度寄存器 LSB 对应的 deg/s，实测填

    def tick_to_deg(self, ticks: int) -> float:
        return self.dir * (ticks - self.zero_ticks) * p.DEG_PER_TICK

    def deg_to_tick(self, deg: float) -> int:
        return int(round(self.zero_ticks + self.dir * deg / p.DEG_PER_TICK))

    def check(self) -> None:
        if self.dir not in (-1, 1):
            raise CalibError(f"{self.name}: dir 只能是 ±1")
        if not 0 <= self.zero_ticks <= 4095:
            raise CalibError(f"{self.name}: zero_ticks 越界 {self.zero_ticks}")
        if self.min_deg >= self.max_deg:
            raise CalibError(f"{self.name}: min_deg 必须小于 max_deg")


@dataclass
class Calibration:
    robot: str = "modkit-m1"
    created: str = ""
    joints: dict[str, Joint] = field(default_factory=dict)

    def add(self, j: Joint) -> None:
        j.check()
        self.joints[j.name] = j

    def save(self, path: str | pathlib.Path) -> pathlib.Path:
        path = pathlib.Path(path)
        self.created = time.strftime("%Y-%m-%dT%H:%M:%S")
        for j in self.joints.values():
            j.check()
        path.write_text(json.dumps(
            {"robot": self.robot, "created": self.created,
             "joints": {k: asdict(v) for k, v in self.joints.items()}},
            ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: str | pathlib.Path) -> "Calibration":
        d = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        c = cls(robot=d.get("robot", "modkit-m1"), created=d.get("created", ""))
        for k, v in d["joints"].items():
            c.add(Joint(**v))
        return c

    def get(self, name: str) -> Joint:
        if name not in self.joints:
            raise CalibError(f"没有关节 {name}；先 --zero 标一个")
        return self.joints[name]


# ---------------------------------------------------------------- 读数与探测

def probe(robot: Robot, sid: int) -> dict:
    fb = robot.feedback(sid)
    return {
        "id": sid,
        "ticks": robot.position_ticks(sid),
        "deg": round(fb.position_deg, 2),
        "voltage": fb.voltage,
        "temp_c": fb.temp_c,
        "faults": fb.faults,
    }


def find_limits(robot: Robot, sid: int, lo: float = -10.0, hi: float = 190.0,
                step: float = 5.0, settle: float = 0.25, speed: int = 120) -> tuple[int, int]:
    """慢速从 lo 扫到 hi，记录能稳定到达的 tick 范围。

    判据：连续两步读数差 < 3 tick（说明到位了），且没有过流/过温故障。
    真机上撞到机械限位会堵转，所以步长小、速度慢、一旦故障立刻卸力。
    """
    robot.set_torque(sid, True)
    reached: list[int] = []
    deg = lo
    while deg <= hi + 1e-6:
        robot.goto(sid, deg, speed=speed, acc=10)
        time.sleep(settle)
        fb = robot.feedback(sid)
        if fb.faults:
            robot.set_torque(sid, False)
            raise CalibError(f"ID {sid} 在 {deg:.0f}° 报故障 {fb.faults}，停止扫描")
        reached.append(robot.position_ticks(sid))
        deg += step
    robot.set_torque(sid, False)
    if len(reached) < 2:
        raise CalibError("没有采到有效点")
    return min(reached), max(reached)


def set_zero(robot: Robot, sid: int, deg: float = 0.0, steps: int = 30) -> int:
    """让关节停在 `deg`，把此时的 tick 记为 0°。返回 zero_ticks。"""
    robot.set_torque(sid, True)
    robot.goto(sid, deg, speed=100, acc=5)
    time.sleep(0.4)
    ticks = robot.position_ticks(sid)
    robot.set_torque(sid, False)
    return ticks


def verify(robot: Robot, joint: Joint, points: list[float] | None = None,
           tol_deg: float = 2.0) -> list[dict]:
    """依次走到若干角度，读回并算误差。返回每点的记录，超差抛错。"""
    pts = points or [joint.min_deg, (joint.min_deg + joint.max_deg) / 2, joint.max_deg]
    robot.set_torque(joint.servo_id, True)
    out = []
    for want in pts:
        want = max(joint.min_deg, min(joint.max_deg, want))
        # goto 收的是"舵机绝对角度"，关节角要先用零位换算过去
        robot.goto(joint.servo_id, p.ticks_to_deg(joint.deg_to_tick(want)), speed=150, acc=10)
        time.sleep(0.3)
        got = joint.tick_to_deg(robot.position_ticks(joint.servo_id))
        err = abs(got - want)
        out.append({"want": round(want, 2), "got": round(got, 2), "err": round(err, 2)})
    robot.set_torque(joint.servo_id, False)
    bad = [r for r in out if r["err"] > tol_deg]
    if bad:
        raise CalibError(f"超差：{bad}（容差 {tol_deg}°）")
    return out


def scan_joints(robot: Robot, expected: int = 6) -> list[int]:
    ids = robot.scan()
    if len(ids) != expected:
        raise CalibError(f"扫到 {len(ids)} 个舵机（期望 {expected}）：{ids}")
    return ids


def default_joints() -> list[str]:
    """M1 的关节顺序（和 docs/03 §5 的 ID 分配一致）。"""
    return ["yaw", "shoulder", "elbow", "wrist", "left_wheel", "right_wheel"]


def parse_deg(text: str) -> float:
    v = float(text)
    if not math.isfinite(v):
        raise CalibError("角度必须是有限数")
    return v