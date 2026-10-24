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
import sys
import time

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

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())