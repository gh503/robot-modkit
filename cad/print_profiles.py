"""打印参数卡：每个零件到底用什么层高/壁数/填充/支撑。

原则（不是拍脑袋）：
  · 受力件（连杆/输出盘/夹爪/支架）：4 壁 + 25% 填充，宁可多 10 分钟；
  · 外观/盖板：3 壁 + 15%，省时间；
  · 高瘦件（z>60mm）：加 5mm brim，防翘边带倒；
  · 悬垂 >15%：必须开支撑（数值来自 manufacture.py 的实测悬垂率）。

产物：docs/31-打印参数.md + cad/out/print_profiles.json
用法：cd cad && ../.venv/bin/python print_profiles.py
"""

from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).parent.parent
MFG = pathlib.Path(__file__).parent / "out" / "manufacturing.json"
DOCS = ROOT / "docs"

# 受力件：按结构作用分类，不按名字猜
LOAD_BEARING = {
    "link_bar", "output_disc", "jaw_fixed", "jaw_moving", "drive_bracket",
    "joint_base", "joint_lid", "wheel_hub", "chassis_left", "chassis_right",
    "chassis_joiner", "camera_mount",
}
COSMETIC = {"print_gauge", "insert_guide", "jaw_block", "cradle"}


def profile_for(name: str, m: dict) -> dict:
    overhang = m.get("overhang_pct", 0.0) / 100.0      # manufacture.py 给的是百分数
    sup_txt = str(m.get("support", ""))
    brim_txt = str(m.get("brim", ""))
    needs_support = ("不需要" not in sup_txt) and ("需要" in sup_txt or "建议" in sup_txt)
    needs_brim = ("不需要" not in brim_txt) and ("建议" in brim_txt or "需要" in brim_txt)
    if name in LOAD_BEARING:
        walls, infill, layer = 4, 25, 0.20
    elif name in COSMETIC:
        walls, infill, layer = 3, 20, 0.20
    else:
        walls, infill, layer = 3, 15, 0.20
    return {
        "walls": walls,
        "infill_pct": infill,
        "layer_mm": layer,
        "brim_mm": 5.0 if needs_brim else 0.0,
        "supports": needs_support or overhang > 0.15,
        "orientation": m.get("orientation", "?"),
        "note": "受力件" if name in LOAD_BEARING else ("工装" if name in COSMETIC else "普通"),
    }


def main() -> int:
    if not MFG.exists():
        raise SystemExit("缺 manufacturing.json，先跑 manufacture.py")
    mfg = json.loads(MFG.read_text(encoding="utf-8"))

    rows = []
    fails = []
    for name, m in mfg.items():
        pr = profile_for(name, m)
        rows.append((name, m, pr))
        if not (3 <= pr["walls"] <= 5):
            fails.append(f"{name} 壁数 {pr['walls']} 越界")
        if not (15 <= pr["infill_pct"] <= 40):
            fails.append(f"{name} 填充 {pr['infill_pct']}% 越界")
        if not (0.16 <= pr["layer_mm"] <= 0.28):
            fails.append(f"{name} 层高 {pr['layer_mm']} 越界")

    total_g = sum(m["mass_g"] * m.get("qty", 1) for _, m, _ in rows)
    total_h = sum(m["hours"] * m.get("qty", 1) for _, m, _ in rows)

    lines = [
        "# 31 · 打印参数（自动生成）",
        "",
        f"> 由 `cad/print_profiles.py` 按零件作用 + 实测悬垂生成；共 **{len(rows)} 个件**，"
        f"{total_g:.0f} g / {total_h:.1f} h（含工装）。",
        "> 材料统一 PETG；热床 80℃；首层 0.2mm。",
        "",
        "## 1. 总则",
        "",
        "| 项 | 值 | 理由 |",
        "|---|---|---|",
        "| 材料 | PETG | 韧、耐温，夹具反复用不蠕变 |",
        "| 层高 | 0.20mm | 强度/时间平衡；0.16 更细但慢 20% |",
        "| 壁数 | 3–4 | 4 壁比 25% 填充更抗弯 |",
        "| 填充 | 15–25% | 受力件 25%，外观件 15% |",
        "| 支撑 | 悬垂 >15% 才开 | 支撑会留疤，能躺平就不立 |",
        "| brim | z>60mm 加 5mm | 高瘦件翘边会带倒 |",
        "",
        "## 2. 逐件参数",
        "",
        "| 零件 | 数量 | 壁 | 填充 | 层高 | 支撑 | brim | 方向 | 克重 | 时长 | 类型 |",
        "|---|---:|---:|---:|---:|:--:|---:|---|---:|---:|---|",
    ]
    for name, m, pr in rows:
        lines.append(
            f"| {name} | {m.get('qty', 1)} | {pr['walls']} | {pr['infill_pct']}% | "
            f"{pr['layer_mm']:.2f} | {'✓' if pr['supports'] else '—'} | "
            f"{pr['brim_mm']:g} | {pr['orientation']} | {m['mass_g']:.0f} g | "
            f"{m['hours']:.2f} h | {pr['note']} |")

    lines += [
        "",
        "## 3. 切片器操作顺序",
        "",
        "1. 导入 `cad/out/plate_A/B/C.stl`（或单件 STL）→ 选「按对象拆分」；",
        "2. 校准件单独设 0.2mm / 3 壁 / 20%，**先打它**；",
        "3. 受力件按上表设 4 壁 / 25%；",
        "4. 检查摆向：长边贴床、大平面朝下（与表中「方向」一致）；",
        "5. 只有悬垂 >15% 的件开支撑（表中 ✓）；",
        "6. 切片预览看三件事：首层是否连续、支撑是否只碰悬垂、有没有细高柱。",
        "",
        "## 4. 常见错误",
        "",
        "| 现象 | 原因 | 改法 |",
        "|---|---|---|",
        "| 孔变小、螺丝拧不进 | 收缩 + 挤出过宽 | 孔按 Ø3.4/3.6 设计；流量校准 -2% |",
        "| 层间开裂 | 层高太大/温度低 | 0.2mm、喷头 240–250℃、关风扇前 3 层 |",
        "| 翘边 | 床温低/无 brim | 80℃ + 胶棒；高件加 5mm brim |",
        "| 支撑拆不掉 | 支撑密度过高 | 支撑密度 15%、Z 距离 0.2mm |",
        "",
        "## 5. 和可制造性报告的关系",
        "",
        "悬垂率、方向、克重/时长都来自 [16-可制造性报告](16-可制造性报告.md)（`manufacture.py` 实测），",
        "这里只做「工艺决策」；改了摆向要重新跑 `manufacture.py` 再回填。",
        "",
    ]
    (DOCS / "31-打印参数.md").write_text("\n".join(lines), encoding="utf-8")

    out = {name: profile_for(name, m) for name, m in mfg.items()}
    (pathlib.Path(__file__).parent / "out" / "print_profiles.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{len(rows)} 个件，{total_g:.0f} g / {total_h:.1f} h；支撑 "
          f"{sum(1 for _, _, p in rows if p['supports'])} 件，brim "
          f"{sum(1 for _, _, p in rows if p['brim_mm'])} 件")
    print("写出 docs/31-打印参数.md 与 cad/out/print_profiles.json")
    if fails:
        for f in fails:
            print("  -", f)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
