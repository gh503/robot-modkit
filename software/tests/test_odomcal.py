"""里程计标定：轮径与轮距必须能从一次实测反推回来。"""

import math

import pytest

from modkit import kinematics as kin
from modkit import odomcal as oc


def test_straight_scale_and_geometry():
    cal = oc.OdomCal()                     # 65mm 轮
    ticks = 20000                          # 约 1m
    pred = cal.predicted_distance(ticks)
    assert 900 < pred < 1050
    sc = cal.apply_straight(ticks, 1000.0)
    assert abs(sc - 1000.0 / pred) < 1e-9
    assert abs(cal.predicted_distance(ticks) - 1000.0) < 1e-6   # 标定后应正好
    assert cal.geometry().wheel_r == cal.wheel_r_mm


def test_turn_scale_restores_90_deg():
    cal = oc.OdomCal()
    # 原地转 90°：差速 = track × θ → 每轮 ±(track/2)·θ
    theta = math.radians(90)
    arc = cal.track_mm * theta / 2
    ticks = arc / (2 * math.pi * cal.wheel_r_mm / cal.ticks_per_rev)
    cal.apply_turn(-ticks, ticks, 90.0)
    # 用新轮距重算，应回到 90°
    arc2 = (ticks - (-ticks)) * 2 * math.pi * cal.wheel_r_mm / cal.ticks_per_rev / 2
    deg = math.degrees(arc2 / (cal.track_mm / 2))
    assert abs(deg - 90.0) < 1e-6


def test_zero_ticks_rejected():
    with pytest.raises(oc.OdomCalError):
        oc.OdomCal().apply_straight(0, 1000)


def test_zero_distance_rejected():
    with pytest.raises(oc.OdomCalError):
        oc.OdomCal().apply_straight(1000, 0)


def test_no_differential_rejected():
    with pytest.raises(oc.OdomCalError):
        oc.OdomCal().apply_turn(100, 100, 90)


def test_save_load_roundtrip(tmp_path):
    cal = oc.OdomCal()
    cal.apply_straight(20000, 980.0)
    p = cal.save(tmp_path / "oc.json")
    again = oc.OdomCal.load(p)
    assert abs(again.wheel_r_mm - cal.wheel_r_mm) < 1e-9
    assert "轮半径" in again.summary()


def test_calibrated_odometry_matches_measured(tmp_path):
    """标定后直行 1m，里程计读数应接近 1000mm。"""
    cal = oc.OdomCal()
    cal.apply_straight(20000, 1000.0)
    g = cal.geometry()
    st = kin.OdomState()
    # 按 50Hz 分段读：一次跳 20000 格会超过半圈，滚动计数无法判断方向
    for i in range(1, 21):
        t = 1000 * i
        st = kin.update_odom(g, st, t, t)
    assert abs(st.x - 1000.0) < 1.0
