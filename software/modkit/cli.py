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
import pathlib
import sys
import time

from . import bench as bench
from . import calibrate as cal
from . import qc as qc
from . import selftest as st
from . import kinematics as kin
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

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())