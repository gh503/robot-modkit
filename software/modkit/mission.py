"""M4 任务状态机：导航 → 找 → 抓 → 搬到指定点 → 放。

设计原则：状态机不碰硬件，只依赖四个可注入的动作。
这样仿真、真机、回放都用同一套流程，错误恢复也能单独测。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import nav
from .vision import Detection


@dataclass
class MissionConfig:
    pick_xy: tuple[float, float] = (200.0, 0.0)
    drop_xy: tuple[float, float] = (-150.0, 0.0)
    max_seconds: float = 180.0
    search_turns: int = 4              # 找不到就转 90°，最多几次
    retries: int = 1                   # 导航/抓取各重试一次
    pos_tol: float = 15.0


@dataclass
class MissionResult:
    success: bool
    states: list[str]
    seconds: float
    attempts: int
    reason: str = ""

    def as_dict(self) -> dict:
        return {"success": self.success, "states": self.states,
                "seconds": round(self.seconds, 1), "attempts": self.attempts,
                "reason": self.reason}


class Mission:
    """drive_to(x, y, theta) / look() / pick(det) / drop() 都由调用方注入。"""

    def __init__(self, drive_to, look, pick, drop,
                 cfg: MissionConfig | None = None, now=time.monotonic):
        self.drive_to = drive_to
        self.look = look
        self.pick = pick
        self.drop = drop
        self.cfg = cfg or MissionConfig()
        self.now = now
        self.t0 = 0.0
        self.states: list[str] = []
        self.attempts = 0

    def _state(self, name: str) -> None:
        self.states.append(name)

    def _timeout(self) -> bool:
        return self.now() - self.t0 > self.cfg.max_seconds

    def _goto(self, xy: tuple[float, float], name: str) -> bool:
        for i in range(self.cfg.retries + 1):
            self.attempts += 1
            self._state(f"{name}:try{i + 1}")
            if self._timeout():
                return False
            if self.drive_to(xy[0], xy[1], 0.0):
                return True
        return False

    def run(self) -> MissionResult:
        self.t0 = self.now()
        self.states = []
        self.attempts = 0

        if not self._goto(self.cfg.pick_xy, "nav_pick"):
            return MissionResult(False, self.states, self.now() - self.t0,
                                 self.attempts, "导航到抓取点失败")

        det: Detection | None = None
        for i in range(self.cfg.search_turns):
            self._state(f"look:{i + 1}")
            if self._timeout():
                return MissionResult(False, self.states, self.now() - self.t0,
                                     self.attempts, "找目标超时")
            det = self.look()
            if det is not None:
                break
            # 原地转 90° 再找
            if not self.drive_to(self.cfg.pick_xy[0], self.cfg.pick_xy[1], 90.0):
                break
        if det is None:
            return MissionResult(False, self.states, self.now() - self.t0,
                                 self.attempts, "没找到目标")

        picked = False
        for i in range(self.cfg.retries + 1):
            self.attempts += 1
            self._state(f"pick:try{i + 1}")
            if self._timeout():
                return MissionResult(False, self.states, self.now() - self.t0,
                                     self.attempts, "抓取超时")
            if self.pick(det):
                picked = True
                break
        if not picked:
            return MissionResult(False, self.states, self.now() - self.t0,
                                 self.attempts, "抓取失败")

        if not self._goto(self.cfg.drop_xy, "nav_drop"):
            return MissionResult(False, self.states, self.now() - self.t0,
                                 self.attempts, "导航到放置点失败")

        self._state("drop")
        if not self.drop():
            return MissionResult(False, self.states, self.now() - self.t0,
                                 self.attempts, "放置失败")

        return MissionResult(True, self.states, self.now() - self.t0,
                             self.attempts, "完成")
