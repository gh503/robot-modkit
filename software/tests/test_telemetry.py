"""M5 日志：CSV 往返、汇总、电量估算、记录条数。"""

import csv

import pytest

from modkit import telemetry as tm
from modkit.bus import SimLink
from modkit.robot import Robot


def sample(i=0, sid=1, v=12.0, temp=30, status=0):
    return tm.Sample(i, sid, 180.0 + i, 0, 0, v, temp, status)


def test_csv_roundtrip(tmp_path):
    p = tmp_path / "log.csv"
    with tm.Recorder(p) as rec:
        rec.write(sample(0))
        rec.write(sample(1, sid=2, v=11.5))
    rows = tm.read_log(p)
    assert len(rows) == 2
    assert rows[1].sid == 2 and rows[1].voltage == 11.5
    with p.open() as f:
        assert list(csv.DictReader(f))[0]["pos_deg"] == "180.0"


def test_summary():
    sm = tm.summarize([sample(0, v=12.1), sample(1, v=11.4, temp=41),
                       sample(2, v=11.0, status=1)])
    assert sm["n"] == 3
    assert sm["v_min"] == 11.0 and sm["v_max"] == 12.1
    assert sm["t_max"] == 41
    assert sm["faults"] == 1
    assert sm["v_end"] == 11.0


def test_empty_summary():
    assert tm.summarize([]) == {"n": 0}


def test_battery_levels():
    assert tm.battery(12.4)[1] == "ok"
    assert tm.battery(10.5)[1] == "low"
    assert tm.battery(10.0)[1] == "critical"
    assert tm.battery(9.0)[0] == 0
    assert tm.battery(13.0)[0] == 100


def test_record_counts(tmp_path):
    bot = Robot(SimLink([1, 2, 3]))
    p, n = tm.record(bot, [1, 2, 3], 0.4, hz=10, path=tmp_path / "t.csv",
                     sleep=lambda dt: None)
    assert n == len(tm.read_log(p))
    assert n == 12


def test_record_rejects_bad_args(tmp_path):
    bot = Robot(SimLink([1]))
    with pytest.raises(ValueError):
        tm.record(bot, [1], 0, hz=5, path=tmp_path / "x.csv")
