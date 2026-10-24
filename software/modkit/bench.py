"""台架测试：重复精度与连续运行（烧机）。

两个测试都可以在仿真链路跑（验证流程与记录），真机只是换个 link。

    python -m modkit.cli bench --sim --action repeat --n 10
    python -m modkit.cli bench --sim --action burnin --minutes 1

真机上建议：
    · 重复精度用千分表/视觉标定板量末端，编码器读数只能当"关节重复性"；
    · 烧机时每 10 秒记一次温度，超过 55℃ 自动卸力并停。
"""

from __future__ import annotations

import csv
import pathlib
import time
from dataclasses import dataclass, field

from . import kinematics as kin
from .robot import Robot


class BenchError(RuntimeError):
    pass


@dataclass
class Sample:
    t: float
    cycle: int
    temp_c: float
    voltage: float
    x: float
    y: float
    z: float
    note: str = ""


@dataclass
class BenchLog:
    path: pathlib.Path
    rows: list[Sample] = field(default_factory=list)

    def add(self, s: Sample) -> None:
        self.rows.append(s)

    def flush(self) -> pathlib.Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["t", "cycle", "temp_c", "voltage", "x", "y", "z", "note"])
            for s in self.rows:
                w.writerow([f"{s.t:.3f}", s.cycle, s.temp_c, s.voltage,
                            f"{s.x:.1f}", f"{s.y:.1f}", f"{s.z:.1f}", s.note])
        return self.path


def fk_point(robot: Robot) -> tuple[float, float, float]:
    """用关节反馈算末端位置（编码器口径，不含机械回差）。"""
    yaw, sh, el = kin.ticks_to_joints(
        robot.position_ticks(1), robot.position_ticks(2), robot.position_ticks(3))
    p = kin.forward(robot.arm, yaw, sh, el)
    return p.x, p.y, p.z


def repeatability(robot: Robot, x: float, y: float, z: float, n: int = 10,
                  settle: float = 0.35) -> dict:
    """同一点往返 n 次，统计末端读数离散。"""
    pts = []
    for _ in range(n):
        robot.move_pose(x, y, z, speed=200)
        time.sleep(settle)
        pts.append(fk_point(robot))
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    zs = [p[2] for p in pts]
    span = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    mean = (sum(xs) / n, sum(ys) / n, sum(zs) / n)
    return {
        "n": n,
        "target": (x, y, z),
        "mean": tuple(round(v, 2) for v in mean),
        "span_mm": round(span, 3),
        "ok": span <= 2.0,
        "points": [(round(a, 2), round(b, 2), round(c, 2)) for a, b, c in pts],
    }


def burn_in(robot: Robot, minutes: float = 1.0, cycle_s: float = 2.0,
            limit_c: float = 55.0, log: BenchLog | None = None,
            poses: list[tuple[float, float, float]] | None = None) -> dict:
    """循环抓放位姿，记录温度/电压；超温或故障立即停并卸力。"""
    poses = poses or [(180, 0, 120), (200, 0, 60), (200, 0, 120), (180, 0, 160)]
    t0 = time.monotonic()
    cycles = 0
    max_t = 0.0
    stopped = ""
    while time.monotonic() - t0 < minutes * 60:
        p = poses[cycles % len(poses)]
        try:
            robot.move_pose(*p, speed=250)
        except Exception as e:                      # 真机上可能是通讯超时
            stopped = f"运动异常：{e}"
            break
        time.sleep(min(cycle_s, 0.5))
        fb = robot.feedback(1)
        max_t = max(max_t, fb.temp_c)
        x, y, z = fk_point(robot)
        if log is not None:
            log.add(Sample(time.monotonic() - t0, cycles, fb.temp_c, fb.voltage, x, y, z))
        if fb.temp_c >= limit_c:
            stopped = f"温度 {fb.temp_c}℃ ≥ {limit_c}℃"
            break
        if fb.faults:
            stopped = f"故障 {fb.faults}"
            break
        cycles += 1

    for sid in (1, 2, 3):
        try:
            robot.set_torque(sid, False)
        except Exception:
            pass
    if log is not None:
        log.flush()
    return {
        "cycles": cycles,
        "duration_s": round(time.monotonic() - t0, 1),
        "max_temp_c": max_t,
        "stopped": stopped,
        "ok": not stopped,
    }