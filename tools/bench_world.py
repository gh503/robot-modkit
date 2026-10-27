#!/usr/bin/env python3
"""世界/管网轻量基准：时间、体积误差、L 形稳定性。不是性能保证。"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "software"))

from modkit import network as nw  # noqa: E402
from modkit import world as wd  # noqa: E402
from modkit import world_sim  # noqa: E402


def run(duration: float, dx: float) -> dict:
    out = {"worlds": {}, "network": {}}
    for key in ("pool", "pool_l", "outdoor"):
        w = wd.from_preset(key)
        t0 = time.perf_counter()
        r = world_sim.WorldRun(w, duration=duration, dx=dx, frame_every=10).run()
        dt = time.perf_counter() - t0
        fluids = {}
        for fid, v in r["fluids"].items():
            m = v.get("metrics", {})
            fluids[fid] = {"volume_m3": m.get("volume_m3"),
                           "volume_error_rel": m.get("volume_error_rel"),
                           "max_depth_m": m.get("max_depth_m"),
                           "max_speed_m_s": m.get("max_speed_m_s"),
                           "wet_cells": m.get("wet_cells")}
        out["worlds"][key] = {"seconds": round(dt, 4), "fluids": fluids}
    net = nw.Network.load(ROOT / "software" / "networks" / "pool_loop.json")
    t0 = time.perf_counter()
    nr = nw.solve(net)
    out["network"] = {"seconds": round(time.perf_counter() - t0, 4),
                      "iterations": nr["iterations"],
                      "mass_balance_error_m3_s": nr["mass_balance_error_m3_s"]}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=float, default=1.0)
    ap.add_argument("--dx", type=float, default=0.4)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    r = run(a.duration, a.dx)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        for k, v in r["worlds"].items():
            print(f"{k:8} {v['seconds']:.3f}s  " + ", ".join(
                f"{fid}: vol={m['volume_m3']:.3f} err={m['volume_error_rel']:.1e} "
                f"maxd={m['max_depth_m']:.3f} v={m['max_speed_m_s']:.3f}"
                for fid, m in v["fluids"].items()))
        n = r["network"]
        print(f"{'network':8} {n['seconds']:.3f}s  iter={n['iterations']} "
              f"mass_err={n['mass_balance_error_m3_s']:.1e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
