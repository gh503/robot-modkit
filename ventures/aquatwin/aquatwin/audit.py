"""模型审计：把“软件可用”与“现场已验证”分开。

输出 fixed schema，检查模型版本、校准边界、置信区间、数据来源、样本量、
误差指标与物理闸门。审计通过 ≠ 现场通过；物理闸门始终显式记录为 0/5。
"""

from __future__ import annotations

import hashlib
import json
import math
import pathlib

from . import model
from .measurements import MeasurementSet
from .scenario import Study

AUDIT_SCHEMA = "aquatwin.audit/1"


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def _check(cid: str, status: str, detail: str) -> dict:
    if status not in ("pass", "warn", "fail"):
        raise ValueError(status)
    return {"id": cid, "status": status, "detail": detail}


def schema_def() -> dict:
    """`aquatwin.audit/1` 的 JSON Schema；field_validated 硬约束为 false。"""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/gh503/robot-modkit/schema/aquatwin-audit-1.json",
        "title": AUDIT_SCHEMA,
        "type": "object",
        "required": ["schema", "model_version", "study", "software_ready",
                     "field_validated", "physical_gate", "status", "checks", "hashes"],
        "properties": {
            "schema": {"const": AUDIT_SCHEMA},
            "model_version": {"type": "string", "minLength": 1},
            "study": {"type": "string", "minLength": 1},
            "software_ready": {"type": "boolean"},
            "field_validated": {"const": False},
            "physical_gate": {"const": "0/5"},
            "status": {"enum": ["fail", "provisional", "software-pass"]},
            "checks": {"type": "array", "items": {
                "type": "object",
                "required": ["id", "status", "detail"],
                "properties": {
                    "id": {"type": "string"},
                    "status": {"enum": ["pass", "warn", "fail"]},
                    "detail": {"type": "string"},
                },
                "additionalProperties": False,
            }},
            "warnings": {"type": "array", "items": {"type": "string"}},
            "hashes": {"type": "object"},
            "note": {"type": "string"},
            "outputs": {"type": "object"},
        },
        "additionalProperties": False,
    }


def run(study: Study, result: dict, *, calibration: dict | None = None,
        measurements: MeasurementSet | None = None) -> dict:
    checks = [_check("model_version",
                     "pass" if result.get("model_version") == model.MODEL_VERSION else "fail",
                     f"运行模型 {result.get('model_version')}；代码模型 {model.MODEL_VERSION}")]
    checks.append(_check("scenario", "pass",
                         f"场景校验通过；池面积 {study.pool.area_m2:.2f} m²"))
    if calibration is None:
        checks.append(_check("calibration", "warn", "未应用校准；输出是未校准预测"))
    else:
        f = calibration.get("factors", {})
        bad = []
        for k, (lo, hi) in model.FACTOR_BOUNDS.items():
            v = f.get(k)
            if not isinstance(v, (int, float)) or not math.isfinite(float(v)) or not lo <= v <= hi:
                bad.append(f"{k}={v} 不在 [{lo},{hi}]")
        checks.append(_check("calibration_bounds", "fail" if bad else "pass",
                             "；".join(bad) if bad else "4 个因子都在物理边界内"))
        if calibration.get("study") and calibration["study"] != study.name:
            checks.append(_check("study_match", "fail",
                                 f"校准属于 {calibration['study']}，当前 {study.name}"))
        else:
            checks.append(_check("study_match", "pass", "场景名一致"))
        if calibration.get("model_version") != model.MODEL_VERSION:
            checks.append(_check("calibration_model_version", "fail",
                                 f"校准模型 {calibration.get('model_version')} != {model.MODEL_VERSION}"))
        ci = calibration.get("confidence_90", {})
        if ci:
            bad = [k for k, v in ci.items()
                   if not isinstance(v, dict) or not all(
                       isinstance(v.get(x), (int, float)) and math.isfinite(float(v[x]))
                       for x in ("low", "high")) or v["low"] > v["high"]]
            checks.append(_check("confidence_90", "fail" if bad else "pass",
                                 "区间非法：" + ",".join(bad) if bad else
                                 f"{len(ci)} 个因子的 90% bootstrap 区间有效"))
        else:
            checks.append(_check("confidence_90", "warn", "没有置信区间（样本 <3 或旧格式）"))
    if measurements is None:
        checks.append(_check("data_source", "warn", "没有测量数据；不能称现场验证"))
        checks.append(_check("sample_size", "warn", "没有测量数据"))
    else:
        src = measurements.source
        checks.append(_check("data_source", "pass" if src == "field" else "warn",
                             f"source={src}" + ("" if src == "field" else "；非现场实测，不能写 field-validated")))
        checks.append(_check("sample_size", "pass" if len(measurements.runs) >= 3 else "warn",
                             f"{len(measurements.runs)} 条 run" +
                             ("" if len(measurements.runs) >= 3 else "；少于 3 不可靠")))
    metrics = (calibration or {}).get("metrics", {})
    for key, label, limit in (("time_mape_pct", "时间 MAPE", 20.0),
                              ("energy_mape_pct", "能耗 MAPE", 20.0)):
        v = metrics.get(key)
        if v is None:
            checks.append(_check(key, "warn", f"没有 {label}"))
        elif v <= limit:
            checks.append(_check(key, "pass", f"{label} {v:.2f}% ≤ {limit:g}%"))
        else:
            checks.append(_check(key, "warn", f"{label} {v:.2f}% > {limit:g}%"))
    checks.append(_check("field_validation", "warn", "物理闸门 0/5；没有现场验收记录"))
    errors = [c for c in checks if c["status"] == "fail"]
    warnings = [c for c in checks if c["status"] == "warn"]
    return {
        "schema": AUDIT_SCHEMA,
        "model_version": model.MODEL_VERSION,
        "study": study.name,
        "software_ready": not errors,
        "field_validated": False,
        "physical_gate": "0/5",
        "status": "fail" if errors else ("provisional" if warnings else "software-pass"),
        "checks": checks,
        "warnings": [c["detail"] for c in warnings],
        "hashes": {
            "study_sha256": _sha(study.to_dict()),
            "measurements_sha256": measurements.sha256() if measurements else None,
            "calibration_sha256": _sha(calibration) if calibration else None,
        },
        "note": "software_ready 只代表代码/数据管线通过；field_validated 永远需要现场证据。",
    }


def markdown(study: Study, audit: dict) -> str:
    L = [f"# AquaTwin 模型审计：{study.name}", "",
         f"- 审计状态：**{audit['status']}**；软件可用：{'是' if audit['software_ready'] else '否'}；"
         f"现场验证：{'是' if audit['field_validated'] else '否'}",
         f"- 模型：`{audit['model_version']}`；物理闸门：**{audit['physical_gate']}**", "",
         "| 检查 | 状态 | 说明 |", "|---|---|---|"]
    for c in audit["checks"]:
        L.append(f"| {c['id']} | {c['status']} | {c['detail']} |")
    L += ["", "## 输入哈希", ""]
    for k, v in audit["hashes"].items():
        L.append(f"- `{k}`：`{v or '—'}`")
    L += ["", "## 边界", "",
          "- 审计通过只说明软件/数据管线可复现；不是现场实测通过；",
          "- `field_validated` 永远为 false，除非有独立的现场验收证据并更新流程；",
          "- 物理闸门保持 **0/5**。", ""]
    return "\n".join(L)


def write(study: Study, audit: dict, out: str | pathlib.Path) -> dict:
    d = pathlib.Path(out)
    d.mkdir(parents=True, exist_ok=True)
    (d / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
                                  encoding="utf-8")
    (d / "audit.md").write_text(markdown(study, audit), encoding="utf-8")
    return {"audit_json": str(d / "audit.json"), "audit_md": str(d / "audit.md")}


__all__ = ["AUDIT_SCHEMA", "schema_def", "run", "markdown", "write"]
