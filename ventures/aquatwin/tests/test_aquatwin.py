import json
import pathlib

import pytest

from aquatwin import cli, coverage, model, report
from aquatwin.scenario import Economics, Filter, Pool, Robot, ScenarioError, Study

ROOT = pathlib.Path(__file__).resolve().parents[1]


def base():
    return Study(name="测试池", description="unit",
                 pool=Pool(length_m=8, width_m=4, depth_m=1.5),
                 robot=Robot(), filter=Filter(), economics=Economics())


def test_scenario_roundtrip_and_defaults(tmp_path):
    s = base()
    assert s.pool.volume == pytest.approx(48.0)
    v = s.validate()
    assert v["ok"], v
    p = s.save(tmp_path / "s.json")
    again = Study.load(p)
    assert again.name == s.name
    assert again.robot.swath_m == s.robot.swath_m
    assert again.to_dict()["schema"] == "aquatwin.study/1"


def test_validation_rejects_bad_values():
    s = base()
    s.pool.length_m = 0
    assert not s.validate()["ok"]
    s = base()
    s.robot.overlap = 0.9
    assert not s.validate()["ok"]
    s = base()
    s.economics.robot_life_years = 0
    assert not s.validate()["ok"]
    with pytest.raises(ScenarioError):
        Study.from_dict({"name": "x", "pool": {"unknown": 1}})


def test_coverage_is_complete_and_deterministic():
    s = base()
    a = coverage.plan(s.pool, s.robot)
    b = coverage.plan(s.pool, s.robot)
    assert a.lanes == b.lanes
    assert a.coverage_pct == pytest.approx(100.0)
    assert a.path_length_m > s.pool.length_m
    assert len(a.lane_segments) == a.lanes
    assert a.turns == a.lanes - 1


def test_run_mass_energy_and_cost():
    s = base()
    r = model.run(s)["results"]
    assert r["pool_volume_m3"] == pytest.approx(48.0)
    assert r["coverage_pct"] == pytest.approx(100.0)
    assert r["total_power_w"] > r["pump_shaft_w"]
    assert r["energy_wh"] > 0
    assert r["cost_per_cleaning_cny"] > r["operating_cost_cny"]
    assert r["manual_cost_cny"] == pytest.approx(1.5 * 60 + 20)
    assert r["savings_per_cleaning_cny"] == pytest.approx(r["manual_cost_cny"] - r["operating_cost_cny"])
    assert r["annual_cleanings"] == pytest.approx(260)


def test_more_speed_less_time():
    s = base()
    t0 = model.run(s)["results"]["total_time_min"]
    s.robot.speed_m_s *= 1.5
    t1 = model.run(s)["results"]["total_time_min"]
    assert t1 < t0
    a = model.run(base())
    b = model.run(base())
    assert a["results"] == b["results"]


def test_filter_warning_and_sensitivity():
    s = base()
    s.pool.debris_g_m3 = 50
    s.filter.capacity_g = 20
    r = model.run(s)
    assert r["results"]["filter_cycles"] > 1
    assert any("过滤压升" in w for w in r["warnings"])
    rows = model.sensitivity(s)
    assert len(rows) == 7
    assert sum(1 for x in rows if x["variant"] == "基准") == 1


def test_cli_outputs(tmp_path, capsys):
    out = tmp_path / "study"
    rc = cli.main(["study", "--scenario", str(ROOT / "scenarios" / "residential_8x4.json"),
                   "--out", str(out)])
    assert rc == 0
    text = capsys.readouterr().out
    assert "住宅泳池" in text and "回收期" in text
    for name in ("metrics.json", "report.md", "coverage.csv", "coverage.svg", "dashboard.html"):
        assert (out / name).is_file(), name
    assert "不是实测" in (out / "report.md").read_text(encoding="utf-8")
    d = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    assert d["schema"] == "aquatwin.result/1"
    assert d["results"]["coverage_pct"] == pytest.approx(100.0)


def test_cli_validate_roi_new(tmp_path, capsys):
    assert cli.main(["validate", "--scenario", str(ROOT / "scenarios" / "small_6x3.json")]) == 0
    assert "PASS" in capsys.readouterr().out
    assert cli.main(["roi", "--scenario", str(ROOT / "scenarios" / "small_6x3.json"), "--json"]) == 0
    assert '"roi_1y_pct"' in capsys.readouterr().out
    p = tmp_path / "new.json"
    assert cli.main(["new", "--out", str(p)]) == 0
    assert Study.load(p).name == "新泳池研究"


def test_dashboard_is_self_contained(tmp_path):
    s = base()
    result = model.run(s)
    paths = report.write(s, result, tmp_path)
    html = pathlib.Path(paths["dashboard"]).read_text(encoding="utf-8")
    assert "AquaTwin" in html
    assert "http://" not in html and "https://" not in html
    assert "不是现场实测" in html
