"""M4 任务状态机：导航 → 找 → 抓 → 搬到指定点 → 放。

设计原则：状态机不碰硬件，只依赖四个可注入的动作。
这样仿真、真机、回放都用同一套流程，错误恢复也能单独测。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from . import nav

if TYPE_CHECKING:
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


def run_tasks(drive_to, look, pick, drop, tasks: list[tuple[tuple[float, float], tuple[float, float]]],
              cfg: MissionConfig | None = None, now=time.monotonic,
              total_seconds: float = 600.0) -> dict:
    """按顺序跑多个 pick→drop；任一任务失败就停，保留每一步结果。"""
    cfg = cfg or MissionConfig()
    t0 = now()
    results = []
    for i, (pick_xy, drop_xy) in enumerate(tasks, 1):
        remain = total_seconds - (now() - t0)
        if remain <= 0:
            results.append({"task": i, "success": False, "reason": "总预算超时"})
            break
        c = replace(cfg, pick_xy=pick_xy, drop_xy=drop_xy,
                    max_seconds=min(cfg.max_seconds, remain))
        r = Mission(drive_to, look, pick, drop, cfg=c, now=now).run()
        results.append({"task": i, "pick": list(pick_xy), "drop": list(drop_xy),
                        **r.as_dict()})
        if not r.success:
            break
    return {"success": bool(results) and all(r.get("success") for r in results),
            "tasks": len(results), "seconds": round(now() - t0, 1),
            "results": results}


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
