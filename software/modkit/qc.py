"""生产记录：序列号、质检结果、标定文件指纹。

为什么写成代码而不是表格模板：
1. 序列号要唯一（重号会让售后查不到批次）；
2. "合格"不能靠人选，判据写在 validate() 里，CI 也能跑；
3. 记录是 JSON，能直接汇总成良率，不用再手抄一遍。

用法：
    python -m modkit.cli qc --action new --serial M1-2026-0001 --operator 老王
    python -m modkit.cli qc --action show records/M1-2026-0001.json
    python -m modkit.cli qc --action validate records/*.json
    python -m modkit.cli qc --action summary records/*.json
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import time
from dataclasses import asdict, dataclass, field

SERIAL_RE = re.compile(r"^M1-\d{4}-\d{4}$")

# 判据（与 docs/18 一致）
MIN_GRASP_SUCCESS = 8       # 10 次里至少 8 次
MAX_REPEAT_MM = 2.0
MAX_TEMP_C = 55.0
MIN_RUNTIME_MIN = 40.0


class QcError(RuntimeError):
    pass


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Record:
    serial: str
    operator: str
    date: str = field(default_factory=lambda: time.strftime("%Y-%m-%d"))
    # Q1 零件
    q1: list[Check] = field(default_factory=list)
    # Q2 装配
    q2: list[Check] = field(default_factory=list)
    # Q3 功能
    grasp_success: int = 0
    grasp_total: int = 10
    repeatability_mm: float = 99.0
    temp_c: float = 99.0
    runtime_min: float = 0.0
    calibration_sha256: str = ""
    firmware_version: str = ""
    notes: str = ""
    conclusion: str = "待检"      # 合格 / 返修 / 报废

    def validate(self) -> list[str]:
        errs = []
        if not SERIAL_RE.match(self.serial):
            errs.append(f"序列号格式不对：{self.serial}（应形如 M1-2026-0001）")
        if not self.operator:
            errs.append("缺装配人")
        if self.conclusion not in ("合格", "返修", "报废", "待检"):
            errs.append(f"结论取值非法：{self.conclusion}")
        if self.conclusion == "合格":
            if not all(c.ok for c in self.q1):
                errs.append("Q1 有未通过项，不能判合格")
            if not all(c.ok for c in self.q2):
                errs.append("Q2 有未通过项，不能判合格")
            if self.grasp_success < MIN_GRASP_SUCCESS:
                errs.append(f"抓放 {self.grasp_success}/{self.grasp_total} < {MIN_GRASP_SUCCESS}")
            if self.repeatability_mm > MAX_REPEAT_MM:
                errs.append(f"重复精度 {self.repeatability_mm}mm > {MAX_REPEAT_MM}")
            if self.temp_c >= MAX_TEMP_C:
                errs.append(f"温升 {self.temp_c}℃ ≥ {MAX_TEMP_C}")
            if not self.calibration_sha256:
                errs.append("缺标定文件指纹")
            if not self.firmware_version:
                errs.append("缺固件版本")
        return errs

    def save(self, root: str | pathlib.Path = "records") -> pathlib.Path:
        root = pathlib.Path(root)
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{self.serial}.json"
        if path.exists():
            raise QcError(f"序列号已存在：{path}（换一个号，不要覆盖历史记录）")
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: str | pathlib.Path) -> "Record":
        d = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        d["q1"] = [Check(**c) for c in d.get("q1", [])]
        d["q2"] = [Check(**c) for c in d.get("q2", [])]
        return cls(**d)


def default_checks() -> tuple[list[Check], list[Check]]:
    """Q1/Q2 默认项，全填 False，现场逐项改。"""
    q1 = [Check(n, False) for n in (
        "关键尺寸（板厚/孔距/孔径）", "无层裂/翘曲 <1mm", "热熔螺母齐平且拉力 ≥50N",
        "圆孔无支撑残留", "M3 螺丝手拧到底不滑牙")]
    q2 = [Check(n, False) for n in (
        "关节全程无卡滞", "关节回差 <2mm", "四轮共面 <1mm", "夹爪闭合间隙 <1mm",
        "12V 无短路", "舵机 ID 与文档一致", "急停断电有效", "保险丝 5A 正确")]
    return q1, q2


def sha256_file(path: str | pathlib.Path) -> str:
    h = hashlib.sha256()
    h.update(pathlib.Path(path).read_bytes())
    return h.hexdigest()


def summary(paths: list[str | pathlib.Path]) -> dict:
    recs = [Record.load(p) for p in paths]
    total = len(recs)
    good = sum(1 for r in recs if r.conclusion == "合格")
    rework = sum(1 for r in recs if r.conclusion == "返修")
    scrap = sum(1 for r in recs if r.conclusion == "报废")
    return {
        "total": total,
        "pass": good,
        "rework": rework,
        "scrap": scrap,
        "yield": round(good / total * 100, 1) if total else 0.0,
        "serials": [r.serial for r in recs],
    }


def next_serial(root: str | pathlib.Path = "records", year: int | None = None) -> str:
    root = pathlib.Path(root)
    year = year or time.localtime().tm_year
    existing = sorted(root.glob(f"M1-{year}-*.json")) if root.exists() else []
    n = len(existing) + 1
    while True:
        cand = f"M1-{year}-{n:04d}"
        if not (root / f"{cand}.json").exists():
            return cand
        n += 1