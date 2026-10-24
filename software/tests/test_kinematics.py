"""运动学测试：先让数学自洽，再让电机动。

覆盖三件最容易出错的事：
  1. 正解→逆解→正解的往返一致（数值精度）；
  2. 工作空间外必须抛错，而不是返回一个"看起来能用"的角度；
  3. 里程计：直线与原地旋转的解析解。
"""

import math

import pytest

from modkit import kinematics as kin


def test_forward_ik_roundtrip():
    geom = kin.ArmGeometry()
    cases = [
        (0, 0, 0), (0, 30, -20), (45, 60, -60), (-60, 20, -90),
        (90, 80, -30), (-90, 45, -100),
    ]
    for yaw, sh, el in cases:
        pose = kin.forward(geom, yaw, sh, el)
        y2, s2, e2 = kin.inverse(geom, pose, elbow_up=el > 0)
        p2 = kin.forward(geom, y2, s2, e2)
        assert math.dist((pose.x, pose.y, pose.z), (p2.x, p2.y, p2.z)) < 0.5, (yaw, sh, el)


def test_ik_rejects_out_of_reach():
    geom = kin.ArmGeometry()
    with pytest.raises(kin.UnreachableError):
        kin.inverse(geom, kin.Pose(500, 0, 90))     # 太远
    with pytest.raises(kin.UnreachableError):
        kin.inverse(geom, kin.Pose(0, 0, 0))        # 太近 + 低于肩


def test_ik_rejects_yaw_limit():
    geom = kin.ArmGeometry()
    with pytest.raises(kin.UnreachableError):
        kin.inverse(geom, kin.Pose(-100, 120, 120))  # 偏航 > 120°


def test_joint_ticks_roundtrip():
    geom = kin.ArmGeometry()
    t = kin.joint_ticks(geom, 30, 45, -60)
    y, s, e = kin.ticks_to_joints(*t)
    assert abs(y - 30) < 0.5 and abs(s - 45) < 0.5 and abs(e + 60) < 0.5


def test_odometry_straight_line():
    g = kin.DriveGeometry()
    st = kin.OdomState()
    per_rev = g.ticks_per_rev
    st = kin.update_odom(g, st, per_rev, per_rev)     # 两边各转一圈
    assert abs(st.yaw) < 1e-6
    assert abs(st.x - 2 * math.pi * g.wheel_r) < 0.5
    assert abs(st.y) < 0.5


def test_odometry_spin_in_place():
    g = kin.DriveGeometry()
    st = kin.OdomState()
    st = kin.update_odom(g, st, 1024, -1024)          # 左轮前进、右轮后退 = 顺时针
    expected = -math.degrees((2 * 1024 * g.mm_per_tick) / g.track)
    assert abs(st.yaw - expected) < 0.5
    assert abs(st.x) < 1e-6


def test_wheel_speeds():
    g = kin.DriveGeometry()
    left, right = kin.wheel_speeds(100.0, 0.0, g)
    assert left == right == 100.0
    left, right = kin.wheel_speeds(0.0, 90.0, g)      # 逆时针：右轮快
    assert right > 0 > left
