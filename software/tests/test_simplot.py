"""调试图：有 trace 能出 PNG，空 trace 明确报错。"""

import pathlib

import pytest

pytest.importorskip("matplotlib")

from modkit import scenario, simplot

SCEN = pathlib.Path(__file__).resolve().parents[2] / "sim" / "scenarios"


def test_plot_written(tmp_path):
    r = scenario.run_scenario(scenario.load(SCEN / "servo_hold.json"))
    assert r["trace"]
    out = simplot.plot(r, tmp_path / "hold.png")
    assert out.stat().st_size > 5000


def test_empty_trace_rejected(tmp_path):
    with pytest.raises(ValueError):
        simplot.plot({"trace": []}, tmp_path / "x.png")
