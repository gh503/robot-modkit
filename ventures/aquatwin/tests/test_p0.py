import copy
import csv
import json
import pathlib

import pytest

from aquatwin import calibrate, cli, model, report
from aquatwin.measurements import MeasurementError, MeasurementRun, MeasurementSet, study_for_run
from aquatwin.scenario import Study

ROOT = pathlib.Path(__file__).resolve().parents[1]


def base():
    return Study.load(ROOT / "scenarios" / "residential_8x4.json")


def synthetic(study, time_scale=1.15, setup=2.5, energy_scale=0.90, pressure_scale=1.30):
    conds = [{"speed_m_s": 0.18}, {"speed_m_s": 0.25},
             {"speed_m_s": 0.32}, {"debris_g_m3": 9.0}]
    runs = []
    for i, c in enumerate(conds):
        s = study_for_run(study, MeasurementRun(f"run-{i+1}", 1, 1, conditions=c))
        r = model.run(s)["results"]
        runs.append(MeasurementRun(
            run_id=f"run-{i+1}",
            time_min=r["active_time_min"] * time_scale + setup,
            energy_wh=r["energy_wh"] * energy_scale,
            coverage_pct=98.0,
            pressure_kpa=r["filter_pressure_rise_kpa"] * pressure_scale,
            conditions=c,
            notes="synthetic; not field data",
        ))
    return MeasurementSet(study=study.name, runs=runs, source="synthetic")


def test_synthetic_calibration_recovers_factors():
    s = base()
    ms = synthetic(s)
    assert ms.validate()["ok"]
    cal = calibrate.calibrate(s, ms)
    f = cal["factors"]
    assert f["time_scale"] == pytest.approx(1.15, abs=0.02)
    assert f["setup_min"] == pytest.approx(2.5, abs=0.15)
    assert f["energy_scale"] == pytest.approx(0.90, abs=0.01)
    assert f["pressure_scale"] == pytest.approx(1.30, abs=0.02)
    assert cal["metrics"]["time_mape_pct"] < 1.0
    assert cal["metrics"]["energy_mape_pct"] < 1.0
    assert "time_scale" in cal["confidence_90"]
    assert cal["confidence_90"]["time_scale"]["low"] <= f["time_scale"] <= cal["confidence_90"]["time_scale"]["high"]
    assert cal["source"] == "synthetic"
    assert any("非现场" in x for x in cal["caveats"])


def test_calibration_applies_to_run():
    s = base()
    ms = synthetic(s)
    cal = calibrate.calibrate(s, ms)
    base_result = model.run(s)["results"]
    full = model.run(s, calibration=cal)
    calibrated = full["results"]
    assert calibrated["total_time_min"] > base_result["total_time_min"]
    assert calibrated["energy_wh"] < base_result["energy_wh"]
    assert calibrated["filter_pressure_rise_kpa"] > base_result["filter_pressure_rise_kpa"]
    assert calibrated["cost_per_cleaning_cny"] != base_result["cost_per_cleaning_cny"]
    assert full["calibration"]["applied"] is True


def test_measurements_csv_json_roundtrip(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text("run_id,time_min,energy_wh,coverage_pct,pressure_kpa,source,study,speed_m_s\n"
                 "r1,6.2,10.5,98,4.1,synthetic,住宅泳池 8×4m,0.25\n", encoding="utf-8")
    ms = MeasurementSet.from_csv(p)
    assert ms.source == "synthetic"
    assert ms.study == "住宅泳池 8×4m"
    assert ms.runs[0].conditions["speed_m_s"] == 0.25
    assert ms.validate()["ok"]
    q = ms.save(tmp_path / "m.json")
    again = MeasurementSet.load(q)
    assert again.to_dict() == ms.to_dict()
    assert len(ms.sha256()) == 64


def test_invalid_measurements_and_conditions():
    s = base()
    ms = MeasurementSet(study=s.name, runs=[], source="field")
    assert not ms.validate()["ok"]
    with pytest.raises(MeasurementError):
        MeasurementSet.from_csv(ROOT / "scenarios" / "residential_8x4.json")  # JSON via CSV path
    ms = MeasurementSet(study=s.name, source="field", runs=[
        MeasurementRun("a", -1, 1), MeasurementRun("a", 1, -1)])
    assert not ms.validate()["ok"]
    with pytest.raises(MeasurementError):
        study_for_run(s, MeasurementRun("x", 1, 1, conditions={"nope": 1}))


def test_report_calibration_and_quote(tmp_path):
    s = base()
    ms = synthetic(s)
    cal = calibrate.calibrate(s, ms)
    result = model.run(s, calibration=cal)
    paths = report.write(s, result, tmp_path, calibration=cal, measurements=ms)
    assert pathlib.Path(paths["calibration"]).is_file()
    assert pathlib.Path(paths["validation"]).is_file()
    assert pathlib.Path(paths["quote"]).is_file()
    md = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "校准因子" in md and "未应用实测校准" not in md
    val = (tmp_path / "validation.md").read_text(encoding="utf-8")
    assert "synthetic" in val and "不是现场实测" in val
    html = (tmp_path / "quote.html").read_text(encoding="utf-8")
    assert "AquaTwin 清洁方案报价" in html and "不是性能保证" in html


def test_cli_calibrate_study_batch_quote(tmp_path, capsys):
    s = base()
    ms = synthetic(s)
    mp = ms.save(tmp_path / "m.json")
    caldir = tmp_path / "cal"
    assert cli.main(["measurements", "--file", str(mp)]) == 0
    assert "PASS" in capsys.readouterr().out
    assert cli.main(["calibrate", "--scenario", str(ROOT / "scenarios" / "residential_8x4.json"),
                     "--measurements", str(mp), "--out", str(caldir)]) == 0
    assert "time_scale" in capsys.readouterr().out
    assert (caldir / "calibration.json").is_file()
    assert (caldir / "validation.md").is_file()
    out = tmp_path / "study"
    assert cli.main(["study", "--scenario", str(ROOT / "scenarios" / "residential_8x4.json"),
                     "--calibration", str(caldir / "calibration.json"), "--out", str(out)]) == 0
    assert (out / "calibration.json").is_file()
    assert (out / "quote.html").is_file()
    batch = tmp_path / "batch"
    assert cli.main(["batch", "--dir", str(ROOT / "scenarios"), "--out", str(batch)]) == 0
    assert (batch / "portfolio.json").is_file()
    assert (batch / "portfolio.md").is_file()
    assert (batch / "portfolio.html").is_file()
    q = tmp_path / "quote"
    assert cli.main(["quote", "--scenario", str(ROOT / "scenarios" / "small_6x3.json"),
                     "--out", str(q), "--customer", "测试"]) == 0
    assert "客户：测试" in (q / "quote.html").read_text(encoding="utf-8")


def test_batch_handles_bad_file(tmp_path):
    from aquatwin import batch
    good = ROOT / "scenarios" / "small_6x3.json"
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    s = batch.run_batch([good, bad], tmp_path / "out")
    assert s["n"] == 1 and s["n_errors"] == 1
    assert "失败" in (tmp_path / "out" / "portfolio.md").read_text(encoding="utf-8")
