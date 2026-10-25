"""硬件仿真：到位、下垂、低压、丢帧、编码器、打滑。"""

import pytest

from modkit import protocol as p
from modkit.bus import RetryLink
from modkit.hwsim import BatterySpec, HardwareSim, ServoSpec
from modkit.robot import Robot


def run(sim, seconds, dt=0.002):
    for _ in range(int(seconds / dt)):
        sim.step(dt)


def test_servo_reaches_target():
    sim = HardwareSim()
    bot = Robot(sim)
    bot.set_torque(2, True)
    bot.goto(2, 210, speed=500)
    run(sim, 1.0)
    assert sim.joint_deg(2) == pytest.approx(210, abs=1.0)


def test_torque_off_falls():
    sim = HardwareSim()
    bot = Robot(sim)
    bot.set_torque(2, True)
    bot.goto(2, 220, speed=500)
    run(sim, 1.0)
    high = sim.joint_deg(2)
    bot.set_torque(2, False)
    run(sim, 1.5)
    assert sim.joint_deg(2) < high - 5


def test_weak_servo_sags_under_payload():
    sim = HardwareSim(spec=ServoSpec(rated_torque=0.05), payload_kg=1.0)
    bot = Robot(sim)
    bot.set_torque(2, True)
    bot.goto(2, 220, speed=500)
    run(sim, 2.0)
    assert sim.joint_deg(2) < 150            # 扛不住，明显下垂
    assert sim.servos[2].status & 0x20       # 负载异常


def test_low_voltage_cutoff():
    sim = HardwareSim(battery=BatterySpec(ocv=9.5))
    sim.step(0.01)
    assert sim.cutoff
    assert sim.servos[2].status & 0x01
    assert not sim.servos[2].torque_on


def test_drop_frame_raises():
    sim = HardwareSim(drop_rate=1.0)
    bot = Robot(sim)
    with pytest.raises(Exception):
        bot.feedback(1)


def test_retry_counts_and_gives_up():
    sim = HardwareSim(drop_rate=1.0)
    link = RetryLink(sim, retries=2)
    bot = Robot(link)
    with pytest.raises(RuntimeError):
        bot.feedback(1)
    assert link.errors == 3
    assert link.retried == 2


def test_encoder_quantized():
    sim = HardwareSim()
    s = sim.servos[1]
    s.pos_deg = 359.9
    assert 0 <= s.ticks < 4096
    s.pos_deg = 720.0
    assert s.ticks == 0


def test_chassis_moves_straight():
    sim = HardwareSim()
    bot = Robot(sim)
    bot.drive_speed(100, 0)
    run(sim, 1.0)
    x, y, yaw = sim.pose()
    assert 60 < x < 100                   # 有加速过程，不到 100
    assert abs(y) < 1 and abs(yaw) < 1


def test_slip_keeps_pose():
    sim = HardwareSim()
    sim.chassis.slip = 1.0
    bot = Robot(sim)
    bot.drive_speed(100, 0)
    run(sim, 1.0)
    assert sim.pose() == pytest.approx((0, 0, 0))


def test_feedback_voltage_and_temp():
    sim = HardwareSim()
    bot = Robot(sim)
    fb = bot.feedback(1)
    assert fb.voltage == pytest.approx(sim.voltage, abs=0.05)
    assert 20 <= fb.temp_c <= 40
