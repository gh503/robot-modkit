"""预算优化器：Python 与 CLI 的降本候选回归。"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

from modkit import assembly as asm
from modkit import optimizer as opt

ROOT = pathlib.Path(__file__).resolve().parents[2]
M1 = ROOT / "assemblies" / "m1.json"


def test_drop_elbow_candidate_is_valid_and_saves():
    data = json.loads(M1.read_text(encoding="utf-8"))
    cands = opt.suggest(data)
    c = next(x for x in cands if x["id"] == "drop-elbow")
    name, inst, payload, accel, strict, raw = asm.parse(c["assembly"])
    rep = asm.validate(name, inst, payload, accel, strict, raw)
    assert rep.ok
    assert c["components"] == 15
    assert c["joints"] == 3
    assert abs(c["cost"] - 968.0) < 0.2
    assert abs(c["saving"] - 159.4) < 0.2
    ids = {row["id"] for row in c["assembly"]["components"]}
    assert "elbow" not in ids and "gripper" in ids
    assert next(row for row in c["assembly"]["components"] if row["id"] == "gripper")["parent"] == "upper"


def test_cli_suggest_and_apply(tmp_path):
    cmd = [sys.executable, "-m", "modkit.cli", "assemble", "suggest", str(M1), "--json"]
    p = subprocess.run(cmd, cwd=ROOT / "software", text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    assert p.returncode == 0, p.stderr
    rows = json.loads(p.stdout)
    drop = next(row for row in rows if row["id"] == "drop-elbow")
    assert drop["cost"] == 968.0 and drop["saving"] == 159.4

    cmd = [sys.executable, "-m", "modkit.cli", "assemble", "suggest", str(M1),
           "--mass", "--json"]
    p = subprocess.run(cmd, cwd=ROOT / "software", text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    assert p.returncode == 0, p.stderr
    mass = next(row for row in json.loads(p.stdout)
                if row["id"] == "swap-frame.chassis_240-frame.chassis_160")
    assert abs(mass["mass_saving"] - 80.0) < 0.2 and abs(mass["saving"]) < 0.01

    out = tmp_path / "m1-opt.json"
    cmd = [sys.executable, "-m", "modkit.cli", "assemble", "suggest", str(M1),
           "--apply", "drop-elbow", "--out", str(out)]
    p = subprocess.run(cmd, cwd=ROOT / "software", text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    assert p.returncode == 0, p.stderr
    assert out.is_file()
    rep = asm.load_and_validate(out)
    assert rep.ok
    assert len(rep.instances) == 15
    assert abs(rep.total_cost_cny - 968.0) < 0.2


def test_plan_reaches_and_reports_unreachable():
    data = json.loads(M1.read_text(encoding="utf-8"))
    hit = opt.plan(data, 1000)
    assert hit["reached"] is True
    assert len(hit["steps"]) == 1 and hit["steps"][0]["id"] == "drop-elbow"
    assert abs(hit["cost"] - 968.0) < 0.2
    assert len(hit["assembly"]["components"]) == 15
    assert "预算规划" in opt.plan_markdown(hit, "m1")

    miss = opt.plan(data, 900)
    assert miss["reached"] is False
    assert [s["id"] for s in miss["steps"]] == ["drop-elbow", "swap-link.beam_100-link.beam_60"]
    assert abs(miss["cost"] - 964.4) < 0.2
    assert abs(miss["remaining"] - 64.4) < 0.2
    assert "未达标" in opt.plan_markdown(miss, "m1")


def test_cli_plan_and_apply(tmp_path):
    cmd = [sys.executable, "-m", "modkit.cli", "assemble", "suggest", str(M1),
           "--goal", "1000", "--json"]
    p = subprocess.run(cmd, cwd=ROOT / "software", text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    assert p.returncode == 0, p.stderr
    plan = json.loads(p.stdout)
    assert plan["reached"] is True and plan["cost"] == 968.0
    assert plan["steps"][0]["id"] == "drop-elbow"

    out = tmp_path / "m1-plan.json"
    cmd = [sys.executable, "-m", "modkit.cli", "assemble", "suggest", str(M1),
           "--goal", "1000", "--apply-plan", "--out", str(out)]
    p = subprocess.run(cmd, cwd=ROOT / "software", text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    assert p.returncode == 0, p.stderr
    rep = asm.load_and_validate(out)
    assert rep.ok and len(rep.instances) == 15
    assert abs(rep.total_cost_cny - 968.0) < 0.2
    assert out.read_text(encoding="utf-8").find("-plan") >= 0


def test_plan_node_cap_reports_truncation():
    data = json.loads(M1.read_text(encoding="utf-8"))
    p = opt.plan(data, 900, max_steps=4, max_nodes=1)
    assert p["truncated"] is True
    assert p["steps"] == []
    assert abs(p["cost"] - 1127.4) < 0.2
    assert "节点上限" in opt.plan_markdown(p, "m1")


def test_mass_only_candidate_is_opt_in():
    data = json.loads(M1.read_text(encoding="utf-8"))
    assert not any(c["id"] == "swap-frame.chassis_240-frame.chassis_160"
                   for c in opt.suggest(data))
    cs = opt.suggest(data, include_mass=True)
    c = next(c for c in cs if c["id"] == "swap-frame.chassis_240-frame.chassis_160")
    assert abs(c["saving"]) < 0.01
    assert abs(c["mass_saving"] - 80.0) < 0.2
    assert abs(c["cost"] - 1127.4) < 0.2
    name, inst, payload, accel, strict, raw = asm.parse(c["assembly"])
    rep = asm.validate(name, inst, payload, accel, strict, raw)
    assert rep.ok and abs(rep.total_mass_g - 1773.8) < 0.2


def test_pareto_and_constrained_plan():
    data = json.loads(M1.read_text(encoding="utf-8"))
    cs = opt.suggest(data, include_mass=True)
    drop = next(c for c in cs if c["id"] == "drop-elbow")
    assert drop["pareto"] is True and drop["dominated_by"] == []
    frame = next(c for c in cs if c["id"] == "swap-frame.chassis_240-frame.chassis_160")
    assert frame["pareto"] is False
    assert "drop-elbow" in frame["dominated_by"]

    p = opt.plan(data, 1000, constraints={"min_joints": 4})
    assert p["feasible"] is True and p["reached"] is False
    assert p["base_violations"] == [] and p["violations"] == []
    assert all(s["id"] != "drop-elbow" for s in p["steps"])
    assert abs(p["cost"] - 1123.8) < 0.2
    assert "约束：" in opt.plan_markdown(p, "m1")

    bad = opt.plan(data, 1000, constraints={"max_mass_g": 1500})
    assert bad["feasible"] is False
    assert bad["base_violations"] and "质量" in bad["base_violations"][0]
    assert "约束未满足" in opt.plan_markdown(bad, "m1")

    assert opt.normalize_constraints({"min_joints": "4", "max_mass_g": "1800",
                                      "max_risk": "low"}) == {
        "min_joints": 4, "max_mass_g": 1800.0, "max_risk": "low"}
