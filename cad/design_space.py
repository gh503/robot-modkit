"""设计空间：载荷 × 连杆厚度 × 臂长，哪一格能用。

回答三个问题：
  1. 现在的 100g 还能加多少？（力矩先到顶还是刚度先超差）
  2. 想抓 300g，必须改什么？
  3. 把臂缩短 20mm，能多抓多少？

产物：docs/27-设计空间.md + docs/images/design_space.png
用法：cd cad && ../.venv/bin/python design_space.py
"""

from __future__ import annotations

import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import params as P
from matplotlib import font_manager as fm

for _f in ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
           "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
           "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"):
    if pathlib.Path(_f).exists():
        fm.fontManager.addfont(_f)
plt.rcParams["font.sans-serif"] = ["Noto Sans CJK JP", "Noto Sans CJK SC",
                                   "WenQuanYi Zen Hei", "DejaVu Sans"]
plt.rcParams["font.family"] = "sans-serif"

ROOT = pathlib.Path(__file__).parent.parent
OUT = pathlib.Path(__file__).parent / "out"
DOCS = ROOT / "docs"

PETG_E = 2000.0
SERVO_RATED = 30.0 * 0.0980665      # N·m
SAFETY = 2.0
G = 9.81 / 1000.0                   # N/g

# 与 verify_design 一致的固定质量（g）
FIXED = {
    "arm_fixed_g": 210.0,   # 连杆×2 + 输出盘 + 夹爪 + 肩肘舵机（不含载荷）
}


def shoulder_moment(payload_g: float, reach_mm: float) -> float:
    """最不利：臂水平伸直，载荷在末端；固定质量按质心 0.45×reach 计。"""
    fixed = FIXED["arm_fixed_g"] * G * (0.45 * reach_mm) / 1000.0
    load = payload_g * G * reach_mm / 1000.0
    return fixed + load


FOREARM_MM = 110.0   # 只有末端这一段（肘→腕）承受载荷；上臂挠度未计，见 §6


def tip_deflection(payload_g: float, thickness: float, reach_mm: float = 0.0) -> float:
    """末端挠度：按肘→腕这一段悬臂梁算（与 verify_design 同口径）。"""
    I = P.LINK_W * thickness ** 3 / 12.0
    F = payload_g * G
    return F * FOREARM_MM ** 3 / (3 * PETG_E * I)


def evaluate(payload_g: float, thickness: float, reach_mm: float) -> dict:
    m = shoulder_moment(payload_g, reach_mm)
    allow = SERVO_RATED / SAFETY
    d = tip_deflection(payload_g, thickness, reach_mm)
    return {
        "payload_g": payload_g, "thickness_mm": thickness, "reach_mm": reach_mm,
        "moment_nm": round(m, 2), "margin": round(allow / m, 2),
        "deflection_mm": round(d, 2),
        "ok": allow / m >= 1.3 and d <= 1.0,
        "limited_by": "力矩" if allow / m < 1.3 else ("刚度" if d > 1.0 else "—"),
    }


def max_payload(thickness: float, reach_mm: float, d_limit: float = 1.0) -> int:
    """二分找同时满足力矩余量 ≥1.3 与挠度 ≤1mm 的最大载荷。"""
    lo, hi = 0.0, 2000.0
    for _ in range(40):
        mid = (lo + hi) / 2
        r = evaluate(mid, thickness, reach_mm)
        if r["margin"] >= 1.3 and r["deflection_mm"] <= d_limit:
            lo = mid
        else:
            hi = mid
    return int(lo // 10 * 10)


def main() -> int:
    thicknesses = [4.0, 5.0, 6.0, 8.0, 10.0]
    payloads = [100, 200, 300, 400, 500]
    reach = 230.0            # l1+l2

    rows = []
    for t in thicknesses:
        for p in payloads:
            rows.append(evaluate(p, t, reach))

    # 图：左=余量，右=挠度
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.2), dpi=160)
    xs = list(range(50, 601, 10))
    for t in thicknesses:
        ax1.plot(xs, [evaluate(p, t, reach)["margin"] for p in xs], label=f"{t:g}mm")
        ax2.plot(xs, [evaluate(p, t, reach)["deflection_mm"] for p in xs], label=f"{t:g}mm")
    ax1.axhline(1.3, color="#c44", ls="--", lw=1)
    ax1.set_xlabel("载荷 / g")
    ax1.set_ylabel("肩部余量 / ×")
    ax1.set_title("力矩余量（虚线 = 1.3 下限）")
    ax1.legend(fontsize=8)
    ax1.grid(alpha=0.25)
    ax2.axhline(1.0, color="#c44", ls="--", lw=1)
    ax2.set_yscale("log")
    ax2.set_xlabel("载荷 / g")
    ax2.set_ylabel("末端挠度 / mm")
    ax2.set_title("连杆挠度（虚线 = 1mm 上限）")
    ax2.legend(fontsize=8)
    ax2.grid(alpha=0.25)
    fig.tight_layout()
    img = DOCS / "images" / "design_space.png"
    fig.savefig(img)
    plt.close(fig)

    caps = {t: max_payload(t, reach) for t in thicknesses}
    # 臂长敏感性（6mm，300g）
    reach_rows = []
    for r in (180, 200, 230, 260):
        e = evaluate(300, 6.0, r)
        reach_rows.append((r, e["margin"], e["deflection_mm"], e["ok"]))

    lines = [
        "# 27 · 设计空间（自动生成）",
        "",
        "> 由 `cad/design_space.py` 计算。固定质量 210g（连杆/输出盘/夹爪/肩肘舵机），",
        f"> 臂展 {reach:g}mm（力矩用全长，挠度只算肘→腕 {FOREARM_MM:g}mm），"
        f"> 安全系数 {SAFETY}，PETG E={PETG_E} MPa。",
        "",
        "## 1. 一句话结论",
        "",
        f"- 6mm 连杆当前能稳拿 **{caps[6.0]} g**（力矩余量 ≥1.3 且挠度 ≤1mm）；",
        f"- 想上 300g：6mm 不够（{'、'.join(f'{t:g}mm→{caps[t]}g' for t in (8.0, 10.0))}），"
        "要么加厚到 8mm，要么缩短臂；",
        "- **限制因素随载荷切换**：轻载时刚度先到顶，重载时力矩先到顶。",
        "",
        "## 2. 可行域（✓ = 余量 ≥1.3 且挠度 ≤1mm）",
        "",
        "| 载荷 \\ 厚度 | " + " | ".join(f"{t:g}mm" for t in thicknesses) + " |",
        "|---:|" + "---|" * len(thicknesses),
    ]
    for p in payloads:
        cells = []
        for t in thicknesses:
            e = evaluate(p, t, reach)
            mark = "✓" if e["ok"] else "✗"
            cells.append(f"{mark} {e['margin']:.1f}× / {e['deflection_mm']:.2f}mm")
        lines.append(f"| {p} g | " + " | ".join(cells) + " |")

    lines += [
        "",
        "## 3. 每种厚度的载荷上限",
        "",
        "| 连杆厚度 | 最大载荷（本臂展） | 受限原因 |",
        "|---:|---:|---|",
    ]
    for t in thicknesses:
        cap = caps[t]
        nxt = evaluate(cap + 10, t, reach)
        why = "力矩" if nxt["margin"] < 1.3 else ("刚度" if nxt["deflection_mm"] > 1.0 else "—")
        lines.append(f"| {t:g} mm | {cap} g | {why} |")

    lines += [
        "",
        "## 4. 臂长敏感性（6mm、300g）",
        "",
        "| 臂展 | 力矩余量 | 挠度 | 可行 |",
        "|---:|---:|---:|:--:|",
    ]
    for r, m, d, ok in reach_rows:
        lines.append(f"| {r} mm | {m:.2f}× | {d:.2f} mm | {'✓' if ok else '✗'} |")
    lines += [
        "",
        "缩短臂长同时改善力矩与刚度（挠度 ∝ L³），是「不加料」的首选。",
        "",
        "## 5. 怎么用这张表",
        "",
        "1. 先定载荷（任务决定），再在表里找 ✓ 的最薄厚度（省料、省时间）；",
        "2. 都在 ✗ 时，按「缩臂 → 加厚 → 换大舵机」的顺序改（成本递增）；",
        "3. 改完必须重跑 `verify_design.py`（它会用实际克重再算一遍）。",
        "",
        "## 6. 假设与局限",
        "",
        "- 只算静态、单姿态（水平伸直），没有动载与冲击；",
        "- 挠度只算肘→腕一段，**未计上臂弯曲与关节间隙**；真机会更软，实测为准；",
        "- 舵机额定 30kg·cm 是厂标，真实堵转/温升会降额。",
        "",
    ]
    (DOCS / "27-设计空间.md").write_text("\n".join(lines), encoding="utf-8")
    (OUT / "design_space.json").write_text(
        json.dumps({"grid": rows, "caps": caps,
                    "reach_mm": reach, "assumptions": FIXED},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"载荷上限：{ {f'{t:g}mm': caps[t] for t in thicknesses} }")
    print(f"图：{img.relative_to(ROOT)}；表：docs/27-设计空间.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
