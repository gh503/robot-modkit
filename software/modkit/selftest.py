"""新机自检：一台刚装好的机器，能不能通电、能不能动、动不动得准。

为什么不是"人工点一遍"：
  · 第一次上电最容易出事（接线错、ID 重、舵机卡死）；
  · 自检要能中断：任何一步失败立刻卸力，不继续动；
  · 结果要能留档（JSON），返修时对比"上次是不是也这样"。

流程（每个关节）：
  1. 读一次反馈（通信 + 电压 + 温度 + 故障位）
  2. 使能，正向转 amp 度，读回，比目标
  3. 反向转回原位，再读
  4. 卸力

用法：
    modkit --sim selftest --expect 1,2,3,4,5,6
    modkit --port /dev/ttyUSB0 selftest --expect 1,2,3,4,5,6 --amp 5
"""

from __future__ import annotations

import json
import pathlib
import time
from dataclasses import asdict, dataclass, field

from . import protocol as p
from .robot import Robot


class SelfTestError(RuntimeError):
    pass


@dataclass
class Step:
    sid: int
    name: str
    ok: bool
    detail: str
    before: float = 0.0
    after: float = 0.0
    target: float = 0.0
    temp_c: int = 0
    voltage: float = 0.0


@dataclass
class Report:
    steps: list[Step] = field(default_factory=list)
    stopped: str = ""

    @property
    def ok(self) -> bool:
        return not self.stopped and all(s.ok for s in self.steps)

    def save(self, path: str | pathlib.Path) -> pathlib.Path:
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"ok": self.ok, "stopped": self.stopped,
                "steps": [asdict(s) for s in self.steps]}
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path


def _deg(robot: Robot, sid: int) -> float:
    return p.ticks_to_deg(robot.position_ticks(sid))


def _status(robot: Robot, sid: int) -> int:
    """故障位不在 8 字节反馈里，要单独读 0x41。"""
    f = robot.link.transact(p.encode(sid, p.READ, bytes([p.REG_STATUS, 1])), sid)
    return f.params[0] if f.params else 0


def selftest(robot: Robot, expect: list[int], amp: float = 5.0,
             tol: float = 1.5, settle: float = 0.25,
             names: dict[int, str] | None = None) -> Report:
    names = names or {1: "yaw", 2: "shoulder", 3: "elbow", 4: "gripper",
                      5: "wheel_l", 6: "wheel_r"}
    rep = Report()

    found = robot.scan(lo=0, hi=20)
    for sid in expect:
        if sid not in found:
            rep.steps.append(Step(sid, names.get(sid, ""), False, "扫描不到这个 ID"))
    if any(not s.ok for s in rep.steps):
        rep.stopped = "有舵机不在线，先查线再上电"
        return rep

    for sid in expect:
        name = names.get(sid, "")
        fb = robot.feedback(sid)
        status = _status(robot, sid)
        step = Step(sid=sid, name=name, ok=True, detail="",
                    temp_c=fb.temp_c, voltage=fb.voltage)
        if status:
            step.ok = False
            step.detail = f"故障位：{','.join(p.status_bits(status)) or hex(status)}"
            rep.steps.append(step)
            rep.stopped = f"ID{sid} 上电就有故障，停止"
            break
        if fb.temp_c >= 55:
            step.ok = False
            step.detail = f"温度 {fb.temp_c}℃ 偏高"
            rep.steps.append(step)
            rep.stopped = "温度异常，停止"
            break

        before = _deg(robot, sid)
        target = min(200.0, before + amp)
        step.before = round(before, 2)
        step.target = round(target, 2)

        try:
            robot.set_torque(sid, True)
            robot.goto(sid, target, speed=150, acc=10)
            time.sleep(settle)
            after = _deg(robot, sid)
        except Exception as e:
            step.ok = False
            step.detail = f"运动失败：{e}"
            rep.steps.append(step)
            rep.stopped = f"ID{sid} 运动异常，已停止"
            break
        finally:
            try:
                robot.set_torque(sid, False)
            except Exception:
                pass

        step.after = round(after, 2)
        err = abs(after - target)
        if err > tol:
            step.ok = False
            step.detail = f"到位误差 {err:.2f}° > {tol}°"
        else:
            step.detail = f"到位误差 {err:.2f}°"
        rep.steps.append(step)

        # 回原位，避免自检后姿态漂移
        try:
            robot.set_torque(sid, True)
            robot.goto(sid, before, speed=150, acc=10)
            time.sleep(settle * 0.5)
        finally:
            try:
                robot.set_torque(sid, False)
            except Exception:
                pass

    return rep


PRETTY = {1: "yaw", 2: "shoulder", 3: "elbow", 4: "gripper", 5: "wheel_l", 6: "wheel_r"}
