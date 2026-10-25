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
