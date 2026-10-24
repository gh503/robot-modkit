"""回差（背隙）：减速齿轮换了方向，要先"空走"一点才动。

为什么值得单独处理：
  · 总线舵机的回差 0.5–1°，在 230mm 力臂上就是 2–4mm 末端误差；
  · 开环蒙特卡洛算出 p95 6.24mm（docs/32），回差是主因之一；
  · 消隙垫片能减小，但**换向补偿**不花钱，软件就能补一半。

两种用法：
  1. 测量：`modkit backlash --action measure --id 1`
  2. 补偿：所有 goto 前按方向加半个回差（本模块的 Compensator）
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import asdict, dataclass, field

from . import protocol as p

# 统一按"关节角"记，内部用 tick
TICK_PER_DEG = p.TICKS_PER_REV / 360.0


class BacklashError(RuntimeError):
    pass


@dataclass
class JointPlay:
    sid: int
    name: str = ""
    play_deg: float = 0.0

    @property
    def play_ticks(self) -> float:
        return self.play_deg * TICK_PER_DEG

    @property
    def ok(self) -> bool:
        return self.play_deg <= 1.0        # 超过 1° 要先查机械


@dataclass
class Compensator:
    """按"上一次运动方向"补偿半个回差。"""

    plays: dict[int, float] = field(default_factory=dict)   # sid -> play_deg
    _last: dict[int, int] = field(default_factory=dict)     # sid -> +1/-1

    def set_play(self, sid: int, play_deg: float) -> None:
        self.plays[sid] = play_deg

    def command(self, sid: int, target_deg: float) -> float:
        """返回实际要下发的角度；首次运动不补偿。"""
        play = self.plays.get(sid, 0.0)
        last = self._last.get(sid)
        if last is None or play <= 0:
            return target_deg
        delta = target_deg - last
        if abs(delta) < 1e-9:
            return target_deg
        direction = 1 if delta > 0 else -1
        return target_deg + direction * play / 2.0

    def note(self, sid: int, target_deg: float) -> None:
        self._last[sid] = target_deg

    def save(self, path: str | pathlib.Path) -> pathlib.Path:
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({str(k): v for k, v in self.plays.items()},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def load(self, path: str | pathlib.Path) -> None:
        raw = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        self.plays = {int(k): float(v) for k, v in raw.items()}


def measure(robot, sid: int, center: float = 180.0, span: float = 10.0,
            settle: float = 0.35, name: str = "") -> JointPlay:
    """从 +侧 和 -侧 各逼近一次 center，两次读数之差就是回差。"""
    if span <= 0:
        raise BacklashError("span 必须为正")

    def pos() -> float:
        return p.ticks_to_deg(robot.position_ticks(sid))

    try:
        robot.set_torque(sid, True)
        robot.goto(sid, center + span, speed=150, acc=10)
        _sleep(settle)
        robot.goto(sid, center, speed=80, acc=10)
        _sleep(settle)
        from_plus = pos()

        robot.goto(sid, center - span, speed=150, acc=10)
        _sleep(settle)
        robot.goto(sid, center, speed=80, acc=10)
        _sleep(settle)
        from_minus = pos()
    finally:
        try:
            robot.set_torque(sid, False)
        except Exception:
            pass

    play = abs(from_plus - from_minus)
    return JointPlay(sid=sid, name=name, play_deg=round(play, 3))


def _sleep(seconds: float) -> None:
    if seconds > 0:
        import time
        time.sleep(seconds)
