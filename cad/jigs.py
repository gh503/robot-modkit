"""工装夹具：让"装得正"不靠手感。

三件套（都按 220 床设计，PETG，30 分钟能打完一套）：

1. `insert_guide` —— 热熔螺母导向块：孔 Ø4.6，垂直度靠夹具而不是手；
2. `jaw_block`    —— 夹爪开口块：40.0mm，装配时塞在两爪之间定开口；
3. `cradle`       —— 底盘翻转载具：66° V 型槽，把底盘立起来接线。

用法：
    cd cad && ../.venv/bin/python jigs.py        # 导出 + 自检
"""

from __future__ import annotations

import pathlib

from build123d import (
    Align,
    Box,
    Cylinder,
    Polyline,
    Pos,
    export_step,
    export_stl,
    extrude,
    make_face,
)

import params as P

OUT = pathlib.Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)

INSERT_HOLE_D = 4.6      # 铜螺母外径 4.0 + 0.6 间隙（手压能进、不晃）
INSERT_TOP_D = 9.0       # 顶部让位，容纳螺母翻边
INSERT_TOP_H = 6.0


def _cyl(d: float, h: float, x: float = 0, y: float = 0, z: float = 0):
    return Pos(x, y, z) * Cylinder(d / 2, h, align=(Align.CENTER, Align.CENTER, Align.MIN))


def insert_guide():
    body = Pos(22, 22, 0) * Box(44, 44, 22, align=(Align.MIN, Align.MIN, Align.MIN))
    body -= _cyl(INSERT_HOLE_D, 24, 22, 22, -1)
    body -= _cyl(INSERT_TOP_D, INSERT_TOP_H, 22, 22, 22 - INSERT_TOP_H)
    # 侧向观察窗：能看见螺母有没有歪
    body -= Pos(44, 22, 11) * Box(10, 10, 10, align=(Align.MIN, Align.CENTER, Align.CENTER))
    return body


def jaw_block():
    body = Pos(0, 0, 0) * Box(P.JAW_GAP_OPEN, 26, 8, align=(Align.CENTER, Align.CENTER, Align.CENTER))
    handle = Pos(0, 18, 0) * Box(20, 10, 8, align=(Align.CENTER, Align.MIN, Align.CENTER))
    return body.fuse(handle)


def cradle():
    profile = Polyline(
        (0, 0), (100, 0), (100, 10), (72, 10), (50, 58), (28, 10), (0, 10), (0, 0)
    )
    face = make_face(profile)
    body = extrude(face, 60)
    # 中间开一道竖槽：省料、能穿扎带，同时避免在 V 形尖端附近留薄壁
    body -= Pos(50, 30, -1) * Box(10, 12, 62, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return body


JIGS = {"insert_guide": insert_guide, "jaw_block": jaw_block, "cradle": cradle}


def main() -> int:
    fails = []
    print(f"{'夹具':<14}{'尺寸 mm':>22}{'体积':>9}  用途")
    uses = {
        "insert_guide": "热熔螺母垂直压入",
        "jaw_block": "夹爪 40mm 开口定位",
        "cradle": "底盘立起接线",
    }
    for name, fn in JIGS.items():
        s = fn()
        bb = s.bounding_box()
        vol = s.volume / 1000
        print(f"{name:<14}{bb.size.X:6.1f}×{bb.size.Y:6.1f}×{bb.size.Z:6.1f}{vol:8.1f}cm³  {uses[name]}")

        if max(bb.size.X, bb.size.Y, bb.size.Z) > max(P.PRINTER_BED):
            fails.append(f"{name} 超出打印床")
        if vol <= 0:
            fails.append(f"{name} 体积非正")

        export_step(s, str(OUT / f"{name}.step"))
        export_stl(s, str(OUT / f"{name}.stl"), tolerance=0.03, angular_tolerance=0.2)

    # 关键配合：导向孔要比螺母大、比螺母松；开口块必须是 40.0
    guide = insert_guide()
    hole = [f for f in guide.faces() if f.geom_type.name == "CYLINDER" and abs(f.radius * 2 - INSERT_HOLE_D) < 0.01]
    if not hole:
        fails.append("insert_guide 没有 Ø4.6 导向孔")
    if abs(jaw_block().bounding_box().size.X - P.JAW_GAP_OPEN) > 0.01:
        fails.append("jaw_block 宽度与 JAW_GAP_OPEN 不一致")

    if fails:
        print("\n未通过：")
        for f in fails:
            print("  -", f)
        return 1
    print("\n三件套自检通过；STL/STEP 在 cad/out/。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())