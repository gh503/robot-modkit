"""确定性场景：用 JSON 描述"给硬件什么激励、期望什么结果"，CI 直接跑。

场景是调试数字孪生的入口：改一个参数（电池内阻/负载/打滑/丢帧），
重跑同一条脚本，看断言过不过——不需要真机，也不靠盯曲线。
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from . import camsim as cs
from . import kinematics as kin
from . import mission as ms
from . import nav as nv
from . import vision as vis
from .bus import RetryLink
from .hwsim import BatterySpec, HardwareSim, ServoSpec
from .robot import Robot


class ScenarioError(RuntimeError):
    pass


def _resolve(sim: HardwareSim, path: str, meta: dict | None = None):
    meta = meta or {}
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
    if path.startswith("mission."):
        return meta.get("mission", {}).get(path.split(".", 1)[1])
    if path.startswith("arm."):
        t = [sim.servos[i].ticks for i in (1, 2, 3)]
        pose = kin.forward(kin.ArmGeometry(), *kin.ticks_to_joints(*t))
        return {"x": pose.x, "y": pose.y, "z": pose.z}[path.split(".")[1]]
    if path.startswith("det."):
        d = meta.get("det")
        if d is None:
            raise ScenarioError("还没有检测结果")
        return {"cx": d.cx, "cy": d.cy, "area": d.area}[path.split(".")[1]]
    raise ScenarioError(f"未知路径：{path}")


def _check(sim, a: dict, meta: dict | None = None) -> tuple[bool, str]:
    got = _resolve(sim, a["path"], meta)
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
    link = RetryLink(sim, retries=cfg["retries"]) if cfg.get("retries") else sim
    sim.chassis.slip = cfg.get("slip", 0.0)
    bot = Robot(link)
    log = []
    failures = []
    meta: dict = {}
    trace: list[dict] = []

    def advance(h: float):
        sim.step(h)
        if not trace or sim.time - trace[-1]["t"] >= 0.02:
                trace.append({
                    "t": round(sim.time, 3),
                    "x": round(sim.chassis.x, 2), "y": round(sim.chassis.y, 2),
                    "yaw": round(sim.chassis.yaw, 1),
                    "j1": round(sim.joint_deg(1), 1),
                    "j2": round(sim.joint_deg(2), 1),
                    "j3": round(sim.joint_deg(3), 1),
                    "v": round(sim.voltage, 2),
                    "temp": round(sim.servos[2].temp_c, 1),
                })

    def step(seconds: float):
        for _ in range(max(1, int(round(seconds / dt)))):
            advance(dt)

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
        elif cmd == "mission":
            cube = act.get("cube", [200.0, 0.0, 40.0])
            cam = cs.Camera(z=act.get("camera_z", 800.0),
                            fx=act.get("fx", 600.0))
            cubes = [cs.Cube(cube[0], cube[1], cube[2],
                             tuple(act.get("color", [200, 60, 40])))]
            color = tuple(act.get("color", [200, 60, 40]))

            def look():
                img = cs.render(cam, cubes, seed=act.get("seed", 0))
                det = vis.detect_color(img, color, tol=act.get("tol", 40))
                meta["det"] = det
                return det

            use_nav = bool(act.get("nav"))

            def drive(x, y, th):
                if not use_nav:
                    step(act.get("drive_seconds", 2.0))
                    return True

                def read_pose():
                    o = bot.update_odom()
                    return nv.Pose(o.x, o.y, o.yaw)

                def set_speed(v, w):
                    bot.drive_speed(v, w)

                r = nv.navigate(read_pose, set_speed, nv.Pose(x, y, th),
                                dt=0.02, sleep=advance)
                log.append(f"[{i}] drive({x:.0f},{y:.0f}) {r.error_mm:.1f}mm "
                           f"{'OK' if r.ok else 'FAIL'}")
                return r.ok

            def pick(det):
                if det is None:
                    return False
                cal = cam.table_calib(cube[2])
                wx, wy = cal.apply(det.cx, det.cy)
                if use_nav:
                    # 世界 → 臂基座：先平移再按偏航旋转
                    dx, dy = wx - sim.chassis.x, wy - sim.chassis.y
                    a = math.radians(-sim.chassis.yaw)
                    bx, by = dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)
                else:
                    bx, by = wx, wy
                clearance = act.get("clearance", 60.0)
                grasp_z = act.get("grasp_z", 25.0)
                above = kin.inverse(kin.ArmGeometry(), kin.Pose(bx, by, clearance))
                grasp = kin.inverse(kin.ArmGeometry(), kin.Pose(bx, by, grasp_z))
                plan = vis.PickPlan(bx, by, 0.0, clearance, grasp_z, above, grasp)
                bot.move_pose(plan.x, plan.y, plan.above_z)
                step(1.5)
                bot.move_pose(plan.x, plan.y, plan.grasp_z)
                step(1.5)
                bot.gripper(act.get("close", 0.15))
                step(0.5)
                bot.move_pose(plan.x, plan.y, plan.above_z)   # 抬起
                step(1.5)
                return True

            def drop():
                bot.gripper(1.0)
                step(0.8)
                return True

            r = ms.Mission(drive, look, pick, drop,
                           cfg=ms.MissionConfig(pick_xy=tuple(act["pick"]),
                                                drop_xy=tuple(act["drop"])),
                           now=lambda: sim.time).run()
            meta["mission"] = r.as_dict()
            log.append(f"[{i}] mission {r.success} {r.seconds:.1f}s {r.reason}")
            if not r.success:
                failures.append(log[-1])
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
                                sleep=advance)
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
            ok, msg = _check(sim, act, meta)
            log.append(f"[{i}] {msg}")
            if not ok:
                failures.append(msg)
        else:
            raise ScenarioError(f"未知动作：{cmd}")

    for a in scene.get("assert", []):
        ok, msg = _check(sim, a, meta)
        log.append(f"[end] {msg}")
        if not ok:
            failures.append(msg)

    return {"ok": not failures, "failures": failures, "log": log,
            "pose": [round(v, 2) for v in sim.pose()],
            "voltage": round(sim.voltage, 2), "time": round(sim.time, 2),
            "trace": trace}


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
