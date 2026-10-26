"""阶段化 bring-up：步骤数、证据、sha256、仿真不计入物理。"""
from __future__ import annotations

import json
import pathlib

import pytest

from modkit import cli
from modkit import stage

ROOT = pathlib.Path(__file__).resolve().parents[2]
A = ROOT / "assemblies"


def test_plan_follows_assembly_capability():
    cases = {"bench_joint": ("joint", 6), "bench_arm": ("arm", 9),
             "rover_base": ("drive", 8), "m1_pen": ("mobile-draw", 12)}
    for name, (key, n) in cases.items():
        rec = stage.init_record(A / f"{name}.json", "S-001", "tester")
        assert rec.stage == key
        assert len(rec.plan) == n
        assert rec.pass_count() == 0
        assert rec.steps["1"].status == "pending"


def test_record_requires_real_evidence(tmp_path):
    rec = stage.init_record(A / "bench_joint.json", "S-001", "tester")
    with pytest.raises(stage.StageError):
        rec.record(2, "pass")
    with pytest.raises(stage.StageError):
        rec.record(2, "pass", str(tmp_path / "missing.txt"))
    ev = tmp_path / "scan.txt"
    ev.write_text("ID 1 pong\n", encoding="utf-8")
    r = rec.record(2, "pass", str(ev), "扫描通过")
    assert r.status == "pass" and len(r.sha256) == 64
    assert rec.pass_count() == 1
    assert rec.next_step()["n"] == 1


def test_simulated_never_counts_as_physical(tmp_path):
    rec = stage.init_record(A / "bench_joint.json", "S-001", "tester")
    rec.record(1, "simulated", note="只做了仿真")
    assert rec.simulated_count() == 1
    errs = rec.validate()
    assert any("simulated" in e for e in errs)
    assert rec.pass_count() == 0


def test_sha256_tamper_detected(tmp_path):
    ev = tmp_path / "video.mp4"
    ev.write_bytes(b"first")
    rec = stage.init_record(A / "bench_joint.json", "S-001", "tester")
    rec.record(1, "pass", str(ev))
    assert rec.validate() == []
    ev.write_bytes(b"changed")
    assert any("sha256" in e for e in rec.validate())


def test_cli_init_record_status(tmp_path):
    f = tmp_path / "stage.json"
    ev = tmp_path / "e.txt"
    ev.write_text("ok", encoding="utf-8")
    assert cli.main(["stage", "--action", "init", "--assembly", str(A / "rover_base.json"),
                     "--serial", "S-9", "--operator", "tester", "--file", str(f)]) == 0
    assert f.is_file()
    assert cli.main(["stage", "--action", "record", "--file", str(f),
                     "--step", "1", "--result", "pass", "--evidence", str(ev)]) == 0
    assert cli.main(["stage", "--action", "status", "--file", str(f), "--json"]) == 0
    d = json.loads(f.read_text(encoding="utf-8"))
    assert d["stage"] == "drive" and d["steps"]["1"]["status"] == "pass"
