"""阶段化 bring-up 记录：给阶段 0/1/2/3 用的证据台账。

和 `bringup.py` 的区别：
  · `bringup` 是整机 M1 的 11 步（六轴/视觉/任务），阶段 0 根本用不上；
  · 本模块按装配能力生成步骤（单关节/臂/底盘/绘图/抓取），可单独记录；
  · 仍然只认**存在的证据文件 + sha256**；simulated 不计入物理闸门；
  · 不改变整机物理闸门 0/5。

用法::

    modkit stage --action init --assembly ../assemblies/bench_joint.json \
        --serial J-001 --operator 老王
    modkit stage --action record --step 2 --result pass --evidence scan.txt
    modkit stage --action status
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import time
from dataclasses import asdict, dataclass, field

from . import assembly as asm
from . import pack

DEFAULT_FILE = "records/stage-bringup.json"
STATUSES = ("pending", "pass", "fail", "simulated")


class StageError(RuntimeError):
    pass


def sha256_file(path: str | pathlib.Path) -> str:
    h = hashlib.sha256()
    h.update(pathlib.Path(path).read_bytes())
    return h.hexdigest()


@dataclass
class Result:
    status: str = "pending"
    note: str = ""
    evidence: str = ""
    sha256: str = ""
    at: str = ""


@dataclass
class Record:
    assembly: str
    stage: str
    stage_title: str
    serial: str
    operator: str
    date: str = field(default_factory=lambda: time.strftime("%Y-%m-%d"))
    steps: dict[str, Result] = field(default_factory=dict)
    notes: str = ""
    plan_data: list[dict] = field(default_factory=list)
    assembly_sha256: str = ""

    def __post_init__(self) -> None:
        # 允许从 JSON 恢复时 steps 已带内容；只补缺的步骤。
        for s in self.plan:
            self.steps.setdefault(str(s["n"]), Result())

    @property
    def plan(self) -> list[dict]:
        # 记录一旦 init 就冻结步骤；装配后来改了，也不让旧证据错位。
        if self.plan_data:
            return self.plan_data
        r = asm.load_and_validate(self.assembly)
        return pack.bringup_steps(r)

    def assembly_changed(self) -> bool:
        if not self.assembly_sha256:
            return False
        p = pathlib.Path(self.assembly)
        return not p.is_file() or sha256_file(p) != self.assembly_sha256

    def record(self, n: int, status: str, evidence: str = "", note: str = "") -> Result:
        if status not in STATUSES or status == "pending":
            raise StageError("结果只能是 pass/fail/simulated")
        steps = {s["n"]: s for s in self.plan}
        if n not in steps:
            raise StageError(f"没有第 {n} 步（1–{len(steps)}）")
        if status == "pass":
            if not evidence:
                raise StageError(f"第 {n} 步 pass 必须带 --evidence")
            p = pathlib.Path(evidence)
            if not p.is_file() or p.stat().st_size == 0:
                raise StageError(f"证据文件不存在或为空：{evidence}")
        r = Result(status=status, note=note, evidence=evidence,
                   sha256=sha256_file(evidence) if evidence and pathlib.Path(evidence).is_file() else "",
                   at=time.strftime("%Y-%m-%dT%H:%M:%S"))
        self.steps[str(n)] = r
        return r

    def pass_count(self) -> int:
        return sum(1 for r in self.steps.values() if r.status == "pass")

    def simulated_count(self) -> int:
        return sum(1 for r in self.steps.values() if r.status == "simulated")

    def next_step(self) -> dict | None:
        for s in self.plan:
            if self.steps.get(str(s["n"]), Result()).status != "pass":
                return s
        return None

    def validate(self) -> list[str]:
        errs = []
        if not self.serial or not self.operator:
            errs.append("缺序列号或操作人")
        if self.simulated_count():
            errs.append(f"有 {self.simulated_count()} 步是 simulated，不能当物理证据")
        if self.assembly_changed():
            errs.append("装配文件在记录后被修改；旧步骤/证据可能错位，建议重新 init")
        for s in self.plan:
            r = self.steps.get(str(s["n"]), Result())
            if r.status == "pass":
                if not r.evidence or not pathlib.Path(r.evidence).is_file():
                    errs.append(f"第 {s['n']} 步 pass 但证据不存在：{r.evidence}")
                elif r.sha256 and sha256_file(r.evidence) != r.sha256:
                    errs.append(f"第 {s['n']} 步证据被修改（sha256 不符）")
        return errs

    def save(self, path: str | pathlib.Path = DEFAULT_FILE, overwrite: bool = True) -> pathlib.Path:
        p = pathlib.Path(path)
        if p.exists() and not overwrite:
            raise StageError(f"记录已存在：{p}")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")
        return p

    @classmethod
    def load(cls, path: str | pathlib.Path = DEFAULT_FILE) -> "Record":
        d = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        d["steps"] = {k: Result(**v) for k, v in d.get("steps", {}).items()}
        return cls(**d)


def init_record(assembly: str | pathlib.Path, serial: str, operator: str) -> Record:
    r = asm.load_and_validate(assembly)
    if not r.ok:
        raise StageError("装配有错误，先修好再记录")
    st = pack.classify(r)
    rec = Record(assembly=str(assembly), stage=st.key, stage_title=st.title,
                 serial=serial, operator=operator,
                 plan_data=pack.bringup_steps(r),
                 assembly_sha256=sha256_file(assembly))
    return rec


def format_plan(rec: Record) -> str:
    out = [f"{rec.stage_title} · {rec.assembly}",
           f"{'#':>2}  {'状态':<9} 步骤"]
    for s in rec.plan:
        st = rec.steps.get(str(s["n"]), Result()).status
        out.append(f"{s['n']:>2}  {st:<9} {s['title']}")
    return "\n".join(out)


def format_status(rec: Record) -> str:
    total = len(rec.plan)
    out = [format_plan(rec), "",
           f"阶段通过 {rec.pass_count()}/{total} 步；整机物理闸门仍 0/5。"]
    if rec.simulated_count():
        out.append(f"注意：{rec.simulated_count()} 步只是 simulated，不计入物理通过。")
    nxt = rec.next_step()
    if nxt:
        out.append(f"下一步 #{nxt['n']} {nxt['title']}")
        out.append(f"  命令：{nxt['command']}")
        out.append(f"  通过：{nxt['pass']}")
        out.append(f"  证据：{nxt['evidence']}")
    elif rec.pass_count() == total:
        out.append("本阶段步骤都有实测记录；仍需按 docs/18 验收整机。")
    return "\n".join(out)


__all__ = ["StageError", "Result", "Record", "init_record", "format_plan", "format_status"]
