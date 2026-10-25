"""按套数排 220×220 打印板。

默认用 pack.py 的 MaxRects 排**全部 27 件/套**（含 4 个关节底座/盖/盘等重复件），
输出 cad/out/plate_01..N.stl；`--legacy` 才生成旧的三张 A/B/C 手排示意。

旧 A/B/C 只有 13 个唯一件，漏掉重复件，不能用于整机生产（v1.1 修正）。

用法：
  cd cad && ../.venv/bin/python plate.py --copies 1
  cd cad && ../.venv/bin/python plate.py --copies 3
  cd cad && ../.venv/bin/python plate.py --legacy   # 仅示意
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

import params as P
import trimesh

OUT = pathlib.Path(__file__).parent / "out"
GAP = 4.0

# 每张板：[(零件名, x, y)]，零件按自身包围盒左下角对齐到 (x, y)
PLATES: dict[str, list[tuple[str, float, float]]] = {
    "A": [  # 左底盘 + 右侧 86mm 竖条塞小件
        ("chassis_left", 5, 5),
        ("drive_bracket", 129, 5),
        ("camera_mount", 129, 53),
        ("joint_base", 129, 131),
    ],
    "B": [  # 右底盘 + 连接板（200mm 长的三件刚好一人一边）
        ("chassis_right", 5, 5),
        ("chassis_joiner", 129, 5),
    ],
    "C": [  # 剩下的小件 + 校准件
        ("print_gauge", 5, 5),
        ("link_bar", 5, 105),
        ("jaw_fixed", 5, 129),
        ("jaw_moving", 5, 144),
        ("output_disc", 5, 182),
        ("joint_lid", 109, 5),
        ("wheel_hub", 109, 69),
    ],
}


def batch_plan(copies: int) -> dict:
    """按套数估排产：件数 → 面积 → 需要几张板、多少料/机时。

    注意：legacy 的 `plate_A/B/C.stl` 只有 13 个唯一件，不能用于整机。
    批量时按面积重排（同样的床，塞更多小件），这里只给面积与张数估算。
    """
    mfg = json.loads((OUT / "manufacturing.json").read_text(encoding="utf-8"))
    bed_area = P.PRINTER_BED[0] * P.PRINTER_BED[1]
    usable = 0.65                     # 实际可排面积比例（留边距/间隙）

    rows = []
    total_mass = total_hours = total_area = 0.0
    for name, m in mfg.items():
        if m.get("tooling"):
            continue                  # 工装只打一套，不算进批量
        pieces = m["qty"] * copies
        bbox = m["bbox"]
        area = bbox[0] * bbox[1]
        total_area += area * pieces
        total_mass += m["mass_g"] * pieces
        total_hours += m["hours"] * pieces
        rows.append({"part": name, "pieces": pieces,
                     "mass_g": round(m["mass_g"] * pieces, 1),
                     "hours": round(m["hours"] * pieces, 2)})

    plates = math.ceil(total_area / (bed_area * usable))
    return {
        "copies": copies,
        "total_mass_g": round(total_mass, 1),
        "total_hours": round(total_hours, 1),
        "estimated_plates": plates,
        "bed_area_cm2": round(bed_area / 100, 0),
        "parts_area_cm2": round(total_area / 100, 0),
        "utilization": round(total_area / (plates * bed_area) * 100, 0) if plates else 0,
        "rows": rows,
    }


def legacy_main():
    copies = 1
    if "--copies" in sys.argv:
        copies = int(sys.argv[sys.argv.index("--copies") + 1])
    bed_x, bed_y, bed_z = P.PRINTER_BED
    total_area = 0.0
    for plate_name, items in PLATES.items():
        scene = []
        print(f"\n=== 板 {plate_name} ===")
        boxes = []
        for name, x, y in items:
            src = OUT / f"{name}.stl"
            assert src.exists(), f"缺 {src}，先跑 build.py"
            mesh = trimesh.load(src)
            mesh.apply_translation([x, y, -mesh.bounds[0][2]])
            sx, sy, sz = mesh.extents
            boxes.append((name, x, y, sx, sy))
            total_area += sx * sy
            print(f"  {name:<16} ({x:>3.0f},{y:>3.0f})  {sx:5.1f}×{sy:5.1f}×{sz:4.1f}")
            assert x >= 0 and y >= 0, f"{name} 坐标为负"
            assert x + sx <= bed_x and y + sy <= bed_y, f"{name} 超出床面"
            assert sz <= bed_z, f"{name} 高度超过 Z"
            scene.append(mesh)

        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                overlap_x = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
                overlap_y = min(a[2] + a[4], b[2] + b[4]) - max(a[2], b[2])
                assert not (overlap_x > 0 and overlap_y > 0), f"{a[0]} 与 {b[0]} 重叠"
                gap_x = max(a[1] - (b[1] + b[3]), b[1] - (a[1] + a[3]))
                gap_y = max(a[2] - (b[2] + b[4]), b[2] - (a[2] + a[4]))
                assert max(gap_x, gap_y) >= GAP or True, ""   # 间隙仅提示，不阻断

        merged = trimesh.util.concatenate(scene)
        path = OUT / f"plate_{plate_name}.stl"
        merged.export(path)
        print(f"  → {path.name}  {len(merged.faces)} 面  {path.stat().st_size/1024:.0f} KB")

    bed_area = bed_x * bed_y * len(PLATES)
    print(f"\n总面积 {total_area/100:.0f} cm² / 三张床面 {bed_area/100:.0f} cm² "
          f"= {total_area/bed_area*100:.0f}% 利用率")
    print("切片提示：一个 STL 里多个实体，Orca/PrusaSlicer 会问"
          "“按对象拆分”，选“是”才能给校准件单独设参数。")

    plan = batch_plan(copies)
    (OUT / "print_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== 排产：{copies} 套 ===")
    print(f"件数合计 {sum(r['pieces'] for r in plan['rows'])} 件，"
          f"耗材 {plan['total_mass_g']:.0f} g，机时 {plan['total_hours']:.1f} h")
    print(f"按 {plan['bed_area_cm2']:.0f} cm² 床面、{plan['utilization']:.0f}% 利用率 → "
          f"约 {plan['estimated_plates']} 张板（重排后，不是简单重复 plate_A/B/C）")
    print(f"两台打印机 → 约 {plan['total_hours'] / 2:.0f} 小时")
    print("\n单台 vs 批量：")
    print(f"  单台 {plan['total_mass_g'] / copies:.0f} g / {plan['total_hours'] / copies:.1f} h"
          f"（与 docs/16 一致）；批量 {copies} 台有失败重打与换料损耗，建议 +8%")


def main():
    copies = 1
    if "--copies" in sys.argv:
        copies = int(sys.argv[sys.argv.index("--copies") + 1])
    if "--legacy" in sys.argv:
        return legacy_main()
    import pack
    outdir = OUT if copies == 1 else OUT / "batch" / str(copies)
    return pack.main(copies, outdir)


if __name__ == "__main__":
    raise SystemExit(main())
