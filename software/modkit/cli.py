"""命令行入口：新手只需要记这几条。

    python -m modkit.cli scan  --sim             # 用仿真链路试试（不需要硬件）
    python -m modkit.cli scan  --port /dev/ttyUSB0
    python -m modkit.cli read  --port /dev/ttyUSB0 --id 1
    python -m modkit.cli home  --port /dev/ttyUSB0
    python -m modkit.cli pose  --sim --x 150 --y 0 --z 150
    python -m modkit.cli demo  --sim
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

from . import backlash as bl
from . import bench as bench
from . import calibrate as cal
from . import odomcal as oc
from . import qc as qc
from . import selftest as st
from . import speedcal as sc
from . import kinematics as kin
from . import nav as nv
from . import mission as ms
from . import telemetry as tm
from . import vision as vis
from . import protocol as p
from .bus import SerialLink, SimLink
from .robot import Robot


def _make_link(args):
    if args.sim:
        return SimLink(list(range(1, 7)))
    if not args.port:
        sys.exit("真机需要 --port /dev/ttyUSB0；想先试仿真加 --sim")
    return SerialLink(args.port, args.baud).open()


def cmd_scan(args) -> int:
    link = _make_link(args)
    bot = Robot(link)
    t0 = time.monotonic()
    ids = bot.scan()
    dt = (time.monotonic() - t0) * 1000
    print(f"扫描 0..20，用时 {dt:.0f}ms")
    if not ids:
        print("没有找到舵机。按顺序查：")
        print("  1) 12V 电源是否上电（量舵机端口）")
        print("  2) DATA 是否接在信号线而不是电源线")
        print("  3) 波特率 1M 是否与舵机一致")
        return 1
    print(f"找到 {len(ids)} 个：{ids}")
    for sid in ids:
        try:
            fb = bot.feedback(sid)
            print(f"  ID {sid}: {fb.position_deg:6.1f}°  {fb.voltage:4.1f}V  {fb.temp_c:2d}℃"
                  + (f"  故障: {fb.faults}" if fb.faults else ""))
        except Exception as e:
            print(f"  ID {sid}: 读反馈失败（{e}）")
    return 0


def cmd_read(args) -> int:
    link = _make_link(args)
    bot = Robot(link)
    fb = bot.feedback(args.id)
    print(f"ID {args.id}: 位置 {fb.position_deg:.1f}°  负载 {fb.load}  "
          f"电压 {fb.voltage:.1f}V  温度 {fb.temp_c}℃")
    if fb.faults:
        print(f"故障位: {fb.faults}")
    return 0


def cmd_home(args) -> int:
    link = _make_link(args)
    bot = Robot(link)
    ids = bot.scan()
    if not ids:
        print("总线上没有舵机，先跑 scan 排查")
        return 1
    print(f"卸力 → 同步回中位 180°：{ids}")
    bot.home_all(ids)
    time.sleep(1.0)
    for sid in ids:
        print(f"  ID {sid}: {bot.feedback(sid).position_deg:.1f}°")
    return 0


def cmd_pose(args) -> int:
    link = _make_link(args)
    bot = Robot(link)
    target = kin.Pose(args.x, args.y, args.z)
    try:
        yaw, sh, el = kin.inverse(bot.arm, target)
    except kin.UnreachableError as e:
        print(f"到不了 ({args.x}, {args.y}, {args.z})：{e}")
        print(f"工作空间：半径 {bot.arm.reach_min:.0f}–{bot.arm.reach_max:.0f}mm，"
              f"高度 {bot.arm.base_h:.0f}–{bot.arm.base_h + bot.arm.reach_max:.0f}mm")
        return 2
    print(f"逆解：偏航 {yaw:.1f}°  肩 {sh:.1f}°  肘 {el:.1f}°")
    if args.sim:
        print("（仿真：只算不动）")
        return 0
    bot.move_pose(args.x, args.y, args.z, speed=args.speed)
    print("已下发同步指令")
    return 0


def cmd_demo(args) -> int:
    link = _make_link(args)
    bot = Robot(link)
    ids = bot.scan()
    print(f"找到 {len(ids)} 个舵机：{ids}")
    print("演示：逐个使能 → 小角度摆动 → 卸力（5A 电源也能安全跑）")
    for sid in ids[: args.max_joints]:
        bot.set_torque(sid, True)
        for deg in (170, 190, 180):
            bot.goto(sid, deg, speed=300, acc=20)
            time.sleep(0.4)
            print(f"  ID {sid} → {deg}°  实测 {bot.feedback(sid).position_deg:.1f}°")
        bot.set_torque(sid, False)
    print("完成。真机上请确认没有卡到东西再重复。")
    return 0


def cmd_calib(args) -> int:
    """标定向导：零位/方向/限位/验证。仿真先跑通再上真机。"""
    link = _make_link(args)
    bot = Robot(link)

    if args.action == "scan":
        ids = cal.scan_joints(bot, expected=args.expect)
        for sid in ids:
            print(f"  ID {sid}: {cal.probe(bot, sid)}")
        return 0

    if args.action == "probe":
        print(cal.probe(bot, args.id))
        return 0

    if args.action == "limits":
        lo, hi = cal.find_limits(bot, args.id, lo=args.lo, hi=args.hi,
                                 step=args.step, settle=args.settle)
        print(f"ID {args.id}: tick 范围 {lo}..{hi}  （{lo * p.DEG_PER_TICK:.1f}°..{hi * p.DEG_PER_TICK:.1f}°）")
        print(f"  建议限位：min_deg={lo * p.DEG_PER_TICK:.1f}  max_deg={hi * p.DEG_PER_TICK:.1f}")
        return 0

    if args.action == "zero":
        ticks = cal.set_zero(bot, args.id, deg=args.deg)
        c = cal.Calibration()
        if args.save and pathlib.Path(args.save).exists():
            c = cal.Calibration.load(args.save)
        c.add(cal.Joint(name=args.name, servo_id=args.id, zero_ticks=ticks,
                        dir=args.dir, min_deg=args.min, max_deg=args.max))
        out = c.save(args.save or "calibration.json")
        print(f"零位：ID {args.id} 在 {args.deg}° 时 tick={ticks}；已写入 {out}")
        return 0

    if args.action == "verify":
        c = cal.Calibration.load(args.file)
        rows = []
        for name, j in c.joints.items():
            rows += [(name, r) for r in cal.verify(bot, j, tol_deg=args.tol)]
            print(f"  {name}: 通过")
        for name, r in rows:
            print(f"    {name:10s} 目标 {r['want']:7.1f}  实测 {r['got']:7.1f}  误差 {r['err']:.2f}")
        return 0

    if args.action == "report":
        c = cal.Calibration.load(args.file)
        print(f"{c.robot}  标定时间 {c.created}")
        print(f"{'关节':<10}{'ID':>4}{'零位tick':>9}{'方向':>5}{'下限':>8}{'上限':>8}")
        for name, j in c.joints.items():
            print(f"{name:<10}{j.servo_id:>4}{j.zero_ticks:>9}{j.dir:>5}{j.min_deg:>8.1f}{j.max_deg:>8.1f}")
        return 0

    raise SystemExit(f"未知动作 {args.action}")


def cmd_qc(args) -> int:
    if args.action == "new":
        serial = args.serial or qc.next_serial(args.dir)
        q1, q2 = qc.default_checks()
        rec = qc.Record(serial=serial, operator=args.operator or "未填", q1=q1, q2=q2)
        path = rec.save(args.dir)
        print(f"已建记录 {path}")
        print("下一步：把 q1/q2 的 ok 改成 true，填 grasp_success 等，再 --action validate")
        return 0

    if args.action == "show":
        r = qc.Record.load(args.file)
        print(f"{r.serial}  {r.date}  装配 {r.operator}  结论 {r.conclusion}")
        for c in r.q1:
            print(f"  Q1 [{'✓' if c.ok else ' '}] {c.name}")
        for c in r.q2:
            print(f"  Q2 [{'✓' if c.ok else ' '}] {c.name}")
        print(f"  Q3 抓放 {r.grasp_success}/{r.grasp_total}  重复 {r.repeatability_mm}mm  "
              f"温升 {r.temp_c}℃  续航 {r.runtime_min}min")
        return 0

    if args.action == "validate":
        bad = 0
        for pth in args.file:
            r = qc.Record.load(pth)
            errs = r.validate()
            if errs:
                bad += 1
                print(f"✗ {r.serial}")
                for e in errs:
                    print(f"    - {e}")
            else:
                print(f"✓ {r.serial}")
        return 1 if bad else 0

    if args.action == "summary":
        print(qc.summary(args.file))
        return 0

    raise SystemExit(f"未知动作 {args.action}")


def cmd_bench(args) -> int:
    link = _make_link(args)
    bot = Robot(link)
    if args.action == "repeat":
        r = bench.repeatability(bot, args.x, args.y, args.z, n=args.n)
        print(f"目标 {r['target']}  均值 {r['mean']}  离散 {r['span_mm']}mm  "
              f"{'通过' if r['ok'] else '超差（限 2mm）'}")
        return 0 if r["ok"] else 1

    if args.action == "burnin":
        log = bench.BenchLog(pathlib.Path(args.csv))
        r = bench.burn_in(bot, minutes=args.minutes, cycle_s=args.cycle,
                          limit_c=args.limit, log=log)
        print(f"循环 {r['cycles']} 次 / {r['duration_s']}s，最高温 {r['max_temp_c']}℃")
        if r["stopped"]:
            print(f"中止：{r['stopped']}")
        print(f"CSV：{args.csv}")
        return 0 if r["ok"] else 1

    raise SystemExit(f"未知动作 {args.action}")


def cmd_selftest(args) -> int:
    link = _make_link(args)
    bot = Robot(link)
    expect = [int(x) for x in args.expect.split(",") if x.strip()]
    rep = st.selftest(bot, expect, amp=args.amp, tol=args.tol, settle=args.settle)
    print(f"{'ID':>3} {'关节':<10}{'结果':<6}{'到位误差':>10}{'温度':>6}")
    for s in rep.steps:
        mark = "✓" if s.ok else "✗"
        print(f"{s.sid:>3} {s.name:<10}{mark:<6}{s.detail:>10}{s.temp_c:>5}℃")
    path = rep.save(args.json)
    print(f"\n{'通过' if rep.ok else '未通过'}；记录 {path}")
    if rep.stopped:
        print(f"中止原因：{rep.stopped}")
    return 0 if rep.ok else 1


def cmd_odomcal(args) -> int:
    cal = oc.OdomCal.load(args.file) if pathlib.Path(args.file).exists() else oc.OdomCal()
    if args.action == "straight":
        pred = cal.predicted_distance(args.ticks)
        sc = cal.apply_straight(args.ticks, args.distance)
        print(f"直线标定：理论 {pred:.1f}mm，实测 {args.distance:.1f}mm → scale {sc:.4f}")
    else:
        sc = cal.apply_turn(args.left_ticks, args.right_ticks, args.deg)
        print(f"转向标定：scale {sc:.4f}")
    print(cal.summary())
    cal.save(args.file)
    print(f"已写入 {args.file}")
    return 0


def cmd_backlash(args) -> int:
    link = _make_link(args)
    bot = Robot(link)
    if args.action == "measure":
        jp = bl.measure(bot, args.id, center=args.center, span=args.span,
                        settle=args.settle, name=args.name)
        print(f"ID{jp.sid} {jp.name or ''} 回差 {jp.play_deg}°"
              f"（{jp.play_ticks:.0f} tick）{'  ← 偏大，先查机械' if not jp.ok else ''}")
        out = pathlib.Path(args.file)
        data = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
        data[str(jp.sid)] = jp.play_deg
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写入 {out}（可直接给 Compensator.load 用）")
        return 0 if jp.ok else 1
    raise SystemExit("未知动作")


def cmd_speedcal(args) -> int:
    link = SimLink(list(range(1, 7)), wheels=True) if args.sim else _make_link(args)
    bot = Robot(link)
    try:
        r = sc.measure(bot, args.sid, args.lsb, args.seconds, args.hz)
    finally:
        try:
            bot.set_speed_raw(args.sid, 0)
        except Exception:
            pass
    print(json.dumps(r.as_dict(), ensure_ascii=False, indent=2))
    if r.note:
        print(r.note)
    if args.save and r.ok:
        out = pathlib.Path(args.save)
        out.write_text(json.dumps({"speed_unit": round(r.unit, 4),
                                   "wheel_sid": r.sid}, indent=2), encoding="utf-8")
        print(f"已写入 {out}")
    return 0 if r.ok else 1


def cmd_record(args) -> int:
    link = _make_link(args)
    bot = Robot(link)
    ids = [int(v) for v in args.ids.split(",")]
    path, n = tm.record(bot, ids, args.seconds, args.hz, args.out)
    sm = tm.summarize(tm.read_log(path))
    print(f"已记录 {n} 条 → {path}")
    print(f"电压 {sm['v_min']}–{sm['v_max']}V，最高温 {sm['t_max']}℃，"
          f"故障 {sm['faults']} 条")
    return 0


def cmd_replay(args) -> int:
    try:
        samples = tm.read_log(args.log)
    except FileNotFoundError:
        sys.exit(f"没有这个日志：{args.log}")
    sm = tm.summarize(samples)
    if args.json:
        out = pathlib.Path(args.json)
        out.write_text(json.dumps(sm, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写入 {out}")
    else:
        print(json.dumps(sm, ensure_ascii=False, indent=2))
    pct, state = tm.battery(sm.get("v_end", 12.0))
    print(f"末电压 {sm.get('v_end')}V ≈ {pct:.0f}%（{state}）")
    return 0


def cmd_mission(args) -> int:
    if not args.sim:
        sys.exit("任务会真动；先 --sim 验证流程，真机版本等硬件到位再放开")

    class SimWorld:
        def __init__(self, cubes):
            self.p = nv.Pose()
            self.t = 0.0
            self.held = False
            self.cubes = [nv.Pose(x, y) for x, y in cubes]

        def now(self):
            return self.t

        def drive(self, x, y, theta):
            r = nv.drive_to(self.p, nv.Pose(x, y, theta))
            self.t += r.seconds
            self.p = r.final
            return r.ok

        def look(self):
            self.t += 0.5
            if any(self.p.distance_to(c) < 20 for c in self.cubes):
                return vis.Detection(160, 120, 1600, (140, 100, 179, 139))
            return None

        def pick(self, det):
            self.t += 4.0
            self.held = True
            return True

        def drop(self):
            self.t += 2.0
            self.held = False
            return True

    if args.tasks:
        tasks = []
        for chunk in args.tasks.split(";"):
            if not chunk.strip():
                continue
            v = [float(x) for x in chunk.split(",")]
            if len(v) != 4:
                sys.exit("--tasks 格式：pick_x,pick_y,drop_x,drop_y;...")
            tasks.append(((v[0], v[1]), (v[2], v[3])))
        w = SimWorld([p for p, _ in tasks])
        res = ms.run_tasks(w.drive, w.look, w.pick, w.drop, tasks,
                           now=w.now, total_seconds=args.max_seconds)
        for r in res["results"]:
            print(f"  任务 {r['task']}: {'OK' if r['success'] else 'FAIL'}"
                  f"（{r.get('reason', '')}，{r.get('seconds', 0)}s）")
        print(f"{'PASS' if res['success'] else 'FAIL'}：{res['tasks']} 个任务，"
              f"{res['seconds']}s")
        pathlib.Path(args.out).write_text(
            json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写入 {args.out}")
        return 0 if res["success"] else 1

    w = SimWorld([args.pick])
    cfg = ms.MissionConfig(pick_xy=args.pick, drop_xy=args.drop,
                           max_seconds=args.max_seconds)
    r = ms.Mission(w.drive, w.look, w.pick, w.drop, cfg=cfg, now=w.now).run()
    for st in r.states:
        print(f"  {st}")
    print(f"{'PASS' if r.success else 'FAIL'}：{r.reason}，"
          f"{r.seconds:.1f}s，动作 {r.attempts} 次")
    out = pathlib.Path(args.out)
    out.write_text(json.dumps(r.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入 {out}")
    return 0 if r.success else 1


def cmd_pick(args) -> int:
    if not args.sim:
        sys.exit("抓取会真动，先 --sim 验证点位；真机请手动示教确认后再放开")
    det = vis.detect_color(vis.load_rgb(args.image),
                           tuple(int(v) for v in args.target.split(",")),
                           tol=args.tol, min_area=args.min_area)
    if det is None:
        print("没找到目标")
        return 1
    cal = vis.load_calib(args.calib)
    try:
        plan = vis.plan_pick(cal, det, kin.ArmGeometry(),
                             z_table=args.z_table, clearance=args.clearance,
                             grasp_z=args.grasp_z)
    except kin.UnreachableError as e:
        print(f"够不到：{e}")
        return 1
    print(f"目标 ({plan.x:.1f}, {plan.y:.1f})mm，"
          f"上方 z={plan.above_z:.0f}，抓取 z={plan.grasp_z:.0f}")
    link = _make_link(args)
    bot = Robot(link)
    bot.move_pose(plan.x, plan.y, plan.above_z)
    bot.move_pose(plan.x, plan.y, plan.grasp_z)
    bot.gripper(args.close)
    bot.move_pose(plan.x, plan.y, plan.above_z)
    print("序列完成：上方 → 下降 → 闭合 → 抬起")
    return 0


def cmd_vision(args) -> int:
    try:
        img = vis.load_rgb(args.image)
    except Exception as e:
        sys.exit(f"读图失败：{e}")
    target = tuple(int(v) for v in args.target.split(","))
    det = vis.detect_color(img, target, tol=args.tol, min_area=args.min_area)
    if det is None:
        print(f"没找到颜色 {target}（tol={args.tol}, min_area={args.min_area}）")
        return 1
    print(f"色块：中心 ({det.cx:.1f}, {det.cy:.1f})px，面积 {det.area}px，"
          f"尺寸 {det.size[0]}×{det.size[1]}px")
    if not args.calib:
        return 0
    cal = vis.load_calib(args.calib)
    x, y = cal.apply(det.cx, det.cy)
    print(f"桌面：({x:.1f}, {y:.1f})mm")
    if args.plan:
        try:
            plan = vis.plan_pick(cal, det, kin.ArmGeometry(),
                                 z_table=args.z_table, clearance=args.clearance,
                                 grasp_z=args.grasp_z)
        except kin.UnreachableError as e:
            print(f"够不到：{e}")
            return 1
        print(json.dumps(plan.as_dict(), ensure_ascii=False, indent=2))
    return 0


def cmd_drive(args) -> int:
    link = _make_link(args)
    bot = Robot(link)
    print(f"轮速 v={args.v}mm/s w={args.w}°/s，{args.seconds}s（真机请先确认方向）")
    bot.drive_speed(args.v, args.w)
    try:
        time.sleep(args.seconds)
    finally:
        bot.stop_wheels()
    if hasattr(link, "pose"):
        print("仿真位姿", tuple(round(v, 1) for v in link.pose()))
    return 0


def cmd_nav(args) -> int:
    if args.closed_loop:
        if not args.sim:
            sys.exit("真机的轮速单位/方向还没标定（docs/06 G7），先加 --sim 跑闭环")
        from .bus import SimLink
        link = SimLink(list(range(1, 7)), wheels=True)
        bot = Robot(link)

        def read_pose():
            o = bot.update_odom()
            return nv.Pose(o.x, o.y, o.yaw)

        def set_speed(v, w):
            bot.drive_speed(v, w)

        if args.path == "square":
            wps = nv.square_waypoints(args.size)
        elif args.path == "line":
            wps = [nv.Pose(args.size, 0.0, 0.0)]
        else:
            wps = []
            for chunk in args.wp.split(";"):
                if chunk.strip():
                    wps.append(nv.Pose(*[float(v) for v in chunk.split(",")]))
        print(f"{'段':>2}  {'目标':>18}  {'用时':>6}  {'误差':>12}  结果")
        legs = []
        for i, wp in enumerate(wps, 1):
            r = nv.navigate(read_pose, set_speed, wp, dt=args.dt)
            legs.append((wp, r))
            print(f"{i:>2}  ({wp.x:6.0f},{wp.y:6.0f},{wp.theta:5.0f}°)  "
                  f"{r.seconds:6.1f}s  {r.error_mm:6.1f}mm {r.error_deg:5.1f}°  "
                  f"{'OK' if r.ok else 'FAIL'}")
        ok = all(r.ok for _, r in legs)
        print(f"终点 ({legs[-1][1].final.x:.1f}, {legs[-1][1].final.y:.1f}, "
              f"{nv.wrap(legs[-1][1].final.theta):.1f}°)，{'全部到达' if ok else '未完成'}")
        return 0 if ok else 1

    if args.path == "square":
        wps = nv.square_waypoints(args.size)
    elif args.path == "line":
        wps = [nv.Pose(args.size, 0.0, 0.0)]
    else:
        wps = []
        for chunk in args.wp.split(";"):
            if not chunk.strip():
                continue
            parts = [float(v) for v in chunk.split(",")]
            if len(parts) != 3:
                sys.exit("--wp 格式：x,y,theta;x,y,theta")
            wps.append(nv.Pose(*parts))
        if not wps:
            sys.exit("--path custom 需要 --wp")
    start = nv.Pose(*[float(v) for v in args.start.split(",")])
    legs, ok = nv.follow(start, wps, dt=args.dt)
    print(f"{'段':>2}  {'目标':>18}  {'用时':>6}  {'误差':>12}  结果")
    for i, r in enumerate(legs, 1):
        g = wps[i - 1]
        print(f"{i:>2}  ({g.x:6.0f},{g.y:6.0f},{g.theta:5.0f}°)  "
              f"{r.seconds:6.1f}s  {r.error_mm:6.1f}mm {r.error_deg:5.1f}°  "
              f"{'OK' if r.ok else 'FAIL'}")
    last = legs[-1].final
    print(f"终点 ({last.x:.1f}, {last.y:.1f}, {nv.wrap(last.theta):.1f}°)，"
          f"{'全部到达' if ok else '未完成'}")
    out = pathlib.Path(args.out)
    out.write_text(json.dumps({
        "ok": ok, "start": [start.x, start.y, start.theta],
        "legs": [{"goal": [w.x, w.y, w.theta], "final": [r.final.x, r.final.y, r.final.theta],
                  "seconds": round(r.seconds, 2), "error_mm": round(r.error_mm, 2),
                  "error_deg": round(r.error_deg, 2), "ok": r.ok} for w, r in zip(wps, legs)],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入 {out}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="modkit", description="modkit 机器人命令行")
    ap.add_argument("--port", help="串口，如 /dev/ttyUSB0 或 COM3")
    ap.add_argument("--baud", type=int, default=1_000_000)
    ap.add_argument("--sim", action="store_true", help="使用仿真链路（不需要硬件）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("scan", help="扫描并读取所有舵机").set_defaults(func=cmd_scan)

    r = sub.add_parser("read", help="读单个舵机")
    r.add_argument("--id", type=int, required=True)
    r.set_defaults(func=cmd_read)

    sub.add_parser("home", help="全部回中位 180°").set_defaults(func=cmd_home)

    pz = sub.add_parser("pose", help="末端到点（自动逆解）")
    pz.add_argument("--x", type=float, required=True)
    pz.add_argument("--y", type=float, required=True)
    pz.add_argument("--z", type=float, required=True)
    pz.add_argument("--speed", type=int, default=300)
    pz.set_defaults(func=cmd_pose)

    d = sub.add_parser("demo", help="逐个关节小角度摆动")
    d.add_argument("--max-joints", type=int, default=4)
    d.set_defaults(func=cmd_demo)

    cb = sub.add_parser("calib", help="标定向导（零位/方向/限位/验证）")
    cb.add_argument("--action", required=True,
                    choices=["scan", "probe", "limits", "zero", "verify", "report"])
    cb.add_argument("--id", type=int)
    cb.add_argument("--name", default="yaw")
    cb.add_argument("--deg", type=float, default=0.0)
    cb.add_argument("--dir", type=int, choices=[1, -1], default=1)
    cb.add_argument("--min", type=float, default=0.0)
    cb.add_argument("--max", type=float, default=180.0)
    cb.add_argument("--lo", type=float, default=0.0)
    cb.add_argument("--hi", type=float, default=180.0)
    cb.add_argument("--step", type=float, default=10.0)
    cb.add_argument("--settle", type=float, default=0.2)
    cb.add_argument("--tol", type=float, default=2.0)
    cb.add_argument("--expect", type=int, default=6)
    cb.add_argument("--file", default="calibration.json")
    cb.add_argument("--save", default="calibration.json")
    cb.set_defaults(func=cmd_calib)

    q = sub.add_parser("qc", help="生产记录：序列号/质检/汇总")
    q.add_argument("--action", required=True, choices=["new", "show", "validate", "summary"])
    q.add_argument("--serial", default="")
    q.add_argument("--operator", default="")
    q.add_argument("--dir", default="records")
    q.add_argument("--file", nargs="+", default=[])
    q.set_defaults(func=cmd_qc)

    bn = sub.add_parser("bench", help="台架测试：重复精度/连续运行")
    bn.add_argument("--action", required=True, choices=["repeat", "burnin"])
    bn.add_argument("--n", type=int, default=10)
    bn.add_argument("--x", type=float, default=180.0)
    bn.add_argument("--y", type=float, default=0.0)
    bn.add_argument("--z", type=float, default=120.0)
    bn.add_argument("--minutes", type=float, default=1.0)
    bn.add_argument("--cycle", type=float, default=2.0)
    bn.add_argument("--limit", type=float, default=55.0)
    bn.add_argument("--csv", default="bench.csv")
    bn.set_defaults(func=cmd_bench)

    stp = sub.add_parser("selftest", help="新机自检：在线/温度/运动/到位")
    stp.add_argument("--expect", default="1,2,3,4,5,6")
    stp.add_argument("--amp", type=float, default=5.0)
    stp.add_argument("--tol", type=float, default=1.5)
    stp.add_argument("--settle", type=float, default=0.25)
    stp.add_argument("--json", default="selftest.json")
    stp.set_defaults(func=cmd_selftest)

    od = sub.add_parser("odomcal", help="里程计标定（轮径/轮距）")
    od.add_argument("--action", required=True, choices=["straight", "turn"])
    od.add_argument("--ticks", type=float, default=0.0)
    od.add_argument("--distance", type=float, default=1000.0)
    od.add_argument("--left-ticks", type=float, default=0.0)
    od.add_argument("--right-ticks", type=float, default=0.0)
    od.add_argument("--deg", type=float, default=90.0)
    od.add_argument("--file", default="odomcal.json")
    od.set_defaults(func=cmd_odomcal)

    blp = sub.add_parser("backlash", help="回差测量（换向补偿用）")
    blp.add_argument("--action", required=True, choices=["measure"])
    blp.add_argument("--id", type=int, default=1)
    blp.add_argument("--name", default="")
    blp.add_argument("--center", type=float, default=180.0)
    blp.add_argument("--span", type=float, default=10.0)
    blp.add_argument("--settle", type=float, default=0.35)
    blp.add_argument("--file", default="backlash.json")
    blp.set_defaults(func=cmd_backlash)

    nvp = sub.add_parser("nav", help="导航到点（控制器 + 理想单轮车验证）")
    nvp.add_argument("--path", default="square", choices=["square", "line", "custom"])
    nvp.add_argument("--size", type=float, default=300.0)
    nvp.add_argument("--wp", default="")
    nvp.add_argument("--start", default="0,0,0")
    nvp.add_argument("--dt", type=float, default=0.02)
    nvp.add_argument("--out", default="nav_sim.json")
    nvp.add_argument("--closed-loop", action="store_true",
                     help="用里程计反馈闭环（目前仅 --sim）")
    nvp.set_defaults(func=cmd_nav)

    spc = sub.add_parser("speedcal", help="标定速度寄存器 1 LSB = ? deg/s")
    spc.add_argument("--sid", type=int, default=5)
    spc.add_argument("--lsb", type=int, default=500)
    spc.add_argument("--seconds", type=float, default=1.0)
    spc.add_argument("--hz", type=float, default=50.0)
    spc.add_argument("--save", help="把 speed_unit 存成 JSON")
    spc.set_defaults(func=cmd_speedcal)

    rc = sub.add_parser("record", help="记录舵机反馈到 CSV")
    rc.add_argument("--ids", default="1,2,3,4")
    rc.add_argument("--seconds", type=float, default=3.0)
    rc.add_argument("--hz", type=float, default=5.0)
    rc.add_argument("--out", default="telemetry.csv")
    rc.set_defaults(func=cmd_record)

    rp = sub.add_parser("replay", help="回放/汇总 CSV 日志")
    rp.add_argument("--log", required=True)
    rp.add_argument("--json", help="另存汇总 JSON")
    rp.set_defaults(func=cmd_replay)

    mp = sub.add_parser("mission", help="M4 任务状态机（目前仅 --sim）")
    mp.add_argument("--pick", type=lambda s: tuple(float(v) for v in s.split(",")),
                    default=(200.0, 0.0))
    mp.add_argument("--drop", type=lambda s: tuple(float(v) for v in s.split(",")),
                    default=(-150.0, 0.0))
    mp.add_argument("--max-seconds", type=float, default=180.0)
    mp.add_argument("--tasks", help="多任务：pick_x,pick_y,drop_x,drop_y;...")
    mp.add_argument("--out", default="mission.json")
    mp.set_defaults(func=cmd_mission)

    pk = sub.add_parser("pick", help="识图 → 抓取序列（目前仅 --sim）")
    pk.add_argument("--image", required=True)
    pk.add_argument("--target", required=True)
    pk.add_argument("--calib", required=True)
    pk.add_argument("--tol", type=int, default=50)
    pk.add_argument("--min-area", type=int, default=200)
    pk.add_argument("--z-table", type=float, default=0.0)
    pk.add_argument("--clearance", type=float, default=60.0)
    pk.add_argument("--grasp-z", type=float, default=25.0)
    pk.add_argument("--close", type=float, default=0.15, help="夹爪闭合量 0..1")
    pk.set_defaults(func=cmd_pick)

    vp = sub.add_parser("vision", help="色块检测 → 桌面坐标 → 抓取逆解")
    vp.add_argument("--image", required=True)
    vp.add_argument("--target", required=True, help="R,G,B，如 200,60,40")
    vp.add_argument("--tol", type=int, default=50)
    vp.add_argument("--min-area", type=int, default=200)
    vp.add_argument("--calib", help="四点标定 JSON")
    vp.add_argument("--plan", action="store_true", help="输出抓取位姿与关节角")
    vp.add_argument("--z-table", type=float, default=0.0)
    vp.add_argument("--clearance", type=float, default=60.0)
    vp.add_argument("--grasp-z", type=float, default=25.0)
    vp.set_defaults(func=cmd_vision)

    dv = sub.add_parser("drive", help="轮子恒速（真机/仿真）")
    dv.add_argument("--v", type=float, default=100.0, help="mm/s")
    dv.add_argument("--w", type=float, default=0.0, help="deg/s")
    dv.add_argument("--seconds", type=float, default=2.0)
    dv.set_defaults(func=cmd_drive)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())