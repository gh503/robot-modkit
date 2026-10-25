"""M5 日志与回放：把舵机反馈记成 CSV，掉电/复盘都能看。

只做事实记录，不做"智能诊断"：
  · 每个采样点：时间、ID、位置、速度、负载、电压、温度、状态位；
  · 回放给最小值/最大值/故障计数，够定位"哪一秒掉压/过热"。
"""

from __future__ import annotations

import csv
import time
from dataclasses import asdict, dataclass
from pathlib import Path

FIELDS = ["t", "sid", "pos_deg", "speed", "load", "voltage", "temp_c", "status"]


@dataclass
class Sample:
    t: float
    sid: int
    pos_deg: float
    speed: int
    load: int
    voltage: float
    temp_c: int
    status: int = 0


class Recorder:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = self.path.open("w", newline="", encoding="utf-8")
        self._w = csv.DictWriter(self._f, fieldnames=FIELDS)
        self._w.writeheader()
        self.n = 0

    def write(self, s: Sample) -> None:
        row = asdict(s)
        row["t"] = round(s.t, 3)
        row["voltage"] = round(s.voltage, 2)
        self._w.writerow(row)
        self.n += 1

    def close(self) -> None:
        self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def record(robot, ids: list[int], seconds: float, hz: float = 5.0,
           path: str | Path = "telemetry.csv",
           clock=time.monotonic, sleep=time.sleep) -> tuple[Path, int]:
    """按固定频率读反馈并落盘；返回 (路径, 样本数)。"""
    if seconds <= 0 or hz <= 0:
        raise ValueError("seconds / hz 必须为正")
    n = max(1, int(round(seconds * hz)))
    t0 = clock()
    with Recorder(path) as rec:
        for i in range(n):
            for sid in ids:
                fb = robot.feedback(sid)
                rec.write(Sample(clock() - t0, sid, fb.position_deg, fb.speed,
                                 fb.load, fb.voltage, fb.temp_c, robot.status(sid)))
            if i != n - 1:
                sleep(1.0 / hz)
    return Path(path), n * len(ids)


def read_log(path: str | Path) -> list[Sample]:
    out: list[Sample] = []
    with Path(path).open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out.append(Sample(
                t=float(row["t"]), sid=int(row["sid"]),
                pos_deg=float(row["pos_deg"]), speed=int(row["speed"]),
                load=int(row["load"]), voltage=float(row["voltage"]),
                temp_c=int(row["temp_c"]), status=int(row["status"]),
            ))
    return out


def summarize(samples: list[Sample]) -> dict:
    if not samples:
        return {"n": 0}
    volts = [s.voltage for s in samples]
    temps = [s.temp_c for s in samples]
    return {
        "n": len(samples),
        "seconds": round(max(s.t for s in samples), 2),
        "ids": sorted({s.sid for s in samples}),
        "v_min": min(volts), "v_max": max(volts),
        "t_max": max(temps),
        "faults": sum(1 for s in samples if s.status),
        "v_end": samples[-1].voltage,
    }


def battery(voltage: float) -> tuple[float, str]:
    """3S 锂电粗估：12.6V 满，9.9V 空；只用于提示，不用于保护。"""
    pct = (voltage - 9.9) / (12.6 - 9.9) * 100.0
    pct = max(0.0, min(100.0, pct))
    if voltage < 10.2:
        return pct, "critical"
    if voltage < 10.8:
        return pct, "low"
    return pct, "ok"
