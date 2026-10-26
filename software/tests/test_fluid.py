import json
import math
import pathlib

import pytest

from modkit import cli, fluid as fl


def test_library_properties_and_units():
    assert len(fl.FLUIDS) >= 15
    w = fl.get("water")
    assert 990 < w.density < 1010
    assert 0.0005 < w.viscosity < 0.002
    assert w.kinematic_viscosity == pytest.approx(w.viscosity / w.density)
    assert not w.is_gas and w.is_newtonian
    assert fl.get("air").is_gas
    assert fl.get("latex_paint").is_bingham
    for f in fl.list_fluids():
        assert f.density > 0 and f.viscosity > 0
        assert 0 <= f.opacity <= 1
        assert f.category in ("water", "oil", "gas", "solution", "food", "slurry", "foam")


def test_temperature_and_salinity_are_approximations():
    w = fl.get("water")
    hot = w.at_temperature(40)
    cold = w.at_temperature(5)
    assert hot.viscosity < w.viscosity < cold.viscosity
    assert hot.density < w.density < cold.density
    sea = w.at_salinity(35)
    assert sea.density > w.density
    assert sea.viscosity > w.viscosity
    with pytest.raises(fl.FluidError):
        w.at_salinity(400)
    with pytest.raises(fl.FluidError):
        fl.get("unobtanium")


def test_custom_fluid_file_and_registry(tmp_path):
    p = tmp_path / "brine.json"
    p.write_text(json.dumps({"key": "test_brine", "name": "试验盐水", "name_en": "Test brine",
                             "category": "water", "density": 1100, "viscosity": 0.0015,
                             "surface_tension": 0.07}), encoding="utf-8")
    rows = fl.load_file(p)
    assert rows[0].key == "test_brine"
    assert fl.get("test_brine").density == 1100
    try:
        with pytest.raises(fl.FluidError):
            fl.load_file(p)
    finally:
        fl.FLUIDS.pop("test_brine", None)


def test_pipe_pump_and_drag():
    w = fl.get("water")
    r = fl.pipe_drop(w, 1e-3, 0.02, 5.0)
    assert r["regime"] == "turbulent"
    assert r["reynolds"] > 2300
    assert r["dp_total_pa"] > 0
    lam = fl.pipe_drop(w, 1e-6, 0.02, 5.0)
    assert lam["regime"] == "laminar"
    assert lam["friction_factor"] == pytest.approx(64 / lam["reynolds"])
    p = fl.pump_power(w, 1e-3, 3.0, 0.6)
    assert p["shaft_w"] > p["hydraulic_w"]
    assert fl.drag_force(w, 1.0, 0.5) > 0
    assert fl.buoyant_force(w, 0.001) > 0
    assert fl.jet_force(w, 1e-3, 2.0) > 0


def test_tank_and_terminal_velocity():
    w = fl.get("water")
    t = fl.tank_drain_time(1.0, 0.01, 0.5, w)
    assert t == pytest.approx((1.0 / (0.62 * 0.01)) * math.sqrt(2 * 0.5 / fl.G), rel=1e-12)
    v = fl.terminal_velocity(w, 0.001, 2500)
    assert 0 < v < 1.0
    assert fl.terminal_velocity(w, 0.001, 900) == pytest.approx(0.0, abs=1e-9)
    non = fl.pipe_drop(fl.get("latex_paint"), 1e-4, 0.05, 2.0)
    assert "非牛顿" in non["warning"]


def test_fluid_cli(capsys):
    assert cli.main(["fluid", "list"]) == 0
    out = capsys.readouterr().out
    assert "water" in out and "seawater" in out
    assert cli.main(["fluid", "show", "water", "--temp", "30", "--json"]) == 0
    assert '"density_kg_m3"' in capsys.readouterr().out
    assert cli.main(["fluid", "pipe", "--fluid", "water", "--flow", "0.001",
                     "--diameter", "0.02", "--length", "5"]) == 0
    assert "kPa" in capsys.readouterr().out
    assert cli.main(["fluid", "tank", "--fluid", "water", "--area", "1",
                     "--height", "1", "--seconds", "1"]) == 0
    assert "液位" in capsys.readouterr().out
