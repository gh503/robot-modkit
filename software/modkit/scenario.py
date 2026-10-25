"""确定性场景：用 JSON 描述"给硬件什么激励、期望什么结果"，CI 直接跑。

场景是调试数字孪生的入口：改一个参数（电池内阻/负载/打滑/丢帧），
重跑同一条脚本，看断言过不过——不需要真机，也不靠盯曲线。
"""

from __future__ import annotations

import json
from pathlib import Path

from . import nav as nv
from .hwsim import BatterySpec, HardwareSim, ServoSpec
from .robot import Robot


class ScenarioError(RuntimeError):
    pass


def _resolve(sim: HardwareSim, path: str):
    if path == "voltage":
        return sim.voltage
    if path == "time":
        return sim.time
    if path.startswith("pose."):
        return {"x": sim.chassis.x, "y": sim.chassis.y, "yaw": sim.chassis.yaw}[path.split(".")[1]]
    if path.startswith("joint."):
        return sim.joint_deg(int(path.split(".")[1]))
    if path.startswith("servos."):
        _, sid, attr = path.split(".")
        s = sim.servos[int(sid)]
        if attr == "status":
            return s.status
        if attr == "temp":
            return s.temp_c
        if attr == "current":
            return s.current_a
        if attr == "pos":
            return s.pos_deg
        raise ScenarioError(f"未知属性：{path}")
    if path.startswith("chassis."):
        return getattr(sim.chassis, path.split(".")[1])
    raise ScenarioError(f"未知路径：{path}")


def _check(sim, a: dict) -> tuple[bool, str]:
    got = _resolve(sim, a["path"])
    op = a.get("op", "near")
    want = a.get("value")
    tol = a.get("tol", 1e-6)
    ok = {
        "near": abs(got - want) <= tol,
        "lt": got < want,
        "gt": got > want,
        "eq": got == want,
        "bit": bool(int(got) & int(want)),
    }.get(op)
    if ok is None:
        raise ScenarioError(f"未知断言：{op}")
    return ok, f"{a['path']}={got!r} {op} {want!r} → {'PASS' if ok else 'FAIL'}"


def run_scenario(scene: dict, dt: float = 0.002) -> dict:
    cfg = scene.get("sim", {})
    spec = ServoSpec(**cfg.get("servo", {}))
    batt = BatterySpec(**cfg.get("battery", {}))
    sim = HardwareSim(spec=spec, battery=batt,
                      drop_rate=cfg.get("drop_rate", 0.0),
                      bus_latency=cfg.get("bus_latency", 0.0),
                      payload_kg=cfg.get("payload_kg", 0.0))
    sim.chassis.slip = cfg.get("slip", 0.0)
    bot = Robot(sim)
    log = []
    failures = []

    def step(seconds: float):
        for _ in range(max(1, int(round(seconds / dt)))):
            sim.step(dt)

    for i, act in enumerate(scene.get("actions", []), 1):
        cmd = act.get("cmd")
        if cmd == "torque":
            bot.set_torque(act["sid"], act["on"])
        elif cmd == "goto":
            bot.set_torque(act["sid"], True)
            bot.goto(act["sid"], act["deg"], speed=act.get("speed", 500))
        elif cmd == "drive":
            bot.drive_speed(act["v"], act.get("w", 0.0))
        elif cmd == "stop":
            bot.stop_wheels()
        elif cmd in ("nav", "nav_square"):
            def read_pose():
                o = bot.update_odom()
                return nv.Pose(o.x, o.y, o.yaw)

            def set_speed(v, w):
                bot.drive_speed(v, w)

            goals = (nv.square_waypoints(act.get("size", 300.0))
                     if cmd == "nav_square"
                     else [nv.Pose(act["x"], act["y"], act.get("theta", 0.0))])
            for g in goals:
                r = nv.navigate(read_pose, set_speed, g, dt=act.get("dt", 0.02),
                                sleep=lambda h: sim.step(h))
                log.append(f"[{i}] nav({g.x:.0f},{g.y:.0f}) "
                           f"{r.error_mm:.1f}mm/{r.error_deg:.1f}° "
                           f"{'OK' if r.ok else 'FAIL'}")
                if not r.ok:
                    failures.append(log[-1])
        elif cmd == "wait":
            step(act["seconds"])
        elif cmd == "set":
            if act["path"] == "chassis.slip":
                sim.chassis.slip = act["value"]
            elif act["path"] == "payload_kg":
                sim.payload_kg = act["value"]
            else:
                raise ScenarioError(f"未知 set 路径：{act['path']}")
        elif cmd == "assert":
            ok, msg = _check(sim, act)
            log.append(f"[{i}] {msg}")
            if not ok:
                failures.append(msg)
        else:
            raise ScenarioError(f"未知动作：{cmd}")

    for a in scene.get("assert", []):
        ok, msg = _check(sim, a)
        log.append(f"[end] {msg}")
        if not ok:
            failures.append(msg)

    return {"ok": not failures, "failures": failures, "log": log,
            "pose": [round(v, 2) for v in sim.pose()],
            "voltage": round(sim.voltage, 2), "time": round(sim.time, 2)}


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
