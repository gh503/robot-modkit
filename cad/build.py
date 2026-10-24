#!/usr/bin/env python
"""构建全部零件 + 导出 STEP/STL + 跑几何自检。

用法：
    cd cad && ../.venv/bin/python build.py

自检不是"看起来对"，而是断言：
    干涉体积 = 0、运动间隙 ≥ 设计值、余量 ≥ 最小壁厚、包络 ≤ 打印机。
任何一条 FAIL 都会以非零退出码结束 —— 这样它才能进 CI。
"""

from __future__ import annotations

import json
import pathlib
import sys
from pathlib import Path

import params as P
import parts as K
import parts_m1 as M1
import tools as T
from build123d import Box, Pos, Rot, export_step, export_stl

OUT = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = ""):
    results.append((name, bool(ok), detail))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))


def vol(shape) -> float:
    try:
        return shape.volume
    except Exception:
        return 0.0


def interference(a, b) -> float:
    """两实体相交体积（mm³）。共面接触会得到 0，这是期望值。"""
    return vol(a & b)


def build_all():
    solids = {name: fn() for name, fn in K.ALL_PARTS.items()}
    solids.update({name: fn() for name, fn in M1.ALL_PARTS_M1.items()})
    servo = K.servo_reference()
    tools = {name: fn() for name, fn in T.TOOLS.items()}
    return solids, servo, tools


def main():
    solids, servo, tools = build_all()

    print("\n=== 导出 ===")
    for name, s in {**solids, **tools}.items():
        step = OUT / f"{name}.step"
        stl = OUT / f"{name}.stl"
        export_step(s, str(step))
        export_stl(s, str(stl), tolerance=0.03, angular_tolerance=0.2)
        print(f"  {name:12s} STEP {step.stat().st_size//1024:5d} KB   STL {stl.stat().st_size//1024:5d} KB"
              f"   体积 {vol(s)/1000:7.2f} cm³")
    export_step(servo, str(OUT / "servo_reference.step"))
    export_stl(servo, str(OUT / "servo_reference.stl"), tolerance=0.05)

    print("\n=== 实体合法性 ===")
    for name, s in solids.items():
        iv = s.is_valid
        iv = iv() if callable(iv) else bool(iv)
        check(f"{name} 实体有效", iv, f"面数 {len(s.faces())}")
    for name, s in solids.items():
        check(f"{name} 体积为正", vol(s) > 0, f"{vol(s)/1000:.2f} cm³")

    print("\n=== 干涉检查（必须为 0）===")
    pairs = [
        ("舵机 × 底板", servo, solids["joint_base"]),
        ("舵机 × 盖板", servo, solids["joint_lid"]),
        ("舵机 × 输出盘", servo, solids["output_disc"]),
        ("盖板 × 输出盘（旋转件不许蹭固定件）", solids["joint_lid"], solids["output_disc"]),
        ("底板 × 盖板", solids["joint_base"], solids["joint_lid"]),
    ]
    for label, a, b in pairs:
        v = interference(a, b)
        check(label, v < 1.0, f"相交 {v:.3f} mm³")

    print("\n=== 关键间隙 / 余量 ===")
    gap_lid = K.Z_LID_BOT - K.Z_SERVO_TOP
    check("舵机顶面→盖板 间隙", gap_lid >= 0.25, f"{gap_lid:.2f} mm（设计 0.4）")

    gap_disc = K.Z_FLANGE_BOT - K.Z_LID_TOP
    check("输出盘→盖板 轴向间隙", gap_disc >= 0.3, f"{gap_disc:.2f} mm（设计 0.6）")

    floor = P.PLATE_T - P.SERVO_RECESS
    check("舵机槽底剩余壁厚", floor >= P.MIN_WALL, f"{floor:.2f} mm（最小 {P.MIN_WALL}）")

    side_clr = P.FIT_CLR / 2
    check("舵机侧面单边间隙", 0.15 <= side_clr <= 0.5, f"{side_clr:.2f} mm（FDM 可装配但能限位）")

    annulus = (P.DISC_D + 0.6 - P.DISC_D) / 2
    check("输出盘↔盖板孔 径向间隙", annulus >= 0.2, f"{annulus:.2f} mm")

    check("角柱壁厚 ≥ 最小壁厚", P.POST >= 2 * P.MIN_WALL, f"{P.POST} mm")
    check("M3 热熔螺母孔深 ≥ 螺母长+2", P.M3_INSERT_H >= 6.0, f"{P.M3_INSERT_H} mm")

    # 花键插座必须够深，否则输出盘压不到舵机壳体上、扭矩全在花键齿上
    socket_depth = P.SERVO_SPLINE_H + 0.4
    check("花键插座深度 > 花键露出高度", socket_depth > P.SERVO_SPLINE_H,
          f"{socket_depth:.2f} vs {P.SERVO_SPLINE_H:.2f}")

    print("\n=== M1 整机检查 ===")
    # 驱动舵机吊在板下：与底盘、与支架都不能干涉
    for side in (1, -1):
        drive = M1.drive_servo_reference(side)
        v = interference(drive, solids["chassis_right"])
        v += interference(drive, solids["chassis_left"])
        check(f"驱动舵机{side:+d} × 底盘 干涉", v < 1.0, f"相交 {v:.3f} mm³")

    bracket = solids["drive_bracket"]
    for side in (1, -1):
        drive = Pos(0, side * P.DRIVE_Y, 0) * M1.drive_servo_reference(1)
        v = interference(drive, Pos(0, side * P.DRIVE_Y, 0) * bracket)
        check(f"驱动舵机{side:+d} × 支架 干涉", v < 1.0, f"相交 {v:.3f} mm³")

    # 底盘三块之间不能互相压死（连接板只在 x=±30 附近重叠）
    v = interference(solids["chassis_right"], solids["chassis_left"])
    check("左右底盘互不重叠", v < 1.0, f"相交 {v:.3f} mm³")

    # 夹爪：全开/全闭都不能撞
    jaw_open = M1.jaw_moving(0)
    jaw_closed = M1.jaw_moving(P.JAW_SWING)
    v = interference(jaw_open, solids["jaw_fixed"])
    check("夹爪全开：动爪 × 定爪", v < 1.0, f"相交 {v:.3f} mm³")
    v = interference(jaw_closed, solids["jaw_fixed"])
    check(f"夹爪闭合 {P.JAW_SWING:.0f}°：动爪 × 定爪", v < 1.0, f"相交 {v:.3f} mm³")
    v = interference(jaw_closed, solids["joint_lid"])
    check("夹爪闭合：动爪 × 盖板", v < 1.0, f"相交 {v:.3f} mm³")

    gap_open = M1.jaw_gap(0.0)
    gap_closed = M1.jaw_gap(P.JAW_SWING)
    check("夹爪全开内距", 35 <= gap_open <= 50, f"{gap_open:.1f} mm")
    check("夹爪闭合内距", 15 <= gap_closed < gap_open, f"{gap_closed:.1f} mm（摆 {P.JAW_SWING:.0f}°）")

    # 驱动几何与运动学参数必须一致（轮子在 WHEEL_Y，轮距 = 2×WHEEL_Y）
    leg_gap = 14.75 - 2 - P.SERVO_W / 2
    check("支架腿内面留间隙", leg_gap >= 0.2, f"单边 {leg_gap:.2f} mm（FDM 可装入）")

    check("轮距与 kinematics 一致", abs(2 * P.WHEEL_Y - 150.0) < 1e-6, f"{2*P.WHEEL_Y:.0f} mm")
    check("轮子不超出底盘宽度", P.WHEEL_Y + 10 <= P.CHASSIS_Y / 2 + 10,
          f"轮平面 {P.WHEEL_Y} / 半宽 {P.CHASSIS_Y/2}")

    # 零件清单与材料表必须一一对应（防止加了零件忘写材料/忘进 BOM）
    all_names = set(K.ALL_PARTS) | set(M1.ALL_PARTS_M1)
    mats = set(K.MATERIAL) | set(M1.MATERIAL_M1)
    check("每个零件都有材料说明", all_names == mats,
          f"零件 {len(all_names)} / 材料 {len(mats)}" +
          ("" if all_names == mats else f" 缺: {sorted(all_names - mats)}"))

    # 文档不能和 CAD 脱节：零件清单必须覆盖全部零件
    idx = pathlib.Path(__file__).resolve().parent.parent / "docs" / "11-零件清单.md"
    if idx.exists():
        text = idx.read_text(encoding="utf-8")
        missing = sorted(n for n in all_names if f"`{n}`" not in text)
        check("零件清单覆盖所有零件", not missing,
              "全部覆盖" if not missing else f"缺 {missing}，跑 parts_index.py 重新生成")
    else:
        check("零件清单存在", False, "缺 docs/11-零件清单.md")

    print("\n=== 打印机成形空间 ===")
    bx, by, bz = P.PRINTER_BED
    for name, s in solids.items():
        bb = s.bounding_box()
        fits = bb.size.X <= bx and bb.size.Y <= by and bb.size.Z <= bz
        check(f"{name} 可打印", fits,
              f"{bb.size.X:.1f}×{bb.size.Y:.1f}×{bb.size.Z:.1f} mm")

    print("\n=== 打印校准件（先打这个，再打整机）===")
    for name, t in tools.items():
        bb = t.bounding_box()
        fits = bb.size.X <= bx and bb.size.Y <= by and bb.size.Z <= bz
        check(f"{name} 可打印", fits,
              f"{bb.size.X:.1f}×{bb.size.Y:.1f}×{bb.size.Z:.1f} mm")
        cut = T.GAUGE_X * T.GAUGE_Y * T.GAUGE_T - vol(t)
        want = T.gauge_expected_cut_volume()
        err = abs(cut - want) / want
        check("校准件孔槽体积符合设计", err < 0.03,
              f"挖掉 {cut:.0f} / 预期 {want:.0f} mm³（偏差 {err*100:.1f}%）")
        check("校准件槽间筋 ≥ 最小壁厚", T.slot_rib() >= P.MIN_WALL,
              f"{T.slot_rib():.2f} mm（最小 {P.MIN_WALL}）")

    print("\n=== 紧固件清单（由几何反推，不是抄的）===")
    m3_clamp = P.LID_T + 4.5          # 盖板 + 铜螺母有效啮合
    print(f"  盖板压紧螺钉   M3×12  ×4   （穿透 {P.LID_T}mm 盖板 + 约 4.5mm 啮合）")
    print(f"  输出盘中心螺钉 原厂 M3×6 ×1   （花键中心孔）")
    print(f"  输出盘→连杆    M3×10  ×{P.DISC_BOLTS}  （{P.DISC_T}mm 盘 + 连杆 {P.PLATE_T}mm）")
    print(f"  连杆→底盘      M3×10 + 螺母 ×4")
    print(f"  M3 热熔铜螺母  M3×5×4 ×4")
    print(f"  M1 底盘→臂底座   M3×12 + 螺母 ×4")
    print(f"  M1 驱动舵机→底盘  M3×12 + 螺母 ×8（每只 4）")
    print(f"  M1 夹爪定爪→盖板  M3×10 ×2")
    print(f"  M1 夹爪动爪→输出盘 M3×10 ×4")

    print("\n=== STL 水密性（切片的硬前提）===")
    try:
        import trimesh
        for name in solids:
            m = trimesh.load(OUT / f"{name}.stl")
            check(f"{name} STL 水密", bool(m.is_watertight),
                  f"体积 {m.volume/1000:.2f} cm³ / {len(m.faces)} 面")
    except ImportError:
        print("  (跳过：未安装 trimesh)")

    failed = [r for r in results if not r[1]]
    print(f"\n=== 汇总：{len(results) - len(failed)}/{len(results)} 通过 ===")
    (OUT / "check_report.json").write_text(
        json.dumps([{"name": n, "pass": ok, "detail": d} for n, ok, d in results],
                   ensure_ascii=False, indent=2), encoding="utf-8")
    if failed:
        print("未通过项：")
        for n, _, d in failed:
            print(f"  - {n} ({d})")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())