"""生产记录（qc.py）的测试：序列号、判据、汇总、指纹。"""

import json

import pytest

from modkit import qc


def make_good(serial="M1-2026-0001") -> qc.Record:
    q1, q2 = qc.default_checks()
    for c in q1 + q2:
        c.ok = True
    return qc.Record(
        serial=serial, operator="老王", q1=q1, q2=q2,
        grasp_success=9, grasp_total=10, repeatability_mm=1.2, temp_c=48.0,
        runtime_min=55.0, calibration_sha256="a" * 64, firmware_version="0.5.0",
        conclusion="合格",
    )


def test_serial_format():
    assert qc.SERIAL_RE.match("M1-2026-0001")
    assert not qc.SERIAL_RE.match("M1-26-1")
    assert not qc.SERIAL_RE.match("m1-2026-0001")


def test_next_serial_is_unique(tmp_path):
    s1 = qc.next_serial(tmp_path, year=2026)
    qc.Record(serial=s1, operator="a").save(tmp_path)
    s2 = qc.next_serial(tmp_path, year=2026)
    assert s1 != s2
    assert s2.endswith("0002")


def test_duplicate_serial_rejected(tmp_path):
    make_good().save(tmp_path)
    with pytest.raises(qc.QcError):
        make_good().save(tmp_path)


def test_good_record_passes():
    assert make_good().validate() == []


def test_failed_check_blocks_pass():
    r = make_good()
    r.q2[0].ok = False
    assert any("Q1" in e or "Q2" in e for e in r.validate())


def test_low_grasp_blocks_pass():
    r = make_good()
    r.grasp_success = 7
    assert any("抓放" in e for e in r.validate())


def test_over_temperature_blocks_pass():
    r = make_good()
    r.temp_c = 61.0
    assert any("温升" in e for e in r.validate())


def test_missing_fingerprint_blocks_pass():
    r = make_good()
    r.calibration_sha256 = ""
    assert any("标定" in e for e in r.validate())


def test_rework_record_can_skip_functional_checks():
    r = make_good()
    r.conclusion = "返修"
    r.grasp_success = 0
    assert r.validate() == []


def test_summary_yield(tmp_path):
    make_good("M1-2026-0001").save(tmp_path)
    bad = make_good("M1-2026-0002")
    bad.conclusion = "报废"
    bad.save(tmp_path)
    s = qc.summary([tmp_path / "M1-2026-0001.json", tmp_path / "M1-2026-0002.json"])
    assert s["total"] == 2 and s["pass"] == 1 and s["yield"] == 50.0


def test_sha256_file(tmp_path):
    p = tmp_path / "calib.json"
    p.write_text('{"a":1}', encoding="utf-8")
    assert len(qc.sha256_file(p)) == 64