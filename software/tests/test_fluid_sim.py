import json
import pathlib

import numpy as np
import pytest

from modkit import fluid as fl
from modkit import fluid_sim as fs


def test_dam_break_conserves_mass_and_moves():
    s = fs.dam_break(48, 24, 0.05, 0.2)
    v0 = s.volume
    for _ in range(160):
        s.step()
    m = s.metrics()
    assert m["t_s"] > 0
    assert m["max_speed_m_s"] > 0.1
    assert s.volume == pytest.approx(v0, rel=1e-12)
    assert m["volume_error_rel"] < 1e-12
    fr = s.frame()
    assert fr["nx"] == 48 and fr["ny"] == 24
    assert len(fr["height_m"]) == 24


def test_source_adds_volume_and_reports_error():
    s = fs.ShallowWater(fl.get("water"), nx=16, ny=12, dx=0.1, depth=0.1)
    s.sources.append(fs.Source(0.5, 0.5, 1e-4, 0.1))
    s.advance(1.0)
    m = s.metrics()
    assert m["injected_m3"] > 0
    assert m["volume_error_rel"] < 0.01


def test_tank_drains_and_records():
    t = fs.Tank(fl.get("water"), area_m2=1.0, height_m=1.0,
                outlet_area_m2=0.01, level_m=1.0)
    l0 = t.level_m
    t.advance(2.0, dt=0.01)
    assert t.level_m < l0
    assert t.metrics()["outflow_total_m3"] > 0
    assert t.metrics()["outlet_flow_m3_s"] > 0


def test_run_experiment_and_json(tmp_path):
    cfg = {"fluid": "water", "nx": 16, "ny": 12, "dx": 0.1, "depth": 0.1,
           "duration": 0.2, "frame_every": 2}
    r = fs.run_experiment(cfg)
    assert r["fluid"] == "water"
    assert len(r["frames"]) >= 1
    assert r["metrics"]["volume_error_rel"] < 1e-10
    p = tmp_path / "frame.json"
    s = fs.ShallowWater(fl.get("water"), nx=16, ny=12, dx=0.1, depth=0.1)
    s.to_json(p)
    d = json.loads(p.read_text())
    assert d["fluid"] == "water" and d["frame"]["nx"] == 16


def test_gas_and_invalid_config_rejected():
    with pytest.raises(fs.FluidSimError):
        fs.ShallowWater(fl.get("air"), nx=8, ny=8, dx=0.1, depth=0.1)
    with pytest.raises(fs.FluidSimError):
        fs.ShallowWater(fl.get("water"), nx=2, ny=2, dx=0.1, depth=0.1)
    with pytest.raises(fs.FluidSimError):
        fs.Tank(fl.get("water"), area_m2=0, height_m=1)
    with pytest.raises(fs.FluidSimError):
        fs.Tank(fl.get("water"), area_m2=1, height_m=1, level_m=2)


def test_cfl_clamps_large_dt():
    s = fs.ShallowWater(fl.get("water"), nx=16, ny=12, dx=0.1, depth=0.1)
    c = s.cfl_dt()
    got = s.step(c * 100)
    assert got <= c + 1e-12
