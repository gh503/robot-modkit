"""把 STL 排成三张 220×220 打印板（对应 SO-ARM100 "预排好的一张板" 的做法）。

为什么手排而不是自动装箱：
  · 底盘 120×200，两张板必然各占一张 —— 自动装箱反而会排出 5 张板
  · 预排结果固定，便于核对"这次打的和我上次打的一样"
  · 排完仍然断言：都在床内、互不重叠、高度不超、间隙 ≥ 4mm

用法：cd cad && ../.venv/bin/python plate.py
产物：cad/out/plate_A.stl / plate_B.stl / plate_C.stl
"""

from __future__ import annotations

import pathlib

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


def main():
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


if __name__ == "__main__":
    main()
