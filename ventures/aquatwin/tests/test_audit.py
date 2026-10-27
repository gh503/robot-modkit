import copy
import json
import pathlib

from aquatwin import audit as au
from aquatwin import calibrate as cb
from aquatwin import cli, model
from aquatwin.measurements import MeasurementSet
from aquatwin.scenario import Study

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_synthetic_audit_is_provisional_and_gate_zero():
    s = Study.load(ROOT / "scenarios" / "residential_8x4.json")
    ms = MeasurementSet.load(ROOT / "data" / "measurements-example.csv")
    cal = cb.calibrate(s, ms)
    r = model.run(s, calibration=cal)
    a = au.run(s, r, calibration=cal, measurements=ms)
    assert a["schema"] == "aquatwin.audit/1"
    assert a["status"] == "provisional"
    assert a["software_ready"] is True
    assert a["field_validated"] is False
    assert a["physical_gate"] == "0/5"
    assert any("synthetic" in w for w in a["warnings"])
    assert a["hashes"]["measurements_sha256"] == ms.sha256()


def test_audit_fails_out_of_bounds_or_version():
    s = Study.load(ROOT / "scenarios" / "residential_8x4.json")
    ms = MeasurementSet.load(ROOT / "data" / "measurements-example.csv")
    cal = cb.calibrate(s, ms)
    cal["factors"]["time_scale"] = 99
    r = model.run(s)
    a = au.run(s, r, calibration=cal, measurements=ms)
    assert a["software_ready"] is False and a["status"] == "fail"
    assert any(c["id"] == "calibration_bounds" and c["status"] == "fail" for c in a["checks"])
    r["model_version"] = "old"
    a2 = au.run(s, r, calibration=cal, measurements=ms)
    assert any(c["id"] == "model_version" and c["status"] == "fail" for c in a2["checks"])


def test_field_source_still_not_claimed_validated():
    s = Study.load(ROOT / "scenarios" / "small_6x3.json")
    ms = MeasurementSet.load(ROOT / "data" / "measurements-example.csv")
    ms = copy.deepcopy(ms)
    ms.source = "field"
    cal = cb.calibrate(s, ms)
    r = model.run(s, calibration=cal)
    a = au.run(s, r, calibration=cal, measurements=ms)
    assert a["field_validated"] is False
    assert a["physical_gate"] == "0/5"
    assert any(c["id"] == "data_source" and c["status"] == "pass" for c in a["checks"])


def test_audit_cli_outputs(tmp_path):
    rc = cli.main(["audit", "--scenario", str(ROOT / "scenarios" / "small_6x3.json"),
                   "--measurements", str(ROOT / "data" / "measurements-example.csv"),
                   "--out", str(tmp_path)])
    assert rc == 0
    d = json.loads((tmp_path / "audit.json").read_text())
    assert d["physical_gate"] == "0/5"
    assert (tmp_path / "audit.md").is_file()


def test_audit_schema_hardcodes_zero_gate():
    d = au.schema_def()
    assert d["properties"]["field_validated"] == {"const": False}
    assert d["properties"]["physical_gate"] == {"const": "0/5"}
    assert "checks" in d["required"]


def test_audit_schema_cli():
    import subprocess, sys
    out = subprocess.run([sys.executable, "-m", "aquatwin.cli", "schema", "--what", "audit"],
                         capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0
    d = json.loads(out.stdout)
    assert d["title"] == "aquatwin.audit/1"
