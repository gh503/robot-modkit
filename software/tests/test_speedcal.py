"""速度寄存器标定：仿真、静止、反向、非法参数。"""

import pytest

from modkit import speedcal
from modkit.bus import SimLink
from modkit.robot import Robot


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, dt):
        self.t += dt


def make(wheels=True):
    c = Clock()
    bot = Robot(SimLink(list(range(1, 7)), wheels=wheels, clock=c))
    return bot, c


def test_sim_unit_is_one():
    bot, c = make()
    r = speedcal.measure(bot, 5, lsb=100, seconds=0.5, hz=50, clock=c, sleep=c.sleep)
    assert r.ok
    assert r.unit == pytest.approx(1.0, abs=0.01)
    assert r.deg_s == pytest.approx(100, abs=1)


def test_no_motion_fails():
    bot, c = make(wheels=False)
    r = speedcal.measure(bot, 5, lsb=100, seconds=0.3, hz=50, clock=c, sleep=c.sleep)
    assert not r.ok
    assert "没转" in r.note


def test_zero_lsb_rejected():
    bot, c = make()
    with pytest.raises(ValueError):
        speedcal.measure(bot, 5, lsb=0, clock=c, sleep=c.sleep)


class ReverseBot:
    """位置计数与命令反向，模拟左右轮接线相反。"""

    def __init__(self, clock):
        self.c = clock
        self.dir = 1

    def set_mode(self, sid, mode):
        pass

    def set_torque(self, sid, on):
        pass

    def set_speed_raw(self, sid, lsb):
        self.dir = -1 if lsb >= 0 else 1

    def position_ticks(self, sid):
        return int(1000 + self.c() * 100 * self.dir * 4096 / 360)


def test_reverse_direction_flagged():
    c = Clock()
    bot = ReverseBot(c)
    bot.set_speed_raw(5, 100)     # 先让假机器人知道方向（measure 里会再写一次）
    r = speedcal.measure(bot, 5, lsb=100, seconds=0.4, hz=50, clock=c, sleep=c.sleep)
    assert not r.ok
    assert "相反" in r.note
