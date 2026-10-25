import pytest

from modkit import envelope as env
from modkit import kinematics as kin


G = kin.ArmGeometry()


def test_nominal_pose_is_clear():
    assert env.check_pose(G, 0, 35, -55) == []
    assert env.check_pose(G, 90, 60, -70) == []


def test_table_clearance():
    # 肩向下、肘伸直，指尖会到桌面以下
    out = env.check_pose(G, 0, -80, 0)
    assert any("桌面" in x for x in out)


def test_base_clearance():
    # 臂收在立柱附近且高度很低
    out = env.check_pose(G, 0, 5, -130)
    assert any("底座" in x or "折叠" in x for x in out)


def test_yaw_and_shoulder_limits():
    out = env.check_pose(G, 130, 35, -55)
    assert any("偏航" in x for x in out)
    out = env.check_pose(G, 0, 120, -55)
    assert any("肩" in x for x in out)


def test_joint_target_checks():
    assert env.check_joint_target(G, "elbow", 10)
    assert not env.check_joint_target(G, "elbow", -50)
    assert env.check_joint_target(G, "yaw", 130)


def test_cli_envelope(capsys):
    from modkit import cli
    assert cli.main(["envelope", "--x", "100", "--y", "0", "--z", "120"]) == 0
    assert "包络：PASS" in capsys.readouterr().out
    assert cli.main(["envelope", "--x", "100", "--y", "0", "--z", "10"]) == 2
    assert "包络：BLOCK" in capsys.readouterr().out


def test_robot_move_pose_checked_rejects_geometry():
    from modkit.bus import SimLink
    from modkit.robot import Robot
    from modkit.safety import SafetyPolicy

    r = Robot(SimLink([1, 2, 3, 4, 5, 6]))
    pol = SafetyPolicy.defaults()
    # 先把单步放宽，专测几何包络，而不是角度跳变
    for j in pol.joints.values():
        object.__setattr__(j, "max_step", 500.0)
    with pytest.raises(ValueError, match="几何包络"):
        r.move_pose_checked(100, 0, 10, pol)
    with pytest.raises(kin.UnreachableError):
        r.move_pose_checked(500, 0, 150, pol)
