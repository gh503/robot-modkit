"""导航控制器：直线、掉头、方形闭环、轮速换算。"""

import math

import pytest

from modkit import nav


def test_wrap():
    assert nav.wrap(190) == -170
    assert nav.wrap(-190) == 170
    assert nav.wrap(180) == 180
    assert nav.wrap(-180) == 180
    assert nav.wrap(0) == 0


def test_drive_straight():
    r = nav.drive_to(nav.Pose(), nav.Pose(300, 0, 0))
    assert r.ok
    assert r.error_mm < 10
    assert abs(r.final.y) < 1.0
    assert r.seconds > 1.0


def test_goal_behind_rotates_first():
    r = nav.drive_to(nav.Pose(), nav.Pose(-200, 0, 180), max_seconds=40)
    assert r.ok
    assert r.error_mm < 10
    # 先原地转：轨迹前几步位移应很小
    early = r.trace[1]
    assert math.hypot(early.x, early.y) < 5


def test_square_closes():
    legs, ok = nav.follow(nav.Pose(), nav.square_waypoints(300))
    assert ok and len(legs) == 4
    assert legs[-1].error_mm < 12
    assert legs[-1].error_deg < 5


def test_timeout_reports_failure():
    r = nav.drive_to(nav.Pose(), nav.Pose(5000, 0, 0), max_seconds=1.0)
    assert not r.ok
    assert r.error_mm > 100


def test_done_at_goal():
    v, w, done = nav.goto_step(nav.Pose(10, 10, 0), nav.Pose(10, 10, 0))
    assert done and v == 0 and w == 0


def test_wheel_speeds_straight_and_turn():
    left, right = nav.to_wheels(100, 0)
    assert left == pytest.approx(100) and right == pytest.approx(100)
    left, right = nav.to_wheels(0, 90)      # 逆时针：右轮快
    assert right > left
    assert left == pytest.approx(-right)


def test_heading_to():
    assert nav.Pose(0, 0, 0).heading_to(nav.Pose(0, 100, 0)) == pytest.approx(90)
    assert nav.Pose(0, 0, 0).heading_to(nav.Pose(-100, 0, 0)) == pytest.approx(180)
