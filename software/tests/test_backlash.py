"""回差：测量逻辑 + 换向补偿方向必须对。"""

import pytest

from modkit import backlash as bl


class StubRobot:
    """按预设序列返回位置；goto 只记录。"""

    def __init__(self, positions):
        self.positions = list(positions)
        self.i = 0
        self.gotos = []
        self.torque = None

    def set_torque(self, sid, on):
        self.torque = on

    def goto(self, sid, deg, speed=0, acc=0):
        self.gotos.append(deg)

    def position_ticks(self, sid):
        v = self.positions[min(self.i, len(self.positions) - 1)]
        self.i += 1
        return v


def test_measure_from_both_sides():
    # 从 + 侧读到 2048，从 - 侧读到 2036 → 12 tick ≈ 1.055°
    bot = StubRobot([2048, 2036])
    jp = bl.measure(bot, 1, center=180, span=10, settle=0)
    assert abs(jp.play_deg - 12 * 360 / 4096) < 0.01
    assert bot.torque is False          # 测完必须卸力
    assert len(bot.gotos) >= 4


def test_measure_rejects_bad_span():
    with pytest.raises(bl.BacklashError):
        bl.measure(StubRobot([2048, 2048]), 1, span=0, settle=0)


def test_play_ok_threshold():
    assert bl.JointPlay(1, "yaw", 0.8).ok
    assert not bl.JointPlay(1, "yaw", 1.2).ok


def test_compensator_first_move_no_offset():
    c = bl.Compensator()
    c.set_play(1, 1.0)
    assert c.command(1, 100.0) == 100.0


def test_compensator_adds_half_play_by_direction():
    c = bl.Compensator()
    c.set_play(1, 1.0)
    c.command(1, 100.0)
    c.note(1, 100.0)
    assert c.command(1, 110.0) == pytest.approx(110.5)   # 正向 +0.5
    c.note(1, 110.0)
    assert c.command(1, 100.0) == pytest.approx(99.5)    # 反向 -0.5


def test_compensator_save_load(tmp_path):
    c = bl.Compensator()
    c.set_play(1, 0.7)
    c.set_play(2, 0.3)
    p = c.save(tmp_path / "bl.json")
    d = bl.Compensator()
    d.load(p)
    assert d.plays == {1: 0.7, 2: 0.3}
