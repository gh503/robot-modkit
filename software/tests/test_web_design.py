"""网页设计器：数据/求解核心/导出/HTML 的离线回归。

浏览器端核心是 assembly.py 的子集，必须和 Python 口径对齐：
M1 18 组件、1853.8g、¥1127.4、4 个位置关节；替换工具后仍可求解。
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
DATA = WEB / "data"


def node() -> str:
    exe = shutil.which("node")
    if not exe:
        pytest.skip("没有 node，跳过浏览器核心测试")
    return exe


def run_core(script: str) -> dict:
    wrapper = """
const fs = require('fs'), vm = require('vm');
const ctx = { window: {} };
vm.createContext(ctx);
for (const f of ['web/data/components.js', 'web/data/assemblies.js']) {
  vm.runInContext(fs.readFileSync(f, 'utf8'), ctx);
}
global.window = ctx.window;
const A = require('./web/assembly-core.js');
const B = require('./web/budget-core.js')(A, window.MODKIT_COMPONENTS);
const out = (() => { %s })();
console.log(JSON.stringify(out));
""" % script
    p = subprocess.run([node(), "-e", wrapper], cwd=ROOT, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout.strip().splitlines()[-1])


def test_data_files_exist():
    assert (DATA / "components.js").is_file()
    assert (DATA / "assemblies.js").is_file()
    assert (WEB / "assembly-core.js").is_file()
    assert (WEB / "budget-core.js").is_file()
    assert (WEB / "designer.js").is_file()
    assert (WEB / "design.html").is_file()
    assert len(list((WEB / "models").glob("*.step"))) == 36


def test_core_presets_match_python_counts():
    out = run_core("""
      return Object.fromEntries(Object.entries(window.MODKIT_ASSEMBLIES).map(([n, a]) => {
        const r = A.validate(a);
        return [n, { ok: r.ok, n: r.instances.length, mass: r.totalMass, cost: r.totalCost,
                     errs: r.issues.filter(i => i.level === 'error').length }];
      }));
    """)
    expect = {
        "m1": (18, 1853.8, 1127.4),
        "m1_budget": (15, 1649.0, 968.0),
        "mini_rover": (9, 843.0, 653.0),
        "pan_tilt": (9, 892.0, 506.0),
        "arm_4dof": (14, 1430.8, 869.4),
        "wide_gripper": (12, 1285.8, 721.4),
        "sensor_tower": (8, 605.0, 256.0),
    }
    for name, (n, mass, cost) in expect.items():
        r = out[name]
        assert r["ok"], (name, r)
        assert r["errs"] == 0
        assert r["n"] == n
        assert abs(r["mass"] - mass) < 0.2
        assert abs(r["cost"] - cost) < 0.2


def test_budget_preset_under_1000():
    out = run_core("""
      const a = window.MODKIT_ASSEMBLIES.m1_budget;
      const r = A.validate(a);
      return { ok: r.ok, cost: r.totalCost, budget: a.budget_cny,
               n: r.instances.length, warnings: r.issues.filter(i => i.level === 'warn').length };
    """)
    assert out["ok"], out
    assert out["cost"] < 1000
    assert out["budget"] == 1000
    assert out["n"] == 15
    assert out["warnings"] >= 1


def test_budget_optimizer_finds_two_joint_variant():
    out = run_core("""
      const base = window.MODKIT_ASSEMBLIES.m1;
      const cands = B.suggest(base);
      const c = cands.find(x => x.id === 'drop-elbow');
      if (!c) return { found: false };
      const r = A.validate(c.assembly);
      return { found: true, cost: c.cost, saving: c.saving, n: c.components,
               joints: c.joints, ok: r.ok,
               old_names: base.components.map(x => x.id),
               new_names: c.assembly.components.map(x => x.id) };
    """)
    assert out["found"], out
    assert out["ok"]
    assert out["n"] == 15
    assert out["joints"] == 3
    assert abs(out["cost"] - 968.0) < 0.2
    assert abs(out["saving"] - 159.4) < 0.2
    assert "elbow" in out["old_names"] and "elbow" not in out["new_names"]
    assert "gripper" in out["new_names"]


def test_tool_dual_mount_allows_swap():
    out = run_core("""
      const a = JSON.parse(JSON.stringify(window.MODKIT_ASSEMBLIES.m1));
      const g = a.components.find(x => x.id === 'gripper');
      g.type = 'tool.pen';
      const r = A.validate(a);
      const pen = window.MODKIT_COMPONENTS['tool.pen'];
      return { ok: r.ok, errs: r.issues.filter(i => i.level === 'error'),
               ports: pen.ports.map(p => [p.name, p.kind, p.gender]) };
    """)
    assert out["ok"], out
    assert out["errs"] == []
    assert ["mount", "mech.grid", "neutral"] in out["ports"]
    assert ["disc", "mech.disc", "female"] in out["ports"]


def test_svg_and_edits():
    out = run_core("""
      const a = JSON.parse(JSON.stringify(window.MODKIT_ASSEMBLIES.m1));
      a.components.find(x => x.id === 'yaw').joint = {name: 'yaw', min: -45, max: 45};
      const r = A.validate(a);
      return { ok: r.ok, svg: A.svgReport(r).slice(0, 40), margin: r.stability.margin,
               joints: r.instances.filter(i => i.joint && i.joint.mode === 'position').length };
    """)
    assert out["ok"]
    assert out["svg"].startswith("<svg")
    assert out["margin"] is not None
    assert out["joints"] == 4


def test_js_syntax():
    n = node()
    for f in ("web/assembly-core.js", "web/designer.js"):
        p = subprocess.run([n, "--check", str(ROOT / f)], text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert p.returncode == 0, (f, p.stderr)


def test_design_html_hooks():
    html = (WEB / "design.html").read_text(encoding="utf-8")
    for node_id in ("viewport", "palette-list", "tree", "joints", "export-json",
                    "export-csv", "export-stl", "export-svg", "export-step",
                    "export-step-zip", "import-design", "restore-design"):
        assert 'id="%s"' % node_id in html, node_id
    assert 'value="m1_budget"' in html
    assert "assembly-core.js" in html and "designer.js" in html
