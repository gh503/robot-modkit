"""可制造性分析（DFM）：每个零件"该怎么打、要多少料、多久、哪里需要支撑"。

不靠手填表格，全部从网格算：
    · 体积 / 质量（PETG，按 15% 填充 + 4 壁折算）
    · 悬垂面积占比（法向与 +Z 夹角 > 45° 的面）
    · 最优摆放方向（在 6 个候选里选悬垂最少、底面最稳的）
    · 最小壁厚（从表面沿法向打射线，取 5% 分位）
    · 打印时间（体积 / 体积流量 × 行程系数）
    · 是否需要支撑、是否需要裙边/brim

产物：
    cad/out/manufacturing.json
    docs/16-可制造性报告.md

用法：cd cad && ../.venv/bin/python manufacture.py
"""

from __future__ import annotations

import json
import math
import pathlib

import numpy as np
import params as P
import parts as K
import parts_m1 as M1
import tools as T
import trimesh

OUT = pathlib.Path(__file__).parent / "out"
DOCS = pathlib.Path(__file__).parent.parent / "docs"

DENSITY = 1.27            # PETG g/cm³
FILL_FACTOR = 0.38        # 15% 填充 + 4 壁 + 上下实层 ≈ 实体的 38%
FLOW = 6.0                # mm³/s，0.4 喷嘴 / 0.2 层高 / PETG 的实际有效值
TRAVEL = 1.25             # 空驶、换层、加减速的系数

QTY = {
    "joint_base": 4, "joint_lid": 4, "output_disc": 4, "link_bar": 4, "wheel_hub": 2,
    "chassis_right": 1, "chassis_left": 1, "chassis_joiner": 1, "drive_bracket": 2,
    "jaw_fixed": 1, "jaw_moving": 1, "camera_mount": 1, "print_gauge": 1,
}

# 设计姿态不一定适合打印：这里给每个零件试几个候选方向
CANDIDATES = [
    ("原姿态", (0, 0, 0)),
    ("绕X 90°", (90, 0, 0)),
    ("绕X -90°", (-90, 0, 0)),
    ("绕X 180°", (180, 0, 0)),
    ("绕Y 90°", (0, 90, 0)),
    ("绕Y -90°", (0, -90, 0)),
]


def load_all() -> dict[str, trimesh.Trimesh]:
    meshes = {}
    for name in list(K.ALL_PARTS) + list(M1.ALL_PARTS_M1) + list(T.TOOLS):
        path = OUT / f"{name}.stl"
        if not path.exists():
            raise SystemExit(f"缺 {path}，先跑 build.py")
        m = trimesh.load(path)
        m.apply_translation(-m.bounds[0])
        meshes[name] = m
    return meshes


def rotate(mesh: trimesh.Trimesh, deg: tuple[float, float, float]) -> trimesh.Trimesh:
    m = mesh.copy()
    rx, ry, rz = [math.radians(a) for a in deg]
    for axis, ang in (([1, 0, 0], rx), ([0, 1, 0], ry), ([0, 0, 1], rz)):
        if abs(ang) > 1e-9:
            m.apply_transform(trimesh.transformations.rotation_matrix(ang, axis))
    m.apply_translation(-m.bounds[0])
    return m


def overhang_ratio(mesh: trimesh.Trimesh) -> float:
    """法向朝下超过 45° 的面积占比。

    贴着热床的那一层不算悬垂——它下面是床，不是空气。
    """
    n = mesh.face_normals
    down = n[:, 2] < -math.cos(math.radians(45))
    zmin = mesh.bounds[0][2]
    on_bed = mesh.triangles_center[:, 2] < zmin + 0.6
    down = down & ~on_bed
    return float(mesh.area_faces[down].sum() / mesh.area)


def bed_area(mesh: trimesh.Trimesh) -> float:
    """与热床接触的面积（法向朝上且贴着最低点）。"""
    n = mesh.face_normals
    down = n[:, 2] > 0.9
    zmin = mesh.bounds[0][2]
    zc = mesh.triangles_center[:, 2]
    touch = down & (zc < zmin + 0.5)
    return float(mesh.area_faces[touch].sum())


def min_thickness(mesh: trimesh.Trimesh, samples: int = 400) -> float:
    """从表面取点沿 -法向 打射线，取穿透厚度的 5% 分位。

    注意：必须用 intersects_id 拿"哪条射线打中了哪个点"的对应关系；
    直接用 intersects_location 会把所有射线的命中点混在一起，算出来全是 0.3mm。
    """
    rng = np.random.default_rng(7)
    idx = rng.choice(len(mesh.faces), min(samples, len(mesh.faces)), replace=False)
    centers = mesh.triangles_center[idx]
    dirs = -mesh.face_normals[idx]
    origins = centers + dirs * 0.01
    locs, ray, _tri = mesh.ray.intersects_location(origins, dirs, multiple_hits=False)
    if len(ray) == 0:
        return 0.0
    dist = np.linalg.norm(locs - origins[ray], axis=1)
    dist = dist[(dist > 0.2) & (dist < 80)]
    if len(dist) == 0:
        return 0.0
    return float(np.percentile(dist, 5))


def analyse(mesh: trimesh.Trimesh) -> dict:
    best = None
    for label, deg in CANDIDATES:
        m = rotate(mesh, deg)
        oh = overhang_ratio(m)
        bed = bed_area(m)
        height = m.extents[2]
        # 悬垂最贵（要支撑、要拆、会留疤）；其次高度（时间）；底面越大越稳
        score = oh * 200 + height - bed / 50
        if best is None or score < best["score"]:
            best = {"label": label, "deg": deg, "mesh": m, "overhang": oh,
                    "bed": bed, "height": height, "score": score}
    m = best["mesh"]
    vol_mm3 = float(m.volume)
    mass = vol_mm3 / 1000.0 * DENSITY * FILL_FACTOR * 1.15     # 含支撑/裙边余量
    hours = vol_mm3 * FILL_FACTOR / FLOW / 3600.0 * TRAVEL
    return {
        "orientation": best["label"],
        "rotation": list(best["deg"]),
        "bbox": [round(float(v), 1) for v in m.extents],
        "volume_cm3": round(vol_mm3 / 1000.0, 2),
        "mass_g": round(mass, 1),
        "hours": round(hours, 2),
        "overhang_pct": round(best["overhang"] * 100, 1),
        "bed_area_mm2": round(best["bed"], 0),
        "min_thickness_mm": round(min_thickness(m), 2),
        "support": "需要" if best["overhang"] > 0.06 else "极少/不需要",
        "brim": "建议" if best["bed"] < 300 and m.extents[2] > 20 else "不需要",
    }


def main() -> int:
    meshes = load_all()
    rows = []
    total_mass = total_hours = 0.0
    fails = []

    for name, mesh in meshes.items():
        r = analyse(mesh)
        qty = QTY.get(name, 1)
        total_mass += r["mass_g"] * qty
        total_hours += r["hours"] * qty
        rows.append((name, qty, r))

        bx, by, bz = P.PRINTER_BED
        if max(r["bbox"]) > max(bx, by, bz):
            fails.append(f"{name} 超出打印床 {r['bbox']}")
        if r["min_thickness_mm"] < P.MIN_WALL * 0.9:
            fails.append(f"{name} 最小壁厚 {r['min_thickness_mm']} < {P.MIN_WALL}")
        if r["overhang_pct"] > 30:
            fails.append(f"{name} 悬垂 {r['overhang_pct']}% 过多，换方向或加倒角")

    print(f"{'零件':<16}{'数量':>4}{'方向':>10}{'悬垂%':>7}{'壁厚':>7}{'质量g':>8}{'时长h':>7}  支撑")
    for name, qty, r in rows:
        print(f"{name:<16}{qty:>4}{r['orientation']:>10}{r['overhang_pct']:>7.1f}"
              f"{r['min_thickness_mm']:>7.2f}{r['mass_g']:>8.1f}{r['hours']:>7.2f}  {r['support']}")
    print(f"\n合计：{total_mass:.0f} g  PETG，{total_hours:.1f} 小时（含 {sum(QTY.values())} 件）")
    print(f"单套耗材成本（¥90/kg）：¥{total_mass/1000*90:.0f}")

    (OUT / "manufacturing.json").write_text(json.dumps(
        {n: {"qty": q, **r} for n, q, r in rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 16 · 可制造性报告（自动生成）",
        "",
        "> 由 `cad/manufacture.py` 从 STL 算出来，不是手填的。改尺寸后重跑即可。",
        f"> 假设：PETG 1.27 g/cm³，15% 填充 + 4 壁（按实体 38% 折算），"
        f"体积流量 {FLOW:.0f} mm³/s，行程系数 {TRAVEL}。",
        "",
        "| 零件 | 数量 | 建议方向 | 悬垂面积 | 最小壁厚 | 单件质量 | 单件时长 | 支撑 | 裙边 |",
        "|---|---:|---|---:|---:|---:|---:|---|---|",
    ]
    for name, qty, r in rows:
        lines.append(
            f"| `{name}` | {qty} | {r['orientation']} | {r['overhang_pct']}% | "
            f"{r['min_thickness_mm']} mm | {r['mass_g']} g | {r['hours']} h | {r['support']} | {r['brim']} |")
    lines += [
        "",
        f"**合计**：{total_mass:.0f} g PETG、{total_hours:.1f} 小时、{sum(QTY.values())} 件；"
        f"耗材约 ¥{total_mass/1000*90:.0f}（¥90/kg）。",
        "",
        "## 判据（CI 会跑）",
        "",
        f"- 每个零件都能放进 {P.PRINTER_BED[0]:.0f}×{P.PRINTER_BED[1]:.0f}×{P.PRINTER_BED[2]:.0f} 的床",
        f"- 最小壁厚 ≥ {P.MIN_WALL} mm（取射线穿透的 5% 分位，允许 10% 误差）",
        "- 最优方向下悬垂面积 ≤ 30%（超过就必须改方向或加 45° 倒角）",
        "",
    ]
    if fails:
        lines += ["## ❌ 未通过", ""] + [f"- {f}" for f in fails] + [""]
    (DOCS / "16-可制造性报告.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"写出 docs/16-可制造性报告.md 与 cad/out/manufacturing.json")

    if fails:
        print("\n未通过：")
        for f in fails:
            print("  -", f)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())