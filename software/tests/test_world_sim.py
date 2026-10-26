import json
import pathlib

import pytest

from modkit import fluid as fl
from modkit import world as wd
from modkit import world_sim as ws


def test_pool_run_is_deterministic_and_conserves():
    w = wd.from_preset("pool")
    a = ws.run_world(w, duration=0.3, dx=0.5, frame_every=2)
    b = ws.run_world(w, duration=0.3, dx=0.5, frame_every=2)
    ma = a["fluids"]["water"]["metrics"]
    mb = b["fluids"]["water"]["metrics"]
    assert ma["volume_m3"] == pytest.approx(38.4, rel=1e-6)
    assert ma["volume_error_rel"] < 1e-8
    assert ma["volume_m3"] == pytest.approx(mb["volume_m3"], rel=1e-12)
    assert len(a["fluids"]["water"]["frames"]) >= 1
    assert a["sensors"]["level"]["value"] == pytest.approx(1.2)
    assert a["sensors"]["temp"]["value"] == 26
    assert a["sensors"]["turb"]["modeled"] is False


def test_tank_and_pipe_and_robot():
    w = wd.from_preset("pipeline")
    w.metadata["robot"] = {"area_m2": 0.12, "volume_m3": 0.004, "speed_m_s": 0.4}
    r = ws.run_world(w, duration=0.2, dx=0.5)
    pipe = r["fluids"]["water"]
    assert pipe["velocity_m_s"] > 0
    assert pipe["dp_total_pa"] > 0
    assert r["robot"]["drag_n"] > 0
    assert r["robot"]["buoyancy_n"] > 0
    assert r["sensors"]["flow"]["value"] == pytest.approx(0.002)

    w = wd.from_preset("lab")
    r = ws.run_world(w, duration=0.5, dx=0.2)
    tank = r["fluids"]["water"]
    assert tank["type"] == "tank"
    assert tank["metrics"]["level_m"] < 0.28
    assert len(tank["levels"]) >= 1


def test_world_run_outputs(tmp_path):
    w = wd.from_preset("pool")
    result = ws.run_world(w, duration=0.2, dx=0.5, out=str(tmp_path))
    paths = result["outputs"]
    for k in ("metrics", "frames", "sensors", "report"):
        assert pathlib.Path(paths[k]).is_file(), k
    d = json.loads((tmp_path / "metrics.json").read_text(encoding="utf-8"))
    assert d["world"] == w.name
    assert "water" in d["fluids"]
    assert "shallow water" in (tmp_path / "report.md").read_text(encoding="utf-8")


def test_world_invalid_does_not_run():
    w = wd.from_preset("pool")
    w.fluids[0].level = 2.0
    with pytest.raises(Exception):
        ws.run_world(w, duration=0.1)
