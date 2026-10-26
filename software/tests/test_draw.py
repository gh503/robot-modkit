"""绘图路径：3DOF 方/圆/三角、2DOF 圆弧、CSV/SVG、仿真回放。"""
from __future__ import annotations

import csv
import io
import json
import pathlib

import pytest

from modkit import cli
from modkit import draw

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_square_path_reachable_and_continuous():
    pts = draw.build_path("square", step=5, z=150)
    st = draw.stats(pts)
    assert len(pts) == 81
    assert st["mode"] == "arm" and st["elbow_used"]
    assert st["x"] == [100.0, 200.0] and st["y"] == [-50.0, 50.0]
    assert st["z"] == [150.0, 150.0]
    assert st["path_mm"] == pytest.approx(400.0)
    assert st["max_step_ok"]
    assert all(p.elbow is not None for p in pts)
    assert pts[0].x == pts[-1].x and pts[0].y == pts[-1].y


def test_circle_triangle_and_unreachable():
    circle = draw.build_path("circle", radius=50, step=5, z=150)
    assert circle[0].x == pytest.approx(circle[-1].x, abs=0.2)
    tri = draw.build_path("triangle", step=5, z=150)
    assert len(tri) > 30 and tri[0].x == tri[0].x
    with pytest.raises(draw.DrawError):
        draw.build_path("square", z=300, step=5)


def test_polar_arc_respects_yaw_limit():
    pts = draw.build_path("arc", mode="polar", radius=150, sweep=240, l1=175, step=5)
    assert len(pts) == 127
    assert all(p.elbow is None for p in pts)
    assert min(p.yaw for p in pts) == pytest.approx(-120.0)
    assert max(p.yaw for p in pts) == pytest.approx(120.0)
    assert draw.stats(pts)["elbow_used"] is False
    with pytest.raises(draw.DrawError):
        draw.build_path("arc", mode="polar", radius=150, sweep=241, l1=175)
    with pytest.raises(draw.DrawError):
        draw.build_path("arc", mode="polar", radius=200, sweep=100, l1=175)


def test_csv_svg_and_cli(tmp_path):
    pts = draw.build_path("square", step=25, z=150)
    csv_text = draw.to_csv(pts)
    rows = list(csv.reader(io.StringIO(csv_text.lstrip("\ufeff"))))
    assert rows[0][0] == "i" and len(rows) == len(pts) + 1
    assert rows[1][1] == "100.00" and rows[1][3] == "150.00"
    svg = draw.to_svg(pts)
    assert "<polyline" in svg and "start" in svg and "end" in svg

    out = tmp_path / "draw.csv"
    svg_out = tmp_path / "draw.svg"
    code = cli.main(["draw", "--shape", "square", "--step", "25",
                     "--out", str(out), "--svg", str(svg_out), "--json"])
    assert code == 0
    assert out.is_file() and svg_out.is_file()


def test_play_sim_arm_and_polar_guard():
    arm = draw.build_path("square", step=25, z=150)
    r = draw.play(arm, sim=True, settle=0)
    assert r["played"] == len(arm) and r["ids"] == [1, 2, 3]
    polar = draw.build_path("arc", mode="polar", radius=150, sweep=240, l1=175, step=20)
    r2 = draw.play(polar, sim=True, settle=0)
    assert r2["played"] == len(polar) and r2["ids"] == [1, 2]
    with pytest.raises(draw.DrawError):
        draw.play(arm, sim=False)
    with pytest.raises(draw.DrawError):
        draw.play(arm, sim=False, port="/dev/null")
