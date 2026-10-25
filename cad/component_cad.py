#!/usr/bin/env python
"""组件库的参数化 CAD 导出（按需运行，不塞进 make check）。

说明
----
这里不是"重新画一台 M1"，而是把**可打印的结构件**按组件注册表的尺寸
批量生成 STEP/STL + manifest。关节/轮子复用现有 `parts.py` 的真实零件；
传感器/电源等采购件只导出参考包围盒，方便装配时看空间，不冒充可打印件。

用法：
    cd cad && ../.venv/bin/python component_cad.py --only frame.chassis_240
    cd cad && ../.venv/bin/python component_cad.py --check
    cd cad && ../.venv/bin/python component_cad.py
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys

from build123d import Align, Box, Cylinder, Pos, Sphere, export_step, export_stl

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "software"))
from modkit import components as C  # noqa: E402

import parts as K  # noqa: E402
import parts_m1 as M1  # noqa: E402
import params as P  # noqa: E402

OUT = pathlib.Path(__file__).parent / "out" / "components"
OUT.mkdir(parents=True, exist_ok=True)


def _hole(d: float, h: float, x: float, y: float, z: float):
    return Pos(x, y, z) * Cylinder(d / 2, h, align=(Align.CENTER, Align.CENTER, Align.CENTER))


def _plate(comp: C.Component, thickness: float | None = None):
    w, d, t = comp.dims
    t = thickness or t
    z0 = comp.bbox[2]
    body = Pos(0, 0, z0 + t / 2) * Box(w, d, t)
    grid = C.get("frame.deck_120x80").ports[0].grid  # not used; keep explicit
    # 从组件的 top/ mount 网格端口取范围；没有就用 bbox 内缩 8mm。
    port = next((p_ for p_ in comp.ports if p_.kind == "mech.grid" and p_.grid), None)
    gw, gd = port.grid if port else (w - 16, d - 16)
    xs = [i * P.GRID for i in range(-int(gw // 2 // P.GRID), int(gw // 2 // P.GRID) + 1)]
    ys = [j * P.GRID for j in range(-int(gd // 2 // P.GRID), int(gd // 2 // P.GRID) + 1)]
    for x in xs:
        for y in ys:
            if abs(x) <= w / 2 - 8 and abs(y) <= d / 2 - 8:
                body = body.cut(_hole(P.M3_CLR, t + 2, x, y, z0 + t / 2))
    return body


def _beam(comp: C.Component):
    w, d, length = comp.dims
    body = Pos(0, 0, length / 2) * Box(w, d, length)
    for z in (0.0, length):
        for sx in (-1, 1):
            for sy in (-1, 1):
                body = body.cut(_hole(P.M3_CLR, 2, sx * (w / 2 - 4), sy * (d / 2 - 4), z))
    return body


def _chassis(comp: C.Component):
    return _plate(comp)


def _joint(comp: C.Component):
    shape = K.joint_base().fuse(K.joint_lid()).fuse(K.output_disc())
    return shape


def _wheel(comp: C.Component):
    d = comp.dims[0]
    tire = Pos(0, 0, -d / 2) * Cylinder(d / 2, 40, align=(Align.CENTER, Align.CENTER, Align.CENTER))
    # 轮轴沿 Y：把圆柱转 90°，再和轮毂融合
    from build123d import Rot
    tire = Pos(0, 0, -d / 2 - 4) * Rot(90, 0, 0) * Cylinder(d / 2, 40,
                                                            align=(Align.CENTER, Align.CENTER, Align.CENTER))
    return K.wheel_hub().fuse(tire)


def _caster(comp: C.Component):
    body = Pos(0, 0, -15) * Box(30, 30, 30)
    ball = Pos(0, 0, -30) * Sphere(7.5)
    return body.fuse(ball)


def _gripper(comp: C.Component):
    # 参考体：真实夹爪由 joint_base/lid/jaw_fixed/jaw_moving 组成；这里导出外壳，
    # 避免把未对齐的旧零件硬拼成错误实体。
    w, d, h = comp.dims
    return Pos(0, 0, h / 2) * Box(w, d, h)


def shape_of(comp: C.Component):
    if comp.cad == "beam":
        return _beam(comp)
    if comp.cad == "chassis":
        return _chassis(comp)
    if comp.cad == "joint":
        return _joint(comp)
    if comp.cad == "wheel":
        return _wheel(comp)
    if comp.cad == "caster":
        return _caster(comp)
    if comp.cad == "gripper":
        return _gripper(comp)
    if comp.cad == "plate":
        return _plate(comp)
    # 采购件/概念件：只给参考盒
    w, d, h = comp.dims
    z0 = comp.bbox[2]
    return Pos(0, 0, z0 + h / 2) * Box(w, d, h)


def bbox_of(shape) -> list[float]:
    b = shape.bounding_box()
    return [round(b.min.X, 2), round(b.min.Y, 2), round(b.min.Z, 2),
            round(b.max.X, 2), round(b.max.Y, 2), round(b.max.Z, 2)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append", help="只导出指定组件 id")
    ap.add_argument("--check", action="store_true", help="只检查尺寸，不写文件")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = C.by_category()
    if args.only:
        rows = [C.get(x) for x in args.only]
    manifest = []
    bad = 0
    for c in rows:
        shape = shape_of(c)
        bb = bbox_of(shape)
        vol = shape.volume / 1000.0
        # 结构件检查：包围盒不能比注册表大出 1mm；小一点允许（孔/倒角）。
        if c.cad in ("plate", "beam", "chassis"):
            exp = list(c.bbox)
            diff = max(abs(bb[i] - exp[i]) for i in range(6))
            ok = diff <= 1.0
        else:
            diff = None
            ok = True
        manifest.append({"id": c.id, "name": c.name, "status": c.status,
                         "cad": c.cad, "bbox": bb, "volume_cm3": round(vol, 3),
                         "bbox_diff_mm": None if diff is None else round(diff, 2),
                         "ok": ok})
        if not ok:
            bad += 1
            print(f"[FAIL] {c.id}: bbox {bb} vs {c.bbox}")
        safe = c.id.replace(".", "_").replace("/", "_")
        if not args.check:
            export_step(shape, str(out / f"{safe}.step"))
            export_stl(shape, str(out / f"{safe}.stl"), tolerance=0.05, angular_tolerance=0.3)
        print(f"[{'PASS' if ok else 'FAIL'}] {c.id:28s} {c.status:9s} "
              f"vol {vol:7.2f} cm³  bbox {bb}")
    (out / "manifest.json").write_text(
        json.dumps({"components": manifest, "count": len(manifest)}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"\n{len(manifest)} 个组件，{bad} 个尺寸 FAIL；manifest: {out / 'manifest.json'}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
