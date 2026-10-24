"""标定向导的测试：全部跑在 SimLink 上，不需要硬件。

覆盖的是"换算"和"流程"——真机的风险在堵转和通讯，不在这几个函数里。
"""

import pytest

from modkit import calibrate as cal
from modkit import protocol as p
from modkit.bus import SimLink
from modkit.calibrate import CalibError, Calibration, Joint
from modkit.robot import Robot


def test_joint_roundtrip_positive_dir():
    j = Joint("yaw", 1, 2048, dir=1, min_deg=0, max_deg=180)
    assert j.tick_to_deg(2048) == 0
    assert abs(j.tick_to_deg(3072) - 90) < 1e-6
    assert j.deg_to_tick(90) == 3072


def test_joint_roundtrip_negative_dir():
    j = Joint("elbow", 3, 1000, dir=-1, min_deg=-150, max_deg=5)
    for deg in (-150, -60, 0, 5):
        assert abs(j.tick_to_deg(j.deg_to_tick(deg)) - deg) < 0.1


def test_zero_is_relative_not_absolute():
    """零位不在 tick 0 时，关节 0° 不能等于舵机 0°。"""
    j = Joint("wrist", 4, 3000, dir=-1, min_deg=-90, max_deg=90)
    assert j.deg_to_tick(0) == 3000
    assert j.tick_to_deg(3000) == 0


def test_validation_rejects_bad_values():
    with pytest.raises(CalibError):
        Joint("x", 1, 2048, dir=0).check()
    with pytest.raises(CalibError):
        Joint("x", 1, 2048, min_deg=90, max_deg=10).check()
    with pytest.raises(CalibError):
        Joint("x", 1, 9999).check()


def test_save_load(tmp_path):
    c = Calibration()
    c.add(Joint("yaw", 1, 2048, 1, 0, 180))
    c.add(Joint("elbow", 3, 1000, -1, -150, 5))
    path = c.save(tmp_path / "calib.json")
    back = Calibration.load(path)
    assert set(back.joints) == {"yaw", "elbow"}
    assert back.joints["elbow"].dir == -1
    assert back.created.startswith("20")


def test_find_limits_in_sim():
    bot = Robot(SimLink([1]))
    lo, hi = cal.find_limits(bot, 1, lo=0, hi=180, step=30, settle=0)
    # 0..360° 对应 0..4095 tick，所以 180° 就是 2048，不是 4000+
    assert lo < 10 and abs(hi - 2048) <= 2


def test_set_zero_then_verify():
    bot = Robot(SimLink([1]))
    ticks = cal.set_zero(bot, 1, deg=90)
    j = Joint("yaw", 1, ticks, 1, 0, 180)
    rows = cal.verify(bot, j, tol_deg=0.5)
    assert len(rows) == 3
    assert all(r["err"] <= 0.5 for r in rows)


class OffsetLink(SimLink):
    """模拟"机械零位偏了"：读位置时整体加一个 tick 偏移。"""

    def __init__(self, ids, offset: int):
        super().__init__(ids)
        self.offset = offset

    def transact(self, frame, expect_id, timeout=0.05):
        f = super().transact(frame, expect_id, timeout)
        if frame[4] == p.READ and frame[5] == p.REG_PRESENT_POS:
            t = (f.params[0] | f.params[1] << 8) + self.offset
            t = max(0, min(4095, t))
            return p.Frame(id=f.id, error=f.error, params=bytes([t & 0xFF, t >> 8]))
        return f


def test_verify_catches_mechanical_offset():
    """标定后如果机械零位又偏了 100 tick（约 8.8°），验证必须报错。"""
    link = OffsetLink([1], offset=0)
    bot = Robot(link)
    ticks = cal.set_zero(bot, 1, deg=90)
    j = Joint("yaw", 1, ticks, 1, 0, 180)
    link.offset = 100
    with pytest.raises(CalibError):
        cal.verify(bot, j, tol_deg=2.0)


def test_scan_expects_six_joints():
    bot = Robot(SimLink([1, 2, 3, 4, 5, 6]))
    assert cal.scan_joints(bot, expected=6) == [1, 2, 3, 4, 5, 6]
    with pytest.raises(CalibError):
        cal.scan_joints(bot, expected=7)


def test_default_joint_order_matches_doc():
    assert cal.default_joints()[:3] == ["yaw", "shoulder", "elbow"]
    assert len(cal.default_joints()) == 6