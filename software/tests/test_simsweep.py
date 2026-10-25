import pytest

from modkit import scenario as sn
from modkit import simsweep as sw

SCEN = __import__("pathlib").Path(__file__).resolve().parents[2] / "sim" / "scenarios"


def test_structure_and_bounds():
    r = sw.run_sweep(sn.load(SCEN / "nav_square.json"), n=6, seed=3)
    assert r["n"] == 6 and r["seed"] == 3
    assert 0 <= r["pass_rate"] <= 1
    assert r["error_mm"]["max"] >= r["error_mm"]["p50"] >= 0
    for run in r["runs"]:
        assert 0 <= run["params"]["slip"] <= 0.3
        assert 1.8 <= run["params"]["rated_torque"] <= 2.94


def test_deterministic_with_seed():
    a = sw.run_sweep(sn.load(SCEN / "nav_square.json"), n=5, seed=11)
    b = sw.run_sweep(sn.load(SCEN / "nav_square.json"), n=5, seed=11)
    assert [x["error_mm"] for x in a["runs"]] == [x["error_mm"] for x in b["runs"]]
    assert a["passed"] == b["passed"]


def test_bad_profile():
    with pytest.raises(ValueError):
        sw.run_sweep(sn.load(SCEN / "nav_square.json"), n=2, profile="nope")


def test_expected_pose_from_asserts():
    scene = {"assert": [{"path": "pose.x", "value": 10},
                        {"path": "pose.y", "value": -5}]}
    assert sw._expected_pose(scene) == (10.0, -5.0)
