"""台架测试（bench.py）：重复精度与烧机，全部在仿真链路跑。"""

import csv

from modkit import bench, protocol as p
from modkit.bus import SimLink
from modkit.robot import Robot


def test_repeatability_ok_in_sim():
    bot = Robot(SimLink([1, 2, 3, 4]))
    r = bench.repeatability(bot, 180, 0, 120, n=4, settle=0)
    assert r["n"] == 4
    assert len(r["points"]) == 4
    assert r["span_mm"] < 2.0 and r["ok"]


def test_burn_in_counts_cycles_and_writes_csv(tmp_path):
    bot = Robot(SimLink([1, 2, 3, 4]))
    log = bench.BenchLog(tmp_path / "b.csv")
    r = bench.burn_in(bot, minutes=0.02, cycle_s=0.01, log=log)
    assert r["cycles"] >= 2
    assert r["ok"]
    with (tmp_path / "b.csv").open(encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0][0] == "t" and len(rows) >= 3


def test_burn_in_stops_on_high_temp(tmp_path):
    link = SimLink([1, 2, 3, 4])
    link.mem[1][p.REG_PRESENT_TEMP] = 70
    bot = Robot(link)
    r = bench.burn_in(bot, minutes=1.0, cycle_s=0.01, limit_c=55.0)
    assert not r["ok"]
    assert "温度" in r["stopped"]
    assert r["cycles"] <= 1


def test_fk_matches_commanded_point():
    bot = Robot(SimLink([1, 2, 3, 4]))
    yaw, sh, el = bot.move_pose(180, 0, 120, speed=200)
    x, y, z = bench.fk_point(bot)
    assert abs(x - 180) < 1.5 and abs(y) < 1.5 and abs(z - 120) < 1.5
