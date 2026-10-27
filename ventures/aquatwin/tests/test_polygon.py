import pathlib

import pytest

from aquatwin import coverage, geometry, model
from aquatwin.scenario import ScenarioError, Study

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_l_shape_area_volume_and_coverage():
    s = Study.load(ROOT / "scenarios" / "l_shape_pool.json")
    assert s.pool.area_m2 == pytest.approx(24.0)
    assert s.pool.volume == pytest.approx(36.0)
    r = model.run(s)
    assert r["results"]["pool_volume_m3"] == pytest.approx(36.0)
    assert r["results"]["path_length_m"] > 0
    assert 0 < r["results"]["coverage_pct"] <= 100
    assert len(r["coverage"]["lane_segments"]) > 4
    assert r["results"]["turns"] >= len(r["coverage"]["lane_segments"]) - 1


def test_polygon_scanline_has_two_intervals_at_cutout():
    pts = [[0, 0], [8, 0], [8, 4], [4, 4], [4, 2], [0, 2]]
    assert geometry.scanline_intervals(pts, 1.0, 0, 8) == [(0.0, 8.0)]
    assert geometry.scanline_intervals(pts, 3.0, 0, 8) == [(4.0, 8.0)]


def test_polygon_invalid():
    p = Study.load(ROOT / "scenarios" / "residential_8x4.json").pool
    p.shape = "polygon"
    p.footprint = [[0, 0], [4, 0], [0, 1]]
    assert p.validate([]) is None  # dataclass method appends
    errs = []
    p.validate(errs)
    assert errs == []
    p.footprint = [[0, 0], [2, 2], [0, 2], [2, 0]]
    errs = []
    p.validate(errs)
    assert any("自交" in e for e in errs)
    p.footprint = None
    errs = []
    p.validate(errs)
    assert any("footprint" in e for e in errs)


def test_polygon_svg(tmp_path):
    s = Study.load(ROOT / "scenarios" / "l_shape_pool.json")
    c = coverage.plan(s.pool, s.robot)
    p = coverage.write_svg(c, s.pool, tmp_path / "l.svg")
    text = p.read_text(encoding="utf-8")
    assert "<polygon" in text and "L 形" not in text
    assert "svg" in text


def test_rect_regression():
    s = Study.load(ROOT / "scenarios" / "residential_8x4.json")
    c = coverage.plan(s.pool, s.robot)
    assert c.lanes == 10
    assert c.coverage_pct == pytest.approx(100.0)
    assert c.path_length_m == pytest.approx(10 * 8 + 9 * 0.405)
