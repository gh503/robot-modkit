"""网页设计器：数据/求解核心/导出/HTML 的离线回归。

浏览器端核心是 assembly.py 的子集，必须和 Python 口径对齐：
M1 18 组件、1853.8g、¥1127.4、4 个位置关节；替换工具后仍可求解。
"""
from __future__ import annotations

import json
import pathlib
import re
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


def test_pwa_shell_is_complete_and_versioned():
    manifest = json.loads((WEB / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert manifest["start_url"] == "./design.html"
    assert manifest["display"] == "standalone"
    sw = (WEB / "sw.js").read_text(encoding="utf-8")
    for name in ("design.html", "designer.js", "assembly-core.js", "budget-core.js"):
        assert name in sw
    assert "CACHE" in sw and "skipWaiting" in sw
    assert 'req.destination === "script"' in sw and 'cache: "no-cache"' in sw
    version = re.search(r'__version__\s*=\s*"([^"]+)"',
                        (ROOT / "software" / "modkit" / "__init__.py").read_text(encoding="utf-8")).group(1)
    assert 'CACHE = "modkit-shell-v' + version + '"' in sw
    for page in ("index.html", "design.html"):
        html = (WEB / page).read_text(encoding="utf-8")
        assert 'rel="manifest"' in html and 'src="pwa.js"' in html


def test_shape_check_rejects_bad_import_before_validate():
    out = run_core("""
      const good = A.check(window.MODKIT_ASSEMBLIES.m1);
      const all = Object.keys(window.MODKIT_ASSEMBLIES).map(k => [k, A.check(window.MODKIT_ASSEMBLIES[k]).ok]);
      const noType = A.check({ components: [{ id: 'x' }] });
      const dup = A.check({ components: [
        { id: 'a', type: 'frame.chassis_160', parent: null },
        { id: 'a', type: 'frame.chassis_160', parent: null }
      ] });
      return { good: good.ok, all: all, noType: noType.ok, noTypeErr: noType.errors[0],
               dup: dup.ok, dupErr: dup.errors[0] };
    """)
    assert out["good"] is True
    assert all(ok for _, ok in out["all"]), out["all"]
    assert out["noType"] is False and "type" in out["noTypeErr"]
    assert out["dup"] is False and "重复" in out["dupErr"]


def test_budget_plan_reaches_and_reports_shortfall():
    out = run_core("""
      const hit = B.plan(window.MODKIT_ASSEMBLIES.m1, 1000, 4);
      const miss = B.plan(window.MODKIT_ASSEMBLIES.m1, 900, 4);
      const cut = B.plan(window.MODKIT_ASSEMBLIES.m1, 900, 4, { maxNodes: 1 });
      return {
        hit: { reached: hit.reached, cost: hit.cost, steps: hit.steps.map(s => s.id),
               components: hit.assembly.components.length },
        miss: { reached: miss.reached, cost: miss.cost, remaining: miss.remaining,
                steps: miss.steps.map(s => s.id) },
        cut: { truncated: cut.truncated, steps: cut.steps, cost: cut.cost }
      };
    """)
    assert out["hit"]["reached"] is True
    assert out["hit"]["cost"] == 968.0
    assert out["hit"]["steps"] == ["drop-elbow"]
    assert out["hit"]["components"] == 15
    assert out["miss"]["reached"] is False
    assert out["miss"]["steps"] == ["drop-elbow", "swap-link.beam_100-link.beam_60"]
    assert abs(out["miss"]["cost"] - 964.4) < 0.2
    assert abs(out["miss"]["remaining"] - 64.4) < 0.2
    assert out["cut"]["truncated"] is True
    assert out["cut"]["steps"] == []
    assert abs(out["cut"]["cost"] - 1127.4) < 0.2


def test_optimizer_mass_only_candidate_is_opt_in():
    out = run_core("""
      const normal = B.suggest(window.MODKIT_ASSEMBLIES.m1);
      const mass = B.suggest(window.MODKIT_ASSEMBLIES.m1, { includeMass: true });
      const c = mass.find(x => x.id === 'swap-frame.chassis_240-frame.chassis_160');
      return { normal: normal.map(x => x.id), cost: c.cost, saving: c.saving,
               massSaving: c.massSaving, components: c.components };
    """)
    assert "swap-frame.chassis_240-frame.chassis_160" not in out["normal"]
    assert abs(out["saving"]) < 0.01
    assert abs(out["massSaving"] - 80.0) < 0.2
    assert abs(out["cost"] - 1127.4) < 0.2
    assert out["components"] == 18


def test_optimizer_markdown_report():
    out = run_core("""
      const cs = B.suggest(window.MODKIT_ASSEMBLIES.m1);
      const plan = B.plan(window.MODKIT_ASSEMBLIES.m1, 900, 4);
      return { md: B.reportMarkdown(cs, 1127.4, 'm1', plan), n: cs.length };
    """)
    assert out["n"] >= 2
    assert out["md"].startswith("# 预算优化：m1")
    assert "去掉肘关节" in out["md"]
    assert "目标规划" in out["md"] and "未达标" in out["md"]
    assert "单步候选" in out["md"]


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
    assert 'id="optimize"' in html and 'id="export-optimizer"' in html
    assert 'id="undo"' in html and 'id="redo"' in html
    assert 'id="plan-budget"' in html
    assert 'id="share-design"' in html
    assert "assembly-core.js" in html and "designer.js" in html
