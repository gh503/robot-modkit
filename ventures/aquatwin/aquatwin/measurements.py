"""AquaTwin 实测数据 schema、CSV/JSON 导入与校验。

这是“预测 vs 实测”的入口，不是造数据的工具。没有 `source=field` 的数据，
报告必须标成 synthetic/vendor/lab，不能当现场验证。
"""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import math
import pathlib
from dataclasses import asdict, dataclass, field

from .scenario import ScenarioError, Study


class MeasurementError(ValueError):
    pass


SOURCE_KINDS = ("field", "lab", "vendor", "synthetic")
CONDITION_FIELDS = {
    "speed_m_s": "robot",
    "swath_m": "robot",
    "overlap": "robot",
    "turn_time_s": "robot",
    "battery_wh": "robot",
    "pump_flow_m3_s": "robot",
    "pump_head_m": "robot",
    "pump_efficiency": "robot",
    "drag_cd": "robot",
    "body_area_m2": "robot",
    "debris_g_m3": "pool",
    "water_temp_c": "pool",
    "salinity_ppt": "pool",
    "length_m": "pool",
    "width_m": "pool",
    "depth_m": "pool",
}


def _num(v) -> float | None:
    if v is None or str(v).strip() == "":
        return None
    try:
        x = float(v)
    except (TypeError, ValueError) as e:
        raise MeasurementError(f"不是数字：{v!r}") from e
    if not math.isfinite(x):
        raise MeasurementError(f"不是有限数：{v!r}")
    return x


@dataclass
class MeasurementRun:
    run_id: str
    time_min: float
    energy_wh: float
    coverage_pct: float | None = None
    pressure_kpa: float | None = None
    debris_g: float | None = None
    conditions: dict = field(default_factory=dict)
    notes: str = ""

    def validate(self, errors: list[str], warnings: list[str]) -> None:
        if not self.run_id:
            errors.append("run_id 不能为空")
        if not (self.time_min > 0):
            errors.append(f"{self.run_id}: time_min 必须 >0")
        if self.energy_wh < 0:
            errors.append(f"{self.run_id}: energy_wh 不能为负")
        if self.coverage_pct is not None and not 0 <= self.coverage_pct <= 100:
            errors.append(f"{self.run_id}: coverage_pct 必须在 0..100")
        if self.pressure_kpa is not None and self.pressure_kpa < 0:
            errors.append(f"{self.run_id}: pressure_kpa 不能为负")
        if self.debris_g is not None and self.debris_g < 0:
            errors.append(f"{self.run_id}: debris_g 不能为负")
        for k, v in self.conditions.items():
            if k not in CONDITION_FIELDS:
                errors.append(f"{self.run_id}: 未知 conditions.{k}")
            elif not isinstance(v, (int, float)) or not math.isfinite(float(v)):
                errors.append(f"{self.run_id}: conditions.{k} 必须是有限数字")
        if not self.conditions:
            warnings.append(f"{self.run_id}: 没有 conditions；多组数据无法区分参数")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MeasurementSet:
    study: str
    runs: list[MeasurementRun]
    source: str = "field"
    collected_at: str = ""
    instrumentation: str = ""
    schema: str = "aquatwin.measurements/1"
    notes: str = ""

    def validate(self) -> dict:
        errors: list[str] = []
        warnings: list[str] = []
        if self.schema != "aquatwin.measurements/1":
            errors.append("schema 必须是 aquatwin.measurements/1")
        if not self.study:
            warnings.append("没有 study 名称；校准仍可用，但报告无法自动核对场景")
        if self.source not in SOURCE_KINDS:
            errors.append(f"source 必须是 {SOURCE_KINDS}")
        if not self.runs:
            errors.append("至少需要 1 条 run")
        ids = set()
        for r in self.runs:
            if r.run_id in ids:
                errors.append(f"run_id 重复：{r.run_id}")
            ids.add(r.run_id)
            r.validate(errors, warnings)
        if len(self.runs) < 3:
            warnings.append("run 少于 3 条，校准参数不可靠")
        if self.source != "field":
            warnings.append(f"source={self.source}：不是现场实测，不能对外写 field-validated")
        return {"ok": not errors, "errors": errors, "warnings": warnings,
                "n_runs": len(self.runs)}

    def to_dict(self) -> dict:
        return {"schema": self.schema, "study": self.study, "source": self.source,
                "collected_at": self.collected_at, "instrumentation": self.instrumentation,
                "notes": self.notes, "runs": [r.to_dict() for r in self.runs]}

    @classmethod
    def from_dict(cls, d: dict) -> "MeasurementSet":
        try:
            runs = [MeasurementRun(**r) for r in d.get("runs", [])]
        except TypeError as e:
            raise MeasurementError(f"run 字段不匹配：{e}") from e
        return cls(study=d.get("study", ""), runs=runs,
                   source=d.get("source", "field"),
                   collected_at=d.get("collected_at", ""),
                   instrumentation=d.get("instrumentation", ""),
                   schema=d.get("schema", "aquatwin.measurements/1"),
                   notes=d.get("notes", ""))

    @classmethod
    def load(cls, path: str | pathlib.Path) -> "MeasurementSet":
        p = pathlib.Path(path)
        if p.suffix.lower() == ".csv":
            return cls.from_csv(p)
        try:
            return cls.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError as e:
            raise MeasurementError(f"JSON 解析失败：{e}") from e

    @classmethod
    def from_csv(cls, path: str | pathlib.Path, study: str = "", source: str = "field",
                 instrumentation: str = "", collected_at: str = "") -> "MeasurementSet":
        p = pathlib.Path(path)
        with p.open(newline="", encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        if not rows:
            raise MeasurementError("CSV 没有数据行")
        runs = []
        for i, row in enumerate(rows, 2):
            rid = (row.get("run_id") or "").strip()
            if not rid:
                raise MeasurementError(f"第 {i} 行缺少 run_id")
            try:
                t = _num(row.get("time_min"))
                e = _num(row.get("energy_wh"))
            except MeasurementError as ex:
                raise MeasurementError(f"第 {i} 行：{ex}") from ex
            if t is None or e is None:
                raise MeasurementError(f"第 {i} 行缺少 time_min/energy_wh")
            conds = {}
            for k in CONDITION_FIELDS:
                if k in row and str(row[k]).strip() != "":
                    v = _num(row[k])
                    conds[k] = v
            runs.append(MeasurementRun(
                run_id=rid, time_min=t, energy_wh=e,
                coverage_pct=_num(row.get("coverage_pct")),
                pressure_kpa=_num(row.get("pressure_kpa")),
                debris_g=_num(row.get("debris_g")),
                conditions=conds, notes=(row.get("notes") or "").strip()))
        if not study and rows:
            study = (rows[0].get("study") or "").strip()
        if rows and (rows[0].get("source") or "").strip():
            source = (rows[0].get("source") or source).strip()
        return cls(study=study, runs=runs, source=source,
                   collected_at=collected_at, instrumentation=instrumentation)

    def save(self, path: str | pathlib.Path) -> pathlib.Path:
        p = pathlib.Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")
        return p

    def sha256(self) -> str:
        raw = json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


def study_for_run(study: Study, run: MeasurementRun) -> Study:
    """把 run 的条件叠加到场景副本；不修改原场景。"""
    s = copy.deepcopy(study)
    for k, v in run.conditions.items():
        target = CONDITION_FIELDS.get(k)
        if target == "robot":
            setattr(s.robot, k, float(v))
        elif target == "pool":
            setattr(s.pool, k, float(v))
        else:
            raise MeasurementError(f"未知条件 {k}")
    # 改了长宽深就不要再沿用旧 volume
    if any(k in run.conditions for k in ("length_m", "width_m", "depth_m")):
        s.pool.volume_m3 = None
    v = s.validate()
    if not v["ok"]:
        raise MeasurementError("条件叠加后场景非法：" + "；".join(v["errors"]))
    return s


__all__ = ["MeasurementError", "MeasurementRun", "MeasurementSet",
           "SOURCE_KINDS", "CONDITION_FIELDS", "study_for_run"]
