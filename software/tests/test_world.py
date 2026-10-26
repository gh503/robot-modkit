import json
import pathlib

import pytest

from modkit import cli, world as wd

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_all_presets_validate_and_roundtrip(tmp_path):
    assert len(wd.presets()) == 8
    for key in wd.presets():
        w = wd.from_preset(key)
        v = w.validate()
        assert v["ok"], (key, v["errors"])
        assert len(w.objects) >= 2
        assert len(w.fluids) >= 1
        for f in w.fluids:
            assert f.volume >= 0
            assert f.volume <= f.capacity_m3 * 1.001
        p = tmp_path / f"{key}.json"
        w.save(p)
        again = wd.World.load(p)
        assert again.name == w.name
        assert len(again.objects) == len(w.objects)
        assert again.validate()["ok"]


def test_pool_volume_and_surface():
    w = wd.from_preset("pool")
    f = w.fluids[0]
    assert f.type == "pool"
    assert f.volume == pytest.approx(8 * 4 * 1.5 * 0.8)
    assert f.depth_m == pytest.approx(1.2)
    assert f.surface_z < 1.6 + 1e-6
    assert w.summary()["water_volume_m3"] == pytest.approx(f.volume)


def test_invalid_worlds_are_rejected():
    w = wd.from_preset("lab")
    w.fluids[0].level = 1.5
    assert not w.validate()["ok"]
    w = wd.from_preset("lab")
    w.fluids[0].fluid = "nope"
    assert not w.validate()["ok"]
    w = wd.from_preset("lab")
    w.objects.append(w.objects[0])
    assert not w.validate()["ok"]
    w = wd.World("bad")
    w.add(wd.WorldObject("m", "mesh", "mesh", [0, 0, 0], [0, 0, 0], [1, 1, 1]))
    assert not w.validate()["ok"]


def test_custom_fluid_is_registered():
    w = wd.from_preset("lab")
    w.custom_fluids = [{"key": "test_brine_world", "name": "试验盐水",
                        "name_en": "Test brine", "category": "water",
                        "density": 1100, "viscosity": 0.0015}]
    w.fluids[0].fluid = "test_brine_world"
    assert w.validate()["ok"]
    from modkit import fluid as fl
    assert fl.get("test_brine_world").density == 1100
    fl.FLUIDS.pop("test_brine_world", None)


def test_cli_world_list_init_validate_summary(tmp_path, capsys):
    assert cli.main(["world", "list"]) == 0
    assert "pool" in capsys.readouterr().out
    p = tmp_path / "pool.json"
    assert cli.main(["world", "init", "--preset", "pool", "--out", str(p)]) == 0
    assert p.is_file()
    assert cli.main(["world", "validate", "--file", str(p)]) == 0
    assert "PASS" in capsys.readouterr().out
    assert cli.main(["world", "summary", "--file", str(p), "--json"]) == 0
    assert '"water_volume_m3"' in capsys.readouterr().out


def test_web_world_data_is_valid():
    files = sorted((ROOT / "web" / "data").glob("world-*.json"))
    assert len(files) == 8
    for p in files:
        w = wd.World.load(p)
        v = w.validate()
        assert v["ok"], (p.name, v["errors"])
        assert w.environment in wd.presets()
