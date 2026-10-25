import json
import math
import pathlib
import time

import pytest

from modkit import protocol as p
from modkit.bus import SimLink
from modkit.robot import Robot
from modkit.safety import DEFAULT_JOINTS, Health, JointLimit, SafetyPolicy


def bot(ids=(1, 2, 3, 4, 5, 6)):
    return Robot(SimLink(list(ids)))


def test_default_mapping_and_roundtrip():
    pol = SafetyPolicy.defaults()
    elbow = pol.joint("elbow")
    servo = elbow.to_servo_deg(-55)
    assert servo == pytest.approx(2048 * p.DEG_PER_TICK + 55, abs=0.1)
    assert elbow.from_servo_deg(servo) == pytest.approx(-55, abs=0.2)
    assert pol.joint("yaw").to_servo_deg(90) == pytest.approx(270, abs=0.1)
    assert pol.joint("gripper").to_servo_deg(0) == pytest.approx(120, abs=0.1)
    assert pol.joint("gripper").to_servo_deg(1) == pytest.approx(180, abs=0.1)


def test_target_bounds_and_step():
    pol = SafetyPolicy.defaults()
    assert pol.check_target("yaw", 120).ok
    assert not pol.check_target("yaw", 120.1).ok
    assert pol.check_target("shoulder", 35, current=0).ok
    assert not pol.check_target("shoulder", 50, current=0).ok
    assert not pol.check_target("nope", 0).ok
    assert not pol.check_target("yaw", float("nan")).ok


def test_health_thresholds():
    pol = SafetyPolicy.defaults()
    assert pol.check_health(Health(1, "yaw", True, 0, 12.0, 30, 0)).ok
    assert not pol.check_health(Health(1, "yaw", False)).ok
    assert not pol.check_health(Health(1, "yaw", True, 0, 12.0, 56, 0)).ok
    assert not pol.check_health(Health(1, "yaw", True, 0, 10.1, 30, 0)).ok
    assert not pol.check_health(Health(1, "yaw", True, 0, 12.0, 30, 0x04)).ok
    assert pol.check_health(Health(1, "yaw", True, 0, 10.5, 46, 0)).warnings
    stale = Health(1, "yaw", True, 0, 12.0, 30, 0, sampled_at=time.monotonic() - 2.0)
    assert not pol.check_health(stale).ok


def test_preflight_nominal_and_faults():
    r = bot()
    pol = SafetyPolicy.defaults()
    rep = pol.preflight(r, expected_ids=[1, 2, 3, 4, 5, 6], scan=True)
    assert rep.ok, rep.issues
    assert len(rep.health) == 6

    bad = bot()
    bad.link.mem[1][p.REG_PRESENT_VOLTAGE] = 100       # 10.0V
    rep = pol.preflight(bad, expected_ids=[1, 2, 3, 4], scan=False)
    assert not rep.ok
    assert any("电压" in x for x in rep.issues)

    bad2 = bot()
    bad2.link.mem[2][p.REG_STATUS] = 0x04
    rep = pol.preflight(bad2, expected_ids=[1, 2, 3, 4], scan=False)
    assert not rep.ok
    assert any("温度" in x for x in rep.issues)


def test_apply_limits_writes_registers():
    r = bot()
    pol = SafetyPolicy.defaults()
    pol.apply_limits(r, [1, 2, 3, 4])
    frames = [f for _, f in r.link.command_log]
    assert any(f[5] == p.REG_TORQUE_LIMIT and p.u16(f[6], f[7]) == 600 for f in frames)
    assert any(f[5] == p.REG_CURRENT_LIMIT and p.u16(f[6], f[7]) == 384 for f in frames)
    assert any(f[5] == p.REG_ACC and f[6] == 30 for f in frames)


def test_sync_checked_uses_correct_elbow_sign():
    r = bot()
    pol = SafetyPolicy.defaults()
    r.sync_goto_checked({"elbow": -55}, pol)
    ticks = r.link.mem[3][p.REG_PRESENT_POS] | (r.link.mem[3][p.REG_PRESENT_POS + 1] << 8)
    assert ticks == pytest.approx(2048 + 55 / p.DEG_PER_TICK, abs=2)


def test_guard_motion_rejects_step_and_bounds():
    r = bot()
    pol = SafetyPolicy.defaults()
    assert pol.guard_motion(r, {"shoulder": 35}).ok
    assert not pol.guard_motion(r, {"shoulder": 80}).ok
    assert not pol.guard_motion(r, {"elbow": 50}).ok


def test_goto_checked_no_command_on_reject():
    r = bot()
    pol = SafetyPolicy.defaults()
    with pytest.raises(ValueError, match="limit"):
        r.goto_checked("elbow", 30, pol)
    writes = [f for _, f in r.link.command_log if f[4] == p.WRITE]
    assert not any(f[5] == p.REG_GOAL_POS for f in writes)


def test_policy_save_load_and_calibration(tmp_path):
    pol = SafetyPolicy.defaults()
    path = tmp_path / "policy.json"
    pol.save(path)
    got = SafetyPolicy.load(path)
    assert got.joint("elbow").to_servo_deg(-55) == pytest.approx(235.0, abs=0.1)
    assert got.calibrated is False

    cal = {
        "robot": "modkit-m1", "created": "2026-10-25",
        "joints": {
            "yaw": {"name": "yaw", "servo_id": 1, "zero_ticks": 2100,
                     "dir": 1, "min_deg": -80, "max_deg": 80, "speed_unit": 1.0},
            "shoulder": {"name": "shoulder", "servo_id": 2, "zero_ticks": 2048,
                          "dir": 1, "min_deg": -20, "max_deg": 90, "speed_unit": 1.0},
            "elbow": {"name": "elbow", "servo_id": 3, "zero_ticks": 2048,
                       "dir": -1, "min_deg": -140, "max_deg": 0, "speed_unit": 1.0},
        },
    }
    cpath = tmp_path / "calibration.json"
    cpath.write_text(json.dumps(cal), encoding="utf-8")
    cp = SafetyPolicy.from_calibration(cpath)
    assert cp.calibrated
    assert cp.joint("yaw").min_value == -80
    assert cp.joint("yaw").zero_ticks == 2100
    assert cp.joint("yaw").to_servo_deg(0) == pytest.approx(2100 * p.DEG_PER_TICK)


def test_scene_safety_matches_python_defaults():
    root = pathlib.Path(__file__).resolve().parents[2]
    text = (root / "web" / "scene.js").read_text(encoding="utf-8")
    payload = text.split("=", 1)[1].strip().rstrip(";")
    scene = json.loads(payload)
    safe = scene["safety"]
    pol = SafetyPolicy.defaults()
    for name in ("yaw", "shoulder", "elbow", "gripper"):
        lo, hi = safe["limits"][name]
        assert (lo, hi) == (pol.joint(name).min_value, pol.joint(name).max_value)
        assert safe["max_step"][name] == pol.joint(name).max_step
    assert safe["temp_warn_c"] == pol.temp_warn_c
    assert safe["temp_max_c"] == pol.temp_max_c
    assert safe["voltage_min_v"] == pol.voltage_min_v
    assert safe["torque_limit"] == pol.torque_limit
    assert safe["current_limit"] == pol.current_limit
    assert safe["acc"] == pol.acc
    assert safe["speed"] == pol.speed


def test_cli_preflight_sim(capsys):
    from modkit import cli
    rc = cli.main(["--sim", "preflight", "--expect", "1,2,3,4,5,6"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "预检：PASS" in out


def test_jointlimit_validation():
    with pytest.raises(ValueError):
        JointLimit("x", 1, 1, 0)
    with pytest.raises(ValueError):
        JointLimit("x", 1, 0, 1, direction=0)
    with pytest.raises(ValueError):
        JointLimit("x", 1, 0, 1, zero_ticks=5000)
