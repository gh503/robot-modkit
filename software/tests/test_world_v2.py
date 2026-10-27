import math
import pathlib

import pytest

from modkit import world as wd
from modkit import world_sim as ws

ROOT = pathlib.Path(__file__).resolve().parents[2]


def l_world():
    w = wd.World("L 形池", environment="pool")
    w.add(wd.WorldObject("floor", "box", "地坪", [0, 0, 0], [0, 0, 0],
                         [10, 6, 0.1], semantic="floor"))
    w.add_fluid(wd.FluidBody(
        "water", "pool", "water", "池水", [0, 0, 0.1], [8, 4, 1.5],
        footprint=[[-4, -2], [4, -2], [4, 2], [0, 2], [0, 0], [-4, 0]],
        level=0.8, temperature_c=26))
    return w


def test_schema_v2_and_v1_migration():
    w = wd.from_preset("pool")
    assert w.schema == wd.SCHEMA == "modkit.world/2"
    old = w.to_dict()
    old["schema"] = wd.SCHEMA_V1
    old["metadata"] = {}
    m = wd.World.from_dict(old)
    assert m.schema == wd.SCHEMA
    assert m.metadata["migrated_from"] == wd.SCHEMA_V1
    assert m.validate()["ok"]
    bad = dict(old, schema="modkit.world/999")
    with pytest.raises(wd.WorldError):
        wd.World.from_dict(bad)


def test_polygon_pool_capacity_volume_and_validation():
    w = l_world()
    v = w.validate()
    assert v["ok"], v
    f = w.fluids[0]
    assert f.capacity_m3 == pytest.approx(24 * 1.5)
    assert f.volume == pytest.approx(24 * 1.5 * 0.8)
    assert f.depth_m == pytest.approx(1.2)
    assert w.summary()["water_volume_m3"] == pytest.approx(f.volume)
    f.footprint = [[-5, 0], [0, 0], [0, 1]]
    assert not w.validate()["ok"]
    f.footprint = [[0, 0], [1, 1], [0, 1], [1, 0]]
    assert not w.validate()["ok"]


def test_heightfield_data_validation_and_roundtrip(tmp_path):
    w = wd.from_preset("outdoor")
    hf = wd.WorldObject("terrain", "heightfield", "地形", [0, 0, 0], [0, 0, 0],
                        [12, 8, 3], source="", heights=[[0, 0.2], [0.1, 0.3]])
    w.add(hf)
    assert w.validate()["ok"]
    p = tmp_path / "hf.json"
    w.save(p)
    again = wd.World.load(p)
    assert again.object("terrain").heights == [[0, 0.2], [0.1, 0.3]]
    again.object("terrain").heights = [[0, float("nan")]]
    assert not again.validate()["ok"]
    again.object("terrain").heights = None
    again.object("terrain").source = ""
    assert not again.validate()["ok"]


def test_shallow_mask_conserves_volume_and_limits_wet_cells():
    w = l_world()
    r = ws.run_world(w, duration=0.15, dt=0.01, dx=0.5, frame_every=3)
    f = r["fluids"]["water"]
    assert f["footprint"]
    m = f["metrics"]
    assert m["wet_cells"] < m["cells"]
    assert m["volume_error_rel"] < 0.25
    assert m["max_depth_m"] > 0


def test_depth_average_preserves_polygon_volume():
    w = l_world()
    r = ws.run_world(w, duration=0.05, dt=0.01, dx=0.5, frame_every=10)
    m = r["fluids"]["water"]["metrics"]
    # 初始体积按多边形面积反推，误差来自掩膜离散；不应出现数量级错误
    assert m["initial_volume_m3"] == pytest.approx(28.8, rel=0.35)


def test_world_editor_markup_and_js_contract():
    root = ROOT / "web"
    html = (root / "world.html").read_text(encoding="utf-8")
    js = (root / "world.js").read_text(encoding="utf-8")
    for need in ("object", "obj-x", "obj-sx", "add-box", "undo", "redo",
                 "share", "save-local", "load-local"):
        assert f'id="{need}"' in html
    for token in ("function addBox", "function undo", "function shareLink",
                  "function heightfieldMesh", "ExtrudeGeometry", "modkit.world/2"):
        assert token in js
    assert "modkit.world/1" in js  # 只用于迁移
