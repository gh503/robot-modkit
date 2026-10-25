"""场景运行器：内置场景、断言失败、导航闭环、未知动作。"""

import pathlib

import pytest

from modkit import scenario

SCEN = pathlib.Path(__file__).resolve().parents[2] / "sim" / "scenarios"


@pytest.mark.parametrize("name", ["servo_hold", "low_battery", "slip", "weak_servo"])
def test_builtin_scenarios_pass(name):
    r = scenario.run_scenario(scenario.load(SCEN / f"{name}.json"))
    assert r["ok"], r["failures"]


def test_nav_square_in_hwsim():
    r = scenario.run_scenario(scenario.load(SCEN / "nav_square.json"))
    assert r["ok"], r["failures"]
    assert r["time"] < 30


def test_failing_assertion_reports():
    scene = {"actions": [], "assert": [
        {"path": "voltage", "value": 99, "tol": 1}]}
    r = scenario.run_scenario(scene)
    assert not r["ok"]
    assert "voltage" in r["failures"][0]


def test_unknown_action_raises():
    with pytest.raises(scenario.ScenarioError):
        scenario.run_scenario({"actions": [{"cmd": "fly"}]})


def test_set_slip():
    scene = {"actions": [
        {"cmd": "set", "path": "chassis.slip", "value": 1.0},
        {"cmd": "drive", "v": 100},
        {"cmd": "wait", "seconds": 0.5},
        {"cmd": "stop"},
    ], "assert": [{"path": "chassis.slip", "value": 1.0}]}
    assert scenario.run_scenario(scene)["ok"]


def test_mission_pick_full_stack():
    r = scenario.run_scenario(scenario.load(SCEN / "mission_pick.json"))
    assert r["ok"], r["failures"]
    assert r["time"] < 20


def test_mission_nav_full_stack():
    r = scenario.run_scenario(scenario.load(SCEN / "mission_nav.json"))
    assert r["ok"], r["failures"]
    assert r["time"] < 25
