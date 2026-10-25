"""回归基线：相同通过、时间/电压/位姿漂移能抓住。"""

import pytest

from modkit import simdiff


def _m(**kw):
    d = {"ok": True, "time": 10.0, "voltage": 12.0, "pose": [0, 0, 0],
         "trace": [{}] * 10, "failures": []}
    d.update(kw)
    return d


def test_identical_passes():
    r = simdiff.compare(_m(), _m())
    assert r["ok"] and not r["problems"]


def test_time_and_voltage_drift_fail():
    r = simdiff.compare(_m(), _m(time=11.0, voltage=12.2))
    assert not r["ok"]
    assert any("用时" in p for p in r["problems"])
    assert any("电压" in p for p in r["problems"])


def test_pose_drift_fail():
    r = simdiff.compare(_m(), _m(pose=[10.0, 0, 5.0]))
    assert not r["ok"]
    assert any("终点偏" in p for p in r["problems"])
