"""Bring-up 证据：不伪造物理通过，pass 必须有可校验文件。"""

import pytest

from modkit import bringup as bu


def test_steps_unique_and_ordered():
    assert [s.n for s in bu.STEPS] == list(range(1, 12))
    assert len({s.key for s in bu.STEPS}) == 11
    assert set(bu.MILESTONES) == {"M1", "M2", "M3", "M4", "M5"}


def test_pass_requires_existing_evidence(tmp_path):
    c = bu.Commission(serial="M1-2026-0001", operator="tester")
    with pytest.raises(bu.BringupError):
        c.record(2, "pass")
    with pytest.raises(bu.BringupError):
        c.record(2, "pass", str(tmp_path / "missing.txt"))
    empty = tmp_path / "empty.txt"
    empty.write_text("")
    with pytest.raises(bu.BringupError):
        c.record(2, "pass", str(empty))


def test_record_pass_and_tamper(tmp_path):
    c = bu.Commission(serial="M1-2026-0001", operator="tester")
    ev = tmp_path / "scan.txt"
    ev.write_text("ID 1..6 ok\n")
    c.record(2, "pass", str(ev), "六轴")
    assert c.pass_count() == 1
    assert c.steps["2"].sha256
    assert c.validate() == []
    ev.write_text("tampered\n")
    assert any("sha256" in e for e in c.validate())


def test_simulated_never_counts_as_physical():
    c = bu.Commission.simulated()
    assert c.simulated_count() == 11
    assert c.pass_count() == 0
    assert c.physical_passed() == 0
    assert c.milestone("M1") == "simulated"
    assert any("simulated" in e for e in c.validate())


def test_milestone_needs_all_steps(tmp_path):
    c = bu.Commission(serial="M1-2026-0001", operator="tester")
    ev = tmp_path / "ok.txt"
    ev.write_text("ok")
    for n in (1, 2, 3, 8):
        c.record(n, "pass", str(ev))
    assert c.milestone("M1") == "pass"
    assert c.milestone("M2") == "pending"
    assert c.next_step().n == 4
