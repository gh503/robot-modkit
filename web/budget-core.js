/* 预算优化器：在浏览器里生成"可验证的降本候选"。
 *
 * 只做保守的结构替换：换更小的标准件、缩短方梁、去掉肘关节；
 * 每个候选都重新走 MODKIT_ASSEMBLY.validate，不通过就不展示。
 * 不改变工具/任务能力的地方标 low，改变构型能力的地方标 high。
 */
(function (root) {
  "use strict";

  function create(A, C) {
    var SUBSTITUTIONS = [
      { from: "frame.chassis_240", to: "frame.chassis_160",
        title: "换 160 底盘", tradeoff: "轴距/支撑面变小，顶面件会自动收拢；重载余量下降", risk: "high" },
      { from: "frame.deck_160x100", to: "frame.deck_120x80",
        title: "换 120×80 甲板", tradeoff: "顶面面积变小，顶面件自动收拢；重载刚性下降", risk: "medium" },
      { from: "frame.mast_200", to: "frame.mast_100",
        title: "换 100mm 立柱", tradeoff: "安装高度降低 100mm，相机/传感器视野下降", risk: "medium" },
      { from: "link.beam_200", to: "link.beam_140",
        title: "缩短 200→140 方梁", tradeoff: "臂展减少 60mm，末端位置随之改变", risk: "medium" },
      { from: "link.beam_140", to: "link.beam_100",
        title: "缩短 140→100 方梁", tradeoff: "臂展减少 40mm，末端位置随之改变", risk: "medium" },
      { from: "link.beam_100", to: "link.beam_60",
        title: "缩短 100→60 方梁", tradeoff: "臂展减少 40mm，末端位置随之改变", risk: "medium" },
      { from: "tool.gripper_70", to: "tool.gripper_40",
        title: "换 40mm 夹爪", tradeoff: "夹持宽度 70→40mm，大件抓取能力下降", risk: "low" }
    ];

    function clone(x) { return JSON.parse(JSON.stringify(x)); }
    function byId(asm, id) {
      for (var i = 0; i < asm.components.length; i++) if (asm.components[i].id === id) return asm.components[i];
      return null;
    }
    function childrenOf(asm, id) {
      return asm.components.filter(function (c) { return c.parent === id; });
    }
    function descendants(asm, id) {
      var out = [], stack = childrenOf(asm, id);
      while (stack.length) {
        var c = stack.shift();
        out.push(c);
        stack = stack.concat(childrenOf(asm, c.id));
      }
      return out;
    }
    function componentDef(c) { return c && C[c.type] ? C[c.type] : null; }
    function portDef(comp, name) {
      var d = componentDef(comp);
      if (!d) return null;
      for (var i = 0; i < d.ports.length; i++) if (d.ports[i].name === name) return d.ports[i];
      return null;
    }
    function hasPort(comp, name) {
      return (componentDef(comp) || { ports: [] }).ports.some(function (p) { return p.name === name; });
    }
    function childPortFor(comp, parentPort) {
      if (!parentPort) return null;
      if (parentPort.kind === "mech.disc" && hasPort(comp, "disc")) return "disc";
      if (parentPort.kind === "mech.grid" && hasPort(comp, "mount")) return "mount";
      if (hasPort(comp, "mount")) return "mount";
      if (hasPort(comp, "disc")) return "disc";
      return null;
    }
    function report(asm) {
      try { return A.validate(asm); }
      catch (e) { return null; }
    }
    function candidate(base, baseReport, asm, id, title, tradeoff, risk, changes) {
      var r = report(asm);
      if (!r || !r.ok) return null;
      var saving = baseReport.totalCost - r.totalCost;
      if (!(saving > 0.01)) return null;
      return {
        id: id,
        title: title,
        tradeoff: tradeoff,
        risk: risk,
        changes: changes || [],
        saving: saving,
        cost: r.totalCost,
        mass: r.totalMass,
        components: r.instances.length,
        joints: r.instances.filter(function (i) { return i.joint && i.joint.mode === "position"; }).length,
        assembly: asm
      };
    }

    // 去掉肘关节及其下游转接/前臂，把末端工具直接装回父件。
    // 这是 m1 → m1_budget 的结构，不是"少一个滑杆"。
    function dropElbow(base, baseReport) {
      var out = [];
      var elbows = base.components.filter(function (c) { return c.type === "joint.elbow"; });
      elbows.forEach(function (elbow) {
        if (!elbow.parent) return;
        var parent = byId(base, elbow.parent);
        var parentPort = portDef(parent, elbow.port);
        if (!parent) return;
        var under = descendants(base, elbow.id);
        var tools = under.filter(function (c) { return c.type.indexOf("tool.") === 0; });
        if (tools.length !== 1) return;
        var tool = tools[0];
        var keep = {};
        keep[tool.id] = true;
        descendants(base, tool.id).forEach(function (c) { keep[c.id] = true; });
        var remove = {};
        remove[elbow.id] = true;
        under.forEach(function (c) { if (!keep[c.id]) remove[c.id] = true; });
        // 工具不能是肘关节的祖先，也不应该被删
        if (remove[tool.id]) return;
        var asm = clone(base);
        asm.components = asm.components.filter(function (c) { return !remove[c.id]; });
        var t = byId(asm, tool.id);
        var cp = childPortFor(t, parentPort);
        if (!cp) return;
        t.parent = parent.id;
        t.port = elbow.port;
        t.child_port = cp;
        t.at = [0, 0];
        t.spin = 0;
        var removedNames = Object.keys(remove).map(function (id) {
          var c = byId(base, id); return c ? (c.type + "(" + id + ")") : id;
        });
        var extraJoints = under.filter(function (c) {
          return c.id !== elbow.id && c.type.indexOf("joint.") === 0;
        });
        var title = "去掉肘关节 · 两关节定点抓放";
        var tradeoff = "失去肘关节后臂展固定，只能抓放与肩同半径的站点；不是通用三关节臂";
        if (extraJoints.length) {
          title = "去掉肘关节及下游 " + extraJoints.map(function (c) { return c.id; }).join("/") + " · 定点抓放";
          tradeoff = "除了肘关节，还会移除下游关节；末端姿态能力进一步下降，只剩偏航/肩";
        }
        var c = candidate(base, baseReport, asm, "drop-elbow", title, tradeoff,
          "high", ["移除 " + removedNames.join("、"), "把 " + tool.id + " 直接装到 " + parent.id + "/" + elbow.port]);
        if (c) out.push(c);
      });
      return out;
    }

    function clampAt(at, grid) {
      at = at || [0, 0];
      if (!grid) return [at[0] || 0, at[1] || 0];
      var lx = Math.max(0, Math.floor(((grid[0] - 20) / 2) / 20) * 20);
      var ly = Math.max(0, Math.floor(((grid[1] - 20) / 2) / 20) * 20);
      function clamp(v, lim) {
        var n = Math.round((v || 0) / 20) * 20;
        return Math.max(-lim, Math.min(lim, n));
      }
      return [clamp(at[0], lx), clamp(at[1], ly)];
    }

    function swap(base, baseReport, sub) {
      var hits = base.components.filter(function (c) { return c.type === sub.from; });
      if (!hits.length) return null;
      var asm = clone(base);
      var changes = [];
      for (var i = 0; i < asm.components.length; i++) {
        var c = asm.components[i];
        if (c.type !== sub.from) continue;
        var def = C[sub.to];
        if (!def) return null;
        c.type = sub.to;
        if (!hasPort(c, c.child_port)) c.child_port = childPortFor(c, null);
        // 新底盘的顶面网格变小：把直接挂在上面的 at 收进新网格。
        childrenOf(asm, c.id).forEach(function (kid) {
          var p = portDef(c, kid.port);
          if (p && p.kind === "mech.grid" && p.grid) kid.at = clampAt(kid.at, p.grid);
        });
        changes.push(c.id + ": " + sub.from + " → " + sub.to);
      }
      var id = "swap-" + sub.from + "-" + sub.to;
      return candidate(base, baseReport, asm, id, sub.title, sub.tradeoff, sub.risk, changes);
    }

    function suggest(assembly, opts) {
      opts = opts || {};
      var base = clone(assembly);
      var baseReport = report(base);
      if (!baseReport || !baseReport.ok) return [];
      var out = dropElbow(base, baseReport);
      SUBSTITUTIONS.forEach(function (s) {
        var c = swap(base, baseReport, s);
        if (c) out.push(c);
      });
      // 去重：同一 id 只留一个；按省钱从多到少。
      var seen = {};
      out = out.filter(function (c) {
        if (seen[c.id]) return false;
        seen[c.id] = true;
        return true;
      });
      out.sort(function (a, b) { return b.saving - a.saving; });
      return out.slice(0, opts.max || 8);
    }

    function apply(assembly, cand) {
      if (!cand || !cand.assembly) return null;
      return clone(cand.assembly);
    }

    function reportMarkdown(cands, baseCost, title) {
      function md(v) { return String(v == null ? "" : v).replace(/\|/g, "\\|").replace(/\n/g, " "); }
      var lines = ["# 预算优化：" + md(title || "装配"), "",
                   "当前 BOM：¥" + Number(baseCost).toFixed(1), ""];
      if (!cands || !cands.length) {
        lines.push("没有找到既省钱又能通过校验的单步候选。");
        return lines.join("\n") + "\n";
      }
      lines.push("| # | 候选 | 省 ¥ | 应用后 ¥ | 组件/关节 | 风险 | 代价 |");
      lines.push("|---:|---|---:|---:|---|---|---|");
      cands.forEach(function (c, i) {
        lines.push("| " + (i + 1) + " | " + md(c.title) + " | " + Number(c.saving).toFixed(1) +
          " | " + Number(c.cost).toFixed(1) + " | " + c.components + "/" + c.joints +
          " | " + md(c.risk) + " | " + md(c.tradeoff) + " |");
        if (c.changes && c.changes.length) {
          lines.push("| | " + c.changes.map(md).join("<br>") + " | | | | | |");
        }
      });
      lines.push("", "> 单步候选，不是全局最优；候选都重新通过装配校验。", "");
      return lines.join("\n") + "\n";
    }

    return { SUBSTITUTIONS: SUBSTITUTIONS, suggest: suggest, apply: apply,
             reportMarkdown: reportMarkdown, clampAt: clampAt };
  }

  if (typeof module !== "undefined" && module.exports) module.exports = create;
  if (root) root.MODKIT_BUDGET = create(root.MODKIT_ASSEMBLY, root.MODKIT_COMPONENTS);
})(typeof window !== "undefined" ? window : globalThis);
