"""新机自检：必须能区分"装对了""没接上""有故障""动不准"。"""

import json

import pytest

from modkit import protocol as p
from modkit import selftest as st
from modkit.bus import SimLink
from modkit.robot import Robot


class OffsetRead(SimLink):
    """读到位置永远偏 10°（约 114 tick），用于模拟机械卡滞/编码器偏。"""

    def __init__(self, ids, offset_deg=10.0):
        super().__init__(ids)
        self.offset = int(offset_deg / p.DEG_PER_TICK)

    def transact(self, frame, expect_id, timeout=0.05):
        f = super().transact(frame, expect_id, timeout)
        if frame[4] == p.READ and frame[5] == p.REG_PRESENT_POS and len(f.params) >= 2:
            t = (f.params[0] | f.params[1] << 8) + self.offset
            t = max(0, min(4095, t))
            buf = bytearray(f.params)
            buf[0], buf[1] = t & 0xFF, (t >> 8) & 0xFF
            return p.Frame(id=f.id, error=f.error, params=bytes(buf))
        return f


def test_all_good(tmp_path):
    bot = Robot(SimLink([1, 2, 3, 4]))
    rep = st.selftest(bot, [1, 2, 3, 4], settle=0)
    assert rep.ok
    assert [s.sid for s in rep.steps] == [1, 2, 3, 4]
    path = rep.save(tmp_path / "st.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["ok"] is True and len(data["steps"]) == 4


def test_missing_servo_stops():
    bot = Robot(SimLink([1, 2]))
    rep = st.selftest(bot, [1, 2, 3], settle=0)
    assert not rep.ok
    assert rep.stopped
    assert any(not s.ok for s in rep.steps if s.sid == 3)


def test_fault_bit_stops():
    link = SimLink([1, 2, 3, 4])
    link.mem[2][p.REG_STATUS] = 0x01
    rep = st.selftest(Robot(link), [1, 2, 3, 4], settle=0)
    assert not rep.ok
    assert "故障" in rep.stopped
    assert len(rep.steps) <= 2


def test_position_error_detected():
    rep = st.selftest(Robot(OffsetRead([1, 2])), [1, 2], amp=5.0, tol=1.5, settle=0)
    assert not rep.ok
    assert any("到位误差" in s.detail for s in rep.steps)


def test_torque_is_disabled_after_test():
    link = SimLink([1, 2, 3, 4])
    rep = st.selftest(Robot(link), [1, 2, 3, 4], settle=0)
    assert rep.ok
    for sid in (1, 2, 3, 4):
        assert link.mem[sid][p.REG_TORQUE_ENABLE] == 0


def test_high_temperature_blocks_motion():
    link = SimLink([1])
    link.mem[1][p.REG_PRESENT_TEMP] = 60
    rep = st.selftest(Robot(link), [1], settle=0)
    assert not rep.ok
    assert "温度" in rep.stopped
