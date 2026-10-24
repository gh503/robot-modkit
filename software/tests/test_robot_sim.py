"""用仿真链路跑通上位机全流程（不需要硬件）。"""

from modkit import kinematics as kin
from modkit import protocol as p
from modkit.bus import SimLink
from modkit.cli import main
from modkit.robot import Robot


def test_scan_and_feedback():
    bot = Robot(SimLink([1, 2, 3, 4]))
    assert bot.scan() == [1, 2, 3, 4]
    fb = bot.feedback(1)
    assert abs(fb.position_deg - 180.0) < 0.1
    assert fb.voltage == 12.0


def test_goto_then_read():
    bot = Robot(SimLink([1]))
    bot.set_torque(1, True)
    bot.goto(1, 90.0)
    assert abs(bot.feedback(1).position_deg - 90.0) < 0.2


def test_sync_goto_is_broadcast_frame():
    link = SimLink([1, 2])
    bot = Robot(link)
    bot.sync_goto({1: 100.0, 2: 120.0})
    last = link.command_log[-1][1]
    assert last[2] == p.BROADCAST_ID
    assert last[4] == p.SYNC_WRITE
    assert last[-1] == p.checksum(last[2:-1])


def test_move_pose_lands_near_target():
    bot = Robot(SimLink([1, 2, 3]))
    pose = kin.Pose(150, 0, 150)
    yaw, sh, el = bot.move_pose(*pose.__dict__.values())
    back = kin.forward(bot.arm, yaw, sh, el)
    assert abs(back.x - 150) < 1.0 and abs(back.z - 150) < 1.0


def test_cli_scan_sim(capsys):
    assert main(["--sim", "scan"]) == 0
    out = capsys.readouterr().out
    assert "找到 6 个" in out


def test_cli_pose_unreachable(capsys):
    assert main(["--sim", "pose", "--x", "999", "--y", "0", "--z", "90"]) == 2
    assert "到不了" in capsys.readouterr().out
