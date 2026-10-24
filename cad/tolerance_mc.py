"""公差蒙特卡洛：装配能不能装上、末端会偏多少。

两个模型（都在这里写清楚假设，别让数字看起来比实际更准）：

1. 对接装配：两块板的孔位各 ±0.2（2σ），相对错位需 ≤ 过孔可吃量（Ø3.6 → 0.6mm 总）
2. 末端精度：每个关节径向间隙 0–0.2mm 随机 → 角度误差 θ≈c/r → 沿力臂放大后叠加

产物：docs/32-公差蒙特卡洛.md、docs/images/tolerance_mc.png、cad/out/tolerance_mc.json
用法：cd cad && ../.venv/bin/python tolerance_mc.py
"""

from __future__ import annotations

import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
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

N = 20000
SEED = 20261025
PART_TOL = 0.2          # 单件孔位 2σ
ALLOW = (P.M3_CLR_FIT - 3.0)  # Ø3.6 - M3 = 0.6 总可吃
HORN_R = 10.0           # 舵机盘半径
CLEAR_MAX = 0.2         # 关节径向间隙上限
LEVERS = (230.0, 110.0, 40.0)   # 三个关节到末端的等效力臂


def fit_yield(rng) -> dict:
    """两个对接面（底盘左/右 ↔ 连接板），每面 2 个方向错位。"""
    a = rng.normal(0, PART_TOL / 2, N)      # 2σ=0.2
    b = rng.normal(0, PART_TOL / 2, N)
    d = np.abs(a - b)                        # 单轴错位
    # 两轴合成（假设独立）
    d2 = np.hypot(d, np.abs(rng.normal(0, PART_TOL / 2, N) -
                            rng.normal(0, PART_TOL / 2, N)))
    ok = d2 <= ALLOW
    return {
        "n": N, "allow_mm": round(ALLOW, 2),
        "yield": round(float(ok.mean()) * 100, 2),
        "p50_mm": round(float(np.percentile(d2, 50)), 3),
        "p99_mm": round(float(np.percentile(d2, 99)), 3),
    }


def tip_error(rng) -> dict:
    """三个关节间隙 → 角度 → 末端位移；每个关节的力臂不同。"""
    total = np.zeros(N)
    for lever in LEVERS:
        c = rng.uniform(0, CLEAR_MAX, N)
        theta = c / HORN_R                     # rad
        total += theta * lever
    return {
        "n": N, "p50_mm": round(float(np.percentile(total, 50)), 2),
        "p95_mm": round(float(np.percentile(total, 95)), 2),
        "p99_mm": round(float(np.percentile(total, 99)), 2),
        "limit_mm": 8.0,
        "closed_loop_limit_mm": 2.0,
    }


def main() -> int:
    rng = np.random.default_rng(SEED)
    fit = fit_yield(rng)
    tip = tip_error(rng)

    fails, warns = [], []
    if fit["yield"] < 99.5:
        fails.append(f"装配良率 {fit['yield']}% < 99.5%")
    if tip["p95_mm"] > tip["limit_mm"]:
        fails.append(f"末端 95% 误差 {tip['p95_mm']}mm > {tip['limit_mm']}mm")
    elif tip["p95_mm"] > tip["closed_loop_limit_mm"]:
        warns.append(f"开环 95% 误差 {tip['p95_mm']}mm，达不到 2mm 定位；需要闭环或预紧")

    # 图：错位分布 + 末端误差分布
    rng2 = np.random.default_rng(SEED)
    a, b = rng2.normal(0, PART_TOL / 2, N), rng2.normal(0, PART_TOL / 2, N)
    d2 = np.hypot(np.abs(a - b), np.abs(rng2.normal(0, PART_TOL / 2, N) -
                                        rng2.normal(0, PART_TOL / 2, N)))
    err = np.zeros(N)
    for lever in LEVERS:
        err += rng2.uniform(0, CLEAR_MAX, N) / HORN_R * lever

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4), dpi=160)
    ax1.hist(d2, bins=60, color="#4c78a8", alpha=0.85)
    ax1.axvline(ALLOW, color="#c44", ls="--", label=f"可吃 {ALLOW:.2f}mm")
    ax1.set_xlabel("对接错位 / mm")
    ax1.set_ylabel("样本数")
    ax1.set_title(f"装配：良率 {fit['yield']}%")
    ax1.legend(fontsize=8)

    ax2.hist(err, bins=60, color="#f58518", alpha=0.85)
    ax2.axvline(tip["p95_mm"], color="#c44", ls="--", label=f"95% = {tip['p95_mm']}mm")
    ax2.set_xlabel("末端位置误差 / mm")
    ax2.set_ylabel("样本数")
    ax2.set_title("开环末端误差（关节间隙主导）")
    ax2.legend(fontsize=8)
    fig.tight_layout()
    img = DOCS / "images" / "tolerance_mc.png"
    fig.savefig(img)
    plt.close(fig)

    lines = [
        "# 32 · 公差蒙特卡洛（自动生成）",
        "",
        f"> `cad/tolerance_mc.py`，{N} 次采样、固定种子 {SEED}（可复现）。",
        f"> 假设：单件孔位 ±{PART_TOL}mm（2σ）、对接孔 Ø{P.M3_CLR_FIT}、"
        f"关节径向间隙 0–{CLEAR_MAX}mm、舵盘半径 {HORN_R}mm。",
        "",
        "## 1. 结论",
        "",
        f"- 对接装配良率 **{fit['yield']}%**（错位 99 分位 {fit['p99_mm']}mm，可吃 {fit['allow_mm']}mm）",
        f"- 开环末端误差：中位 **{tip['p50_mm']}mm**、95 分位 **{tip['p95_mm']}mm**、99 分位 {tip['p99_mm']}mm",
        "- **关节间隙是主导误差源**，不是打印孔位；想把末端做到 2mm 以内，必须闭环或预紧消隙",
        "",
        "## 2. 装配（对接孔）",
        "",
        "| 项 | 值 |",
        "|---|---:|",
        f"| 采样数 | {fit['n']} |",
        f"| 可吃错位 | {fit['allow_mm']} mm |",
        f"| 良率 | {fit['yield']}% |",
        f"| 中位错位 | {fit['p50_mm']} mm |",
        f"| 99 分位 | {fit['p99_mm']} mm |",
        "",
        "## 3. 末端精度（开环）",
        "",
        "| 关节（等效力臂） | 间隙 → 角度 |",
        "|---|---|",
    ]
    for lever in LEVERS:
        lines.append(f"| {lever:.0f} mm | 0–{CLEAR_MAX}mm → 0–"
                     f"{np.degrees(CLEAR_MAX / HORN_R):.2f}° |")
    lines += [
        "",
        "| 分位 | 误差 |",
        "|---|---:|",
        f"| 50% | {tip['p50_mm']} mm |",
        f"| 95% | {tip['p95_mm']} mm |",
        f"| 99% | {tip['p99_mm']} mm |",
        "",
        "![公差分布](../docs/images/tolerance_mc.png)",
        "",
        "## 4. 怎么改（按性价比）",
        "",
        "1. **预紧/消隙**：关节加 0.1mm 垫片或偏心张紧，成本 ¥0，能把间隙压到 0.05mm；",
        "2. **闭环**：编码器在舵机内部，末端闭环需要外部视觉/标定（M3）；",
        "3. **缩短臂**：力臂 230→180mm，误差按比例降 22%；",
        "4. **换舵机**：金属齿轮 + 更小回差（¥95→¥180/只），最后才考虑。",
        "",
        "## 5. 局限",
        "",
        "- 间隙按均匀分布，实际可能偏一侧（磨损后变大）；",
        "- 没算舵机自身回差（实测 0.5–1°），真机会比这里更差；",
        "- 力臂按单轴叠加，没做完整 DH 变换（保守估计）。",
        "",
    ]
    (DOCS / "32-公差蒙特卡洛.md").write_text("\n".join(lines), encoding="utf-8")
    (OUT / "tolerance_mc.json").write_text(
        json.dumps({"fit": fit, "tip": tip, "seed": SEED}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    print(f"装配良率 {fit['yield']}%（p99 {fit['p99_mm']}mm / 可吃 {fit['allow_mm']}mm）")
    print(f"末端开环：p50 {tip['p50_mm']}mm，p95 {tip['p95_mm']}mm")
    print("写出 docs/32-公差蒙特卡洛.md 与图")
    if fails:
        print("未通过：")
        for f in fails:
            print("  -", f)
        return 1
    if warns:
        print("警告：")
        for w in warns:
            print("  -", w)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
