"""采购/落地成本：预算口径、采购清单、分阶段台架。"""
from __future__ import annotations

import csv
import io
import json
import pathlib

import pytest

from modkit import assembly as asm
from modkit import cli
from modkit import procure as proc

ROOT = pathlib.Path(__file__).resolve().parents[2]
M1_BUDGET = ROOT / "assemblies" / "m1_budget.json"


def test_landed_cost_and_target_bom():
    r = asm.load_and_validate(M1_BUDGET)
    e = proc.estimate(r)
    assert e.parts_cny == 968.0
    assert e.spares_cny == pytest.approx(77.44)
    assert e.total_cny == pytest.approx(1100.44)
    assert e.budget_cny == 1000.0
    assert e.within_budget is False
    assert e.over_cny == pytest.approx(100.44)
    assert e.target_bom_cny == pytest.approx(875.0)

    e0 = proc.estimate(r, shipping=0, spares=0, wire=0, tax=0)
    assert e0.total_cny == 968.0
    assert e0.within_budget is True

    with pytest.raises(ValueError):
        proc.estimate(r, spares=1.0)


def test_purchase_rows_are_exact_and_csv_roundtrips():
    r = asm.load_and_validate(M1_BUDGET)
    rows = proc.purchase_rows(r)
    assert sum(x["cost"] for x in rows) == pytest.approx(r.total_cost_cny)
    assert all(x["buy_qty"] == x["qty"] for x in rows)
    assert any(x["name"] == "总线舵机" and x["qty"] == 5 for x in rows)
    text = proc.to_csv(r)
    assert text.startswith("\ufeff类别,物料")
    parsed = list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))
    assert parsed[0][0] == "类别" and len(parsed) == len(rows) + 1
    assert "采购量=BOM 实用量" in proc.to_markdown(r)


def test_stage_assemblies_are_under_1000_landed():
    stages = ("bench_joint", "bench_arm", "rover_base", "m1_pen")
    costs = {}
    for name in stages:
        r = asm.load_and_validate(ROOT / "assemblies" / f"{name}.json")
        assert r.ok
        e = proc.estimate(r)
        costs[name] = e.total_cny
        assert e.total_cny < 1000
    assert costs["bench_joint"] < costs["bench_arm"]
    assert costs["bench_joint"] == pytest.approx(366.04)
    assert costs["bench_arm"] == pytest.approx(712.72)
    pen = asm.load_and_validate(ROOT / "assemblies" / "m1_pen.json")
    assert pen.ok and pen.raw["budget_cny"] == 1000.0
    assert proc.estimate(pen).within_budget is True
    assert proc.estimate(pen).total_cny == pytest.approx(961.12)

    code = cli.main(["assemble", "procure", str(M1_BUDGET), "--json"])
    assert code == 0
