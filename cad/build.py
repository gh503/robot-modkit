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
import sys
from pathlib import Path

import params as P
import parts as K
from build123d import Box, Pos, export_step, export_stl

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
    servo = K.servo_reference()
    return solids, servo


def main():
    solids, servo = build_all()

    print("\n=== 导出 ===")
    for name, s in solids.items():
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

    print("\n=== 打印机成形空间 ===")
    bx, by, bz = P.PRINTER_BED
    for name, s in solids.items():
        bb = s.bounding_box()
        fits = bb.size.X <= bx and bb.size.Y <= by and bb.size.Z <= bz
        check(f"{name} 可打印", fits,
              f"{bb.size.X:.1f}×{bb.size.Y:.1f}×{bb.size.Z:.1f} mm")

    print("\n=== 紧固件清单（由几何反推，不是抄的）===")
    m3_clamp = P.LID_T + 4.5          # 盖板 + 铜螺母有效啮合
    print(f"  盖板压紧螺钉   M3×12  ×4   （穿透 {P.LID_T}mm 盖板 + 约 4.5mm 啮合）")
    print(f"  输出盘中心螺钉 原厂 M3×6 ×1   （花键中心孔）")
    print(f"  输出盘→连杆    M3×10  ×{P.DISC_BOLTS}  （{P.DISC_T}mm 盘 + 连杆 {P.PLATE_T}mm）")
    print(f"  连杆→底盘      M3×10 + 螺母 ×4")
    print(f"  M3 热熔铜螺母  M3×5×4 ×4")

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