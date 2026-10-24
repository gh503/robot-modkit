"""生产链路的产物校验：可制造性/成本 JSON 是 CI 生成的真值，别让它悄悄退化。

这些文件由 `cad/manufacture.py`、`cad/cost.py` 生成；本地没生成时跳过（不阻塞纯上位机开发）。
"""

from __future__ import annotations

import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
MFG = ROOT / "cad" / "out" / "manufacturing.json"
COST = ROOT / "cad" / "out" / "cost.json"


def load(path: pathlib.Path):
    if not path.exists():
        pytest.skip(f"{path.name} 不存在，先跑 cad/manufacture.py + cost.py")
    return json.loads(path.read_text(encoding="utf-8"))


def test_every_part_has_manufacturing_data():
    mfg = load(MFG)
    assert len(mfg) >= 13
    for name, r in mfg.items():
        assert r["qty"] >= 1, name
        assert r["mass_g"] > 0, name
        assert r["hours"] > 0, name


def test_parts_fit_printer_bed():
    mfg = load(MFG)
    for name, r in mfg.items():
        assert max(r["bbox"]) <= 250, f"{name} 超床：{r['bbox']}"


def test_overhang_under_control():
    mfg = load(MFG)
    for name, r in mfg.items():
        assert r["overhang_pct"] <= 30, f"{name} 悬垂 {r['overhang_pct']}%"


def test_wall_thickness():
    mfg = load(MFG)
    for name, r in mfg.items():
        # 射线法有 10% 误差，且螺丝柱内孔会被误测，故留 0.9 系数
        assert r["min_thickness_mm"] >= 1.2 * 0.9 - 0.02, f"{name} 壁厚 {r['min_thickness_mm']}"


def test_cost_decreases_with_quantity():
    data = load(COST)
    for tier, rows in data.items():
        per = [r["per_unit"] for r in rows]
        assert per == sorted(per, reverse=True), f"{tier} 单价没随数量下降：{per}"


def test_tier_b_costs_more_than_tier_a():
    data = load(COST)
    a = next(v for k, v in data.items() if k.startswith("A ") and "自己" not in k)
    b = next(v for k, v in data.items() if k.startswith("B ") and "自己" not in k)
    assert b[0]["per_unit"] > a[0]["per_unit"]


def test_cost_breakdown_is_consistent():
    data = load(COST)
    for rows in data.values():
        for r in rows:
            parts = r["parts_cost"] + r["filament_cost"] + r["machine_cost"] + r["labor_cost"]
            assert abs(parts + r["scrap"] + r["shipping_packaging"] - r["per_unit"]) < 2.0
            assert abs(r["per_unit"] * r["qty"] - r["total"]) <= r["qty"]