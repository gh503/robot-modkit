"""确定性场景：用 JSON 描述"给硬件什么激励、期望什么结果"，CI 直接跑。

场景是调试数字孪生的入口：改一个参数（电池内阻/负载/打滑/丢帧），
重跑同一条脚本，看断言过不过——不需要真机，也不靠盯曲线。
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from . import calib as cb
from . import camsim as cs
from . import kinematics as kin
from . import mission as ms
from . import nav as nv
from . import contact as ct
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
    if path.startswith("grasp."):
        return {"error_mm": meta.get("grasp_error_mm", 0.0),
                "holds": meta.get("grasp", {}).get("holds", False)}[path.split(".")[1]]
    if path.startswith("contact."):
        c = meta.get("contact", {})
        key = path.split(".", 1)[1]
        if key.startswith("wrench."):
            return c.get("wrench", {}).get(key.split(".", 1)[1], 0.0)
        return {"state": c.get("state", "hold"), "slip_mm": c.get("slip_mm", 0.0),
                "dropped": c.get("dropped", False)}[key]
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

    def arm_side():
        def joint(sid):
            return sim.servos[sid].output_deg() - 180.0
        a = math.radians(joint(2))
        b = math.radians(joint(3))
        g = kin.ArmGeometry()
        d = g.l1 * math.cos(a) + g.l2 * math.cos(a + b)
        z = g.base_h + g.l1 * math.sin(a) + g.l2 * math.sin(a + b)
        return [[0.0, g.base_h],
                [g.l1 * math.cos(a), g.base_h + g.l1 * math.sin(a)],
                [d, z]]

    def advance(h: float):
        sim.step(h)
        if not trace or sim.time - trace[-1]["t"] >= 0.02:
                arm = arm_side()
                yaw = math.radians(sim.chassis.yaw)
                ee = [sim.chassis.x + arm[2][0] * math.cos(yaw),
                      sim.chassis.y + arm[2][0] * math.sin(yaw), arm[2][1]]
                trace.append({
                    "t": round(sim.time, 3),
                    "x": round(sim.chassis.x, 2), "y": round(sim.chassis.y, 2),
                    "yaw": round(sim.chassis.yaw, 1),
                    "j1": round(sim.joint_deg(1), 1),
                    "j2": round(sim.joint_deg(2), 1),
                    "j3": round(sim.joint_deg(3), 1),
                    "j4": round(sim.joint_deg(4), 1),
                    "arm": [[round(p[0], 1), round(p[1], 1)] for p in arm],
                    "ee": [round(v, 1) for v in ee],
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
            onboard = act.get("camera") == "onboard"
            cam = cs.Camera(width=act.get("cam_w", 320 if onboard else 640),
                            height=act.get("cam_h", 240 if onboard else 480),
                            cx=act.get("cam_w", 320 if onboard else 640) / 2,
                            cy=act.get("cam_h", 240 if onboard else 480) / 2,
                            z=act.get("camera_z", 500.0 if onboard else 800.0),
                            fx=act.get("fx", 250.0 if onboard else 600.0),
                            k1=act.get("cam_k1", 0.0), k2=act.get("cam_k2", 0.0),
                            p1=act.get("cam_p1", 0.0), p2=act.get("cam_p2", 0.0))
            cubes = [cs.Cube(cube[0], cube[1], cube[2],
                             tuple(act.get("color", [200, 60, 40])))]
            color = tuple(act.get("color", [200, 60, 40]))

            def look():
                if onboard:
                    cam.x, cam.y = sim.chassis.x, sim.chassis.y
                    cam.yaw_deg = sim.chassis.yaw
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
                # 用反投影而不是仿射：镜头畸变下仿射只在中心近似
                wx, wy = cam.unproject(det.cx, det.cy, cube[2])
                if use_nav:
                    # 世界 → 臂基座：先平移再按偏航旋转
                    dx, dy = wx - sim.chassis.x, wy - sim.chassis.y
                    a = math.radians(-sim.chassis.yaw)
                    true_bx = dx * math.cos(a) - dy * math.sin(a)
                    true_by = dx * math.sin(a) + dy * math.cos(a)
                else:
                    true_bx, true_by = wx, wy

                # 手眼误差：nominal = 真实变换的逆；标定后估计出正向变换
                he = cb.HandEye(*act.get("handeye", [0.0, 0.0, 0.0]))
                if act.get("calibrate"):
                    truth = cb.calibration_grid(0.0, 0.0, 80.0)
                    measured = [he.inverse().apply(*p) for p in truth]
                    est = cb.HandEye.fit(measured, truth)
                    bx, by = est.apply(*he.inverse().apply(true_bx, true_by))
                    meta["handeye"] = est.to_json()
                    log.append(f"[{i}] 手眼标定残余 {est.residual_mm(measured, truth):.2f}mm")
                else:
                    bx, by = he.inverse().apply(true_bx, true_by)
                    meta["handeye"] = he.to_json()
                err_mm = math.hypot(bx - true_bx, by - true_by)
                meta["grasp_error_mm"] = round(err_mm, 2)
                clearance = act.get("clearance", 60.0)
                grasp_z = act.get("grasp_z", 25.0)
                above = kin.inverse(kin.ArmGeometry(), kin.Pose(bx, by, clearance))
                grasp = kin.inverse(kin.ArmGeometry(), kin.Pose(bx, by, grasp_z))
                plan = vis.PickPlan(bx, by, 0.0, clearance, grasp_z, above, grasp)
                if err_mm > act.get("grasp_tol", 15.0):
                    log.append(f"[{i}] 抓空：手眼偏移 {err_mm:.1f}mm "
                               f"> {act.get('grasp_tol', 15.0):.0f}mm")
                    return False
                bot.move_pose(plan.x, plan.y, plan.above_z)
                step(1.5)
                bot.move_pose(plan.x, plan.y, plan.grasp_z)
                step(1.5)
                bot.gripper(act.get("close", 0.15))
                step(0.5)
                gs = ct.GraspSpec(mass_kg=act.get("cube_mass", 0.05),
                                  mu=act.get("mu", 0.4),
                                  grip_force_n=act.get("grip_force", 4.0),
                                  cube_size_mm=act.get("cube_size", 40.0),
                                  max_opening_mm=act.get("max_opening", 42.0))
                meta["grasp"] = {
                    "capacity_n": round(gs.friction_capacity_n, 2),
                    "required_n": round(gs.required_n(), 2),
                    "holds": gs.holds(),
                }
                log.append(f"[{i}] grasp 摩擦 {gs.friction_capacity_n:.2f}N / "
                           f"需要 {gs.required_n():.2f}N")
                if not gs.fits():
                    log.append(f"[{i}] 方块 {gs.cube_size_mm:.0f}mm 超出夹爪开口 "
                               f"{gs.max_opening_mm:.0f}mm")
                    meta["grasp_slip"] = True
                    return False
                if not gs.holds():
                    log.append(f"[{i}] 抓取滑落（μ={gs.mu:.2f}）")
                    meta["grasp_slip"] = True
                    return False
                bot.move_pose(plan.x, plan.y, plan.above_z)   # 抬起
                step(1.5)

                # 运输加速度：超过摩擦锥就滑动/掉落，而不是"抓着飞"
                if act.get("transport_accel"):
                    gd = ct.GraspDynamics(gs, slip_limit_mm=act.get("slip_limit", 18.0))
                    for _ in range(max(1, int(act.get("transport_seconds", 1.0) / 0.01))):
                        gd.update(0.01, ay=float(act["transport_accel"]))
                    meta["contact"] = gd.to_dict()
                    log.append(f"[{i}] 接触 {gd.state} 滑移 {gd.slip_mm:.1f}mm "
                               f"Fz={gd.wrench.fz:.2f}N")
                    if gd.dropped:
                        log.append(f"[{i}] 运输滑落（a={act['transport_accel']}m/s²）")
                        meta["grasp_slip"] = True
                        return False
                return True

            def drop():
                bot.gripper(1.0)
                step(0.8)
                return True

            standoff = float(act.get("standoff", 0.0))
            nav_pick = (act["pick"][0] - standoff, act["pick"][1])
            r = ms.Mission(drive, look, pick, drop,
                           cfg=ms.MissionConfig(pick_xy=nav_pick,
                                                drop_xy=tuple(act["drop"])),
                           now=lambda: sim.time).run()
            meta["mission"] = r.as_dict()
            log.append(f"[{i}] mission {r.success} {r.seconds:.1f}s {r.reason}")
            if not r.success:
                failures.append(log[-1])
        elif cmd in ("nav", "nav_square"):
            cam = cs.Camera(width=act.get("cam_w", 320),
                            height=act.get("cam_h", 240),
                            cx=act.get("cam_w", 320) / 2,
                            cy=act.get("cam_h", 240) / 2,
                            x=act.get("cam_x", 0.0), y=act.get("cam_y", 0.0),
                            z=act.get("cam_z", 800.0), fx=act.get("fx", 300.0))

            cache = {"t": -1.0, "pose": None}

            def read_pose():
                if act.get("localize"):
                    # 相机按 10Hz 出图；控制环 50Hz 复用同一帧
                    bucket = round(sim.time * 10.0)
                    if cache["t"] == bucket and cache["pose"] is not None:
                        return cache["pose"]
                    m = cs.Marker(sim.chassis.x, sim.chassis.y, sim.chassis.yaw,
                                  color=tuple(act.get("marker_color", [200, 40, 200])),
                                  dot_color=tuple(act.get("dot_color", [0, 180, 220])))
                    img = cs.render(cam, [], markers=[m], seed=0,
                                    noise=0, texture=False)
                    p = cs.localize_marker(img, cam, m)
                    if p is not None:
                        cache["t"] = bucket
                        cache["pose"] = nv.Pose(*p)
                        return cache["pose"]
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

    expected_fail = bool(scene.get("expect_fail"))
    ok = bool(failures) if expected_fail else not failures
    return {"ok": ok, "failures": failures, "log": log, "expect_fail": expected_fail,
            "pose": [round(v, 2) for v in sim.pose()],
            "voltage": round(sim.voltage, 2), "time": round(sim.time, 2),
            "trace": trace}


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
