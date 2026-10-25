"""硬件 bring-up（调试）记录：把 docs/42 §3 的 11 步变成可核验的证据。

设计原则：
  · 工具不代替实测：`pass` 必须带**存在的证据文件**，否则拒绝；
  · 仿真只能标 `simulated`，永远不计入物理闸门；
  · 记录只写 JSON + 文件 sha256，不碰硬件、不自动发运动指令。

用法：
    python -m modkit.cli bringup --action list
    python -m modkit.cli bringup --action init --serial M1-2026-0001 --operator 老王
    python -m modkit.cli bringup --action record --step 2 --result pass \
        --evidence logs/scan.txt
    python -m modkit.cli bringup --action status
    python -m modkit.cli bringup --action simulate   # 仅演示，不计入物理
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import time
from dataclasses import asdict, dataclass, field

DEFAULT_FILE = "records/bringup.json"

STATUSES = ("pending", "pass", "fail", "simulated")


@dataclass(frozen=True)
class Step:
    n: int
    key: str
    title: str
    detail: str
    command: str
    gate: str
    motion: bool = False


# 与 docs/42 §3、docs/28 G0–G8 对齐；顺序就是执行顺序，不许跳。
STEPS: tuple[Step, ...] = (
    Step(1, "preflight", "上电前检查",
         "万用表量 12V 极性/短路；急停串电源正极；保险 3A；电池压差 <0.05V",
         "见 docs/42 §3.1，不需要命令", "G4"),
    Step(2, "scan", "扫描六轴",
         "6 个 ID 全在；电压/温度/故障位正常",
         "modkit --port /dev/ttyUSB0 scan", "G5"),
    Step(3, "direction", "方向与零位",
         "逐个 home；方向反了立刻断电；标定零位并存盘",
         "modkit --port ... home; modkit calib --action zero ...", "G6", True),
    Step(4, "speedcal", "速度寄存器标定",
         "0x2E 写 1000，实测轮速，回填 speed_unit；直行 1m 偏差 <20mm",
         "modkit --port ... speedcal --sid 5 --lsb 1000 --save speed.json", "G6", True),
    Step(5, "estop", "急停时序",
         "全速前进时拍急停，录像数帧，<0.3s 停；复测 3 次",
         "人工 + 摄像，记录秒表/视频", "G4", True),
    Step(6, "straight", "直线 2m",
         "地面贴胶带，3 次，偏差 <5cm；记录起点/终点",
         "modkit --port ... nav --closed-loop --path line --size 2000", "G7", True),
    Step(7, "turn", "原地转 90°",
         "3 次，误差 <3°；正反各一次",
         "modkit --port ... nav --closed-loop --path custom --wp 0,0,90", "G7", True),
    Step(8, "grasp", "夹爪抓放",
         "100g 方块 10 次，成功 ≥8；记录失败模式；夹爪闭合间隙 <1mm",
         "modkit --port ... bench --action repeat --n 10", "G7", True),
    Step(9, "vision", "视觉标定",
         "棋盘格内参 + 四点/手眼；固定光照；10 次识别 ≥9",
         "modkit camcalib ... / modkit --port ... pick --sim", "G6", True),
    Step(10, "mission", "T1 任务闭环",
         "真机 mission 5 次 ≥4，单次 ≤3min；急停监控在场",
         "modkit mission --port ... (需先过 1–9)", "M4", True),
    Step(11, "burnin", "30min 烤机",
         "连续抓放/行走 30min；壳温 <55℃；掉压/丢步回放定位",
         "modkit --port ... bench --action burnin --minutes 30", "G7", True),
)

MILESTONES: dict[str, tuple[int, ...]] = {
    "M1": (1, 2, 3, 8),
    "M2": (4, 5, 6, 7),
    "M3": (8, 9),
    "M4": (10,),
    "M5": (11,),
}


class BringupError(RuntimeError):
    pass


def sha256_file(path: str | pathlib.Path) -> str:
    h = hashlib.sha256()
    h.update(pathlib.Path(path).read_bytes())
    return h.hexdigest()


@dataclass
class StepResult:
    status: str = "pending"
    note: str = ""
    evidence: str = ""
    sha256: str = ""
    at: str = ""


@dataclass
class Commission:
    serial: str
    operator: str
    date: str = field(default_factory=lambda: time.strftime("%Y-%m-%d"))
    steps: dict[str, StepResult] = field(default_factory=dict)
    notes: str = ""

    def __post_init__(self):
        for s in STEPS:
            self.steps.setdefault(str(s.n), StepResult())

    def record(self, n: int, status: str, evidence: str = "", note: str = "") -> StepResult:
        if status not in STATUSES or status == "pending":
            raise BringupError("结果只能是 pass/fail/simulated")
        step = _step(n)
        if status == "pass":
            if not evidence:
                raise BringupError(f"第 {n} 步 pass 必须带 --evidence（扫描日志/视频/记录）")
            path = pathlib.Path(evidence)
            if not path.is_file() or path.stat().st_size == 0:
                raise BringupError(f"证据文件不存在或为空：{evidence}")
        r = StepResult(status=status, note=note,
                       evidence=evidence,
                       sha256=sha256_file(evidence) if evidence and pathlib.Path(evidence).is_file() else "",
                       at=time.strftime("%Y-%m-%dT%H:%M:%S"))
        self.steps[str(step.n)] = r
        return r

    def pass_count(self) -> int:
        return sum(1 for r in self.steps.values() if r.status == "pass")

    def simulated_count(self) -> int:
        return sum(1 for r in self.steps.values() if r.status == "simulated")

    def milestone(self, key: str) -> str:
        statuses = [self.steps[str(n)].status for n in MILESTONES[key]]
        if all(s == "pass" for s in statuses):
            return "pass"
        if all(s == "simulated" for s in statuses):
            return "simulated"
        if any(s == "fail" for s in statuses):
            return "fail"
        return "pending"

    def physical_passed(self) -> int:
        return sum(1 for k in MILESTONES if self.milestone(k) == "pass")

    def next_step(self) -> Step | None:
        if self.simulated_count() == len(STEPS):
            return None
        for s in STEPS:
            if self.steps[str(s.n)].status != "pass":
                return s
        return None

    def validate(self) -> list[str]:
        errs = []
        if not self.serial or not self.operator:
            errs.append("缺序列号或操作人")
        if self.simulated_count():
            errs.append(f"有 {self.simulated_count()} 步是 simulated，不能当物理证据")
        for s in STEPS:
            r = self.steps[str(s.n)]
            if r.status == "pass":
                if not r.evidence or not pathlib.Path(r.evidence).is_file():
                    errs.append(f"第 {s.n} 步 pass 但证据文件不存在：{r.evidence}")
                elif r.sha256 and sha256_file(r.evidence) != r.sha256:
                    errs.append(f"第 {s.n} 步证据已被修改（sha256 不符）")
        return errs

    def save(self, path: str | pathlib.Path = DEFAULT_FILE, overwrite: bool = True) -> pathlib.Path:
        p = pathlib.Path(path)
        if p.exists() and not overwrite:
            raise BringupError(f"记录已存在：{p}")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")
        return p

    @classmethod
    def load(cls, path: str | pathlib.Path = DEFAULT_FILE) -> "Commission":
        d = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        d["steps"] = {k: StepResult(**v) for k, v in d.get("steps", {}).items()}
        return cls(**d)

    @classmethod
    def simulated(cls, serial: str = "DEMO-0000", operator: str = "sim") -> "Commission":
        c = cls(serial=serial, operator=operator)
        for s in STEPS:
            c.steps[str(s.n)] = StepResult(status="simulated", note="仿真占位，不计入物理闸门")
        return c


def _step(n: int) -> Step:
    for s in STEPS:
        if s.n == n:
            return s
    raise BringupError(f"没有第 {n} 步（1–{len(STEPS)}）")


def format_steps(rec: Commission | None = None) -> str:
    lines = [f"{'#':>2}  {'状态':<9} {'闸门':<4} 标题"]
    for s in STEPS:
        st = rec.steps[str(s.n)].status if rec else "pending"
        lines.append(f"{s.n:>2}  {st:<9} {s.gate:<4} {s.title}")
    return "\n".join(lines)


def format_status(rec: Commission) -> str:
    lines = [format_steps(rec), "",
             f"实测通过 {rec.pass_count()}/{len(STEPS)} 步；"
             f"物理闸门 {rec.physical_passed()}/5（M1–M5）"]
    if rec.simulated_count():
        lines.append(f"注意：{rec.simulated_count()} 步只是 simulated，不计入物理通过。")
    for k in MILESTONES:
        lines.append(f"  {k}: {rec.milestone(k)}")
    nxt = rec.next_step()
    if nxt:
        lines.append(f"下一步 #{nxt.n} {nxt.title}：{nxt.command}")
    elif rec.pass_count() == len(STEPS):
        lines.append("全部步骤已有实测记录；仍以 docs/18 质检结论为准。")
    else:
        lines.append("这是 simulated 演示，不计入物理；开始实测请新建记录。")
    return "\n".join(lines)


def readonly_check(bot, expect: int = 6) -> dict:
    """只读检查：scan + 读反馈，不发任何运动/扭矩指令。"""
    ids = bot.scan()
    rows = []
    faults = 0
    for sid in ids:
        try:
            fb = bot.feedback(sid)
            rows.append({"id": sid, "position_deg": round(fb.position_deg, 1),
                         "voltage": round(fb.voltage, 2), "temp_c": fb.temp_c,
                         "faults": fb.faults})
            if fb.faults:
                faults += 1
        except Exception as e:  # 单个舵机读失败不影响其余
            rows.append({"id": sid, "error": f"{type(e).__name__}: {e}"})
            faults += 1
    return {"ids": ids, "count": len(ids), "expect": expect,
            "ok": len(ids) >= expect and faults == 0,
            "faults": faults, "rows": rows}
