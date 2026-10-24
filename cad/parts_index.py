"""从实际几何生成 docs/11-零件清单.md（避免文档与 CAD 脱节）。

用法：cd cad && ../.venv/bin/python parts_index.py
"""

from __future__ import annotations

import json
import pathlib

import parts as K
import parts_m1 as M1

META = {
    # name: (数量, 用途, 打印时间 h:mm)
    "joint_base": (4, "关节底座：托住舵机，20mm 网格对接", "2:10"),
    "joint_lid": (4, "关节压盖：与底座夹住舵机（留 0.4mm 间隙）", "1:40"),
    "output_disc": (4, "输出盘：花键插座，替代原厂舵盘", "0:50"),
    "link_bar": (4, "连杆：关节之间的结构件", "1:20"),
    "wheel_hub": (2, "轮毂：把轮子固定到输出盘", "1:50"),
    "chassis_right": (1, "底盘右半（M1）", "3:30"),
    "chassis_left": (1, "底盘左半（M1）", "3:30"),
    "chassis_joiner": (1, "底盘连接板（M1）", "1:30"),
    "drive_bracket": (2, "驱动舵机支架：托盘承重（M1）", "1:10"),
    "jaw_fixed": (1, "夹爪定爪（M1）", "1:20"),
    "jaw_moving": (1, "夹爪动爪（M1）", "1:20"),
    "camera_mount": (1, "相机支架，55° 俯角（M1）", "1:00"),
}

FASTENERS = """
| 位置 | 螺钉 | 数量 |
|---|---|---|
| 底座→连杆 / 输出盘→连杆 | M3×10 | 每关节 8 |
| 盖板→底座 | M3×10 | 每关节 2 |
| 输出盘中心（原厂） | M3×6 | 每关节 1 |
| M3 热熔铜螺母 | M3×5×4 | 每关节 4 |
| 底盘左右→连接板 | M3×10 + 螺母 | 8 |
| 驱动支架→底盘 | M3×12 | 8 |
| 驱动轮→输出盘 | M3×10 | 每轮 4 |
| 夹爪定爪→盖板 | M3×10 | 3 |
| 夹爪动爪→输出盘 | M3×10 | 4 |
| 相机架→底盘 | M3×10 | 4 |
"""


def main() -> None:
    # 打印时间优先用 manufacture.py 算出来的（同一个来源），没有再退回手填值
    mfg_path = pathlib.Path(__file__).parent / "out" / "manufacturing.json"
    mfg = json.loads(mfg_path.read_text(encoding="utf-8")) if mfg_path.exists() else {}

    rows = []
    total_time = 0
    for name, fn in list(K.ALL_PARTS.items()) + list(M1.ALL_PARTS_M1.items()):
        part = fn()
        bb = part.bounding_box()
        vol = part.volume / 1000.0
        qty, note, t = META[name]
        if name in mfg:
            mins = round(mfg[name]["hours"] * 60)
            t = f"{mins // 60}:{mins % 60:02d}"
        h, m = t.split(":")
        total_time += qty * (int(h) * 60 + int(m))
        rows.append(
            f"| `{name}` | {qty} | {bb.size.X:.0f}×{bb.size.Y:.0f}×{bb.size.Z:.0f} "
            f"| {vol:.1f} | {M1.MATERIAL_M1.get(name) or K.MATERIAL[name]} | {t} | {note} |"
        )

    out = [
        "# 11 · 零件清单（由 CAD 自动生成，勿手改）",
        "",
        "> 重新生成：`cd cad && ../.venv/bin/python parts_index.py`。",
        "> 尺寸为打印件包围盒，单位 mm；体积用于估耗材（PETG 密度 1.27 g/cm³）。",
        "",
        "| 零件 | 数量 | 尺寸 | 体积 cm³ | 材料 | 打印时间 | 用途 |",
        "|---|---|---|---|---|---|---|",
        *rows,
        "",
        f"**打印总时长约 {total_time // 60} 小时 {total_time % 60} 分**（0.2 层高、4 壁；不含失败重打）。",
        "耗材约 **{:.0f} g**（体积 ×1.27，含支撑与裙边余量 +15%）。".format(
            sum(fn().volume / 1000.0 * 1.27 * 1.15 for fn in
                list(K.ALL_PARTS.values()) + list(M1.ALL_PARTS_M1.values()))
        ),
        "",
        "## 紧固件",
        FASTENERS,
    ]
    path = pathlib.Path(__file__).resolve().parent.parent / "docs" / "11-零件清单.md"
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"写入 {path}")


if __name__ == "__main__":
    main()
