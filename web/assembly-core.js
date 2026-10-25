/* 浏览器端装配求解/校验核心。
 *
 * 这是 software/modkit/assembly.py 的"同语义子集"：只做刚性端口装配、
 * BOM/质量/功率/重心、AABB 碰撞、关节静载；不假装是网格碰撞或动力学。
 * 纯函数 + 列主序 4×4 矩阵（和 three.js 一致），可在 node 里直接测试。
 */
(function (root, factory) {
  var api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.MODKIT_ASSEMBLY = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";

  var ERROR = "error", WARN = "warn", INFO = "info";
  var GRID = 20;

  function identity() {
    return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  }
  function multiply(a, b) {
    var o = new Array(16);
    for (var c = 0; c < 4; c++) {
      for (var r = 0; r < 4; r++) {
        o[c * 4 + r] = a[r] * b[c * 4] + a[4 + r] * b[c * 4 + 1] +
          a[8 + r] * b[c * 4 + 2] + a[12 + r] * b[c * 4 + 3];
      }
    }
    return o;
  }
  function translation(x, y, z) {
    return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1];
  }
  function rotX(deg) {
    var a = deg * Math.PI / 180, c = Math.cos(a), s = Math.sin(a);
    return [1, 0, 0, 0, 0, c, s, 0, 0, -s, c, 0, 0, 0, 0, 1];
  }
  function rotY(deg) {
    var a = deg * Math.PI / 180, c = Math.cos(a), s = Math.sin(a);
    return [c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, 0, 0, 0, 1];
  }
  function rotZ(deg) {
    var a = deg * Math.PI / 180, c = Math.cos(a), s = Math.sin(a);
    return [c, s, 0, 0, -s, c, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  }
  function fromPose(pos, rot) {
    var m = translation(pos[0] || 0, pos[1] || 0, pos[2] || 0);
    m = multiply(m, rotZ(rot[2] || 0));
    m = multiply(m, rotY(rot[1] || 0));
    m = multiply(m, rotX(rot[0] || 0));
    return m;
  }
  function invertRigid(m) {
    // R^T, -R^T t
    var r = [
      m[0], m[4], m[8],
      m[1], m[5], m[9],
      m[2], m[6], m[10]
    ];
    var tx = m[12], ty = m[13], tz = m[14];
    return [
      r[0], r[1], r[2], 0,
      r[3], r[4], r[5], 0,
      r[6], r[7], r[8], 0,
      -(r[0] * tx + r[1] * ty + r[2] * tz),
      -(r[3] * tx + r[4] * ty + r[5] * tz),
      -(r[6] * tx + r[7] * ty + r[8] * tz),
      1
    ];
  }
  function apply(m, p) {
    return [
      m[0] * p[0] + m[4] * p[1] + m[8] * p[2] + m[12],
      m[1] * p[0] + m[5] * p[1] + m[9] * p[2] + m[13],
      m[2] * p[0] + m[6] * p[1] + m[10] * p[2] + m[14]
    ];
  }
  function close(a, b, eps) { return Math.abs(a - b) <= (eps || 1e-7); }
  function gridOk(v) { return Math.abs(v / GRID - Math.round(v / GRID)) < 1e-7; }

  function components() {
    return (typeof window !== "undefined" && window.MODKIT_COMPONENTS) ||
      (typeof globalThis !== "undefined" && globalThis.MODKIT_COMPONENTS) || {};
  }
  function getComp(id) {
    var c = components()[id];
    if (!c) throw new Error("未知组件 " + id);
    return c;
  }
  function portOf(comp, name) {
    for (var i = 0; i < (comp.ports || []).length; i++) {
      if (comp.ports[i].name === name) return comp.ports[i];
    }
    throw new Error(comp.id + " 没有端口 " + name);
  }
  function compatible(a, b) {
    if (a.kind !== b.kind) return false;
    if (a.kind === "mech.grid") return true;
    if (a.gender === "neutral" || b.gender === "neutral") return true;
    return a.gender !== b.gender;
  }
  function cloneJoint(j, override) {
    if (!j) return null;
    var out = {
      name: j.name, min: j.min, max: j.max, unit: j.unit || "deg",
      zero_ticks: j.zero_ticks, dir: j.dir, ticks_per_unit: j.ticks_per_unit,
      max_step: j.max_step, rated_torque_nm: j.rated_torque_nm,
      mode: j.mode || "position", center: j.center || [0, 0, 30]
    };
    if (override) {
      if (override.name !== undefined) out.name = String(override.name);
      if (override.min !== undefined) out.min = Number(override.min);
      if (override.max !== undefined) out.max = Number(override.max);
      if (override.dir !== undefined) out.dir = Number(override.dir);
      if (override.max_step !== undefined) out.max_step = Number(override.max_step);
      if (override.rated_torque_nm !== undefined) out.rated_torque_nm = Number(override.rated_torque_nm);
      if (override.zero_ticks !== undefined) out.zero_ticks = Number(override.zero_ticks);
      if (override.mode !== undefined) out.mode = String(override.mode);
    }
    return out;
  }

  function normalize(raw) {
    var r = raw || {};
    var at = Array.isArray(r.at) ? r.at : [0, 0];
    var rot = Array.isArray(r.rot) ? r.rot : [0, 0, 0];
    return {
      id: String(r.id || ""),
      type: String(r.type || ""),
      parent: r.parent == null ? null : String(r.parent),
      port: r.port == null ? null : String(r.port),
      child_port: String(r.child_port || "mount"),
      at: [Number(at[0] || 0), Number(at[1] || 0)],
      spin: Number(r.spin || 0),
      rot: [Number(rot[0] || 0), Number(rot[1] || 0), Number(rot[2] || 0)],
      pose: Array.isArray(r.pose) && r.pose.length === 6 ? r.pose.map(Number) : null,
      servo_id: r.servo_id == null ? null : Number(r.servo_id),
      offboard: !!r.offboard,
      joint_override: r.joint || null,
      raw: r
    };
  }

  function aabb(world, bbox) {
    var pts = [], xs = [bbox[0], bbox[3]], ys = [bbox[1], bbox[4]], zs = [bbox[2], bbox[5]];
    for (var i = 0; i < 2; i++) for (var j = 0; j < 2; j++) for (var k = 0; k < 2; k++) {
      pts.push(apply(world, [xs[i], ys[j], zs[k]]));
    }
    return [
      Math.min.apply(null, pts.map(function (p) { return p[0]; })),
      Math.min.apply(null, pts.map(function (p) { return p[1]; })),
      Math.min.apply(null, pts.map(function (p) { return p[2]; })),
      Math.max.apply(null, pts.map(function (p) { return p[0]; })),
      Math.max.apply(null, pts.map(function (p) { return p[1]; })),
      Math.max.apply(null, pts.map(function (p) { return p[2]; }))
    ];
  }

  function validate(assembly, opts) {
    opts = opts || {};
    var issues = [];
    var ignore = {};
    (assembly.ignore_collision || []).forEach(function (p) {
      if (Array.isArray(p) && p.length === 2) ignore[[p[0], p[1]].sort().join("|")] = true;
    });
    function add(level, code, message, instance) {
      issues.push({ level: level, code: code, message: message, instance: instance || "" });
    }
    var raw = assembly.components || [];
    if (!Array.isArray(raw) || !raw.length) {
      add(ERROR, "components.empty", "components 不能为空");
      return { name: assembly.name || "unnamed", ok: false, issues: issues, instances: [],
        bom: [], totalMass: 0, totalCost: 0, power: null, stability: null, servoIds: {} };
    }
    var instances = raw.map(normalize);
    var byId = {}, seen = {};
    instances.forEach(function (i) {
      if (!i.id) add(ERROR, "id.empty", "组件 id 不能为空");
      if (seen[i.id]) add(ERROR, "id.duplicate", "组件 id 重复：" + i.id, i.id);
      seen[i.id] = true;
      byId[i.id] = i;
      try {
        i.component = getComp(i.type);
      } catch (e) {
        add(ERROR, "type.unknown", e.message, i.id);
        return;
      }
      i.joint = cloneJoint(i.component.joint, i.joint_override);
    });

    // offboard 电源：不参与机械根/几何，但参与功率/BOM。
    instances.forEach(function (i) {
      if (!i.offboard) return;
      if (i.parent) add(ERROR, "offboard.parent", i.id + ": offboard 不能有 parent", i.id);
      if (i.pose) i.world = fromPose(i.pose.slice(0, 3), i.pose.slice(3));
      else i.world = identity();
    });
    var roots = instances.filter(function (i) { return !i.parent && !i.offboard; });
    if (roots.length !== 1) {
      add(ERROR, "root.count", "必须有且只有一个机械根；当前 " + roots.length, roots.map(function (r) { return r.id; }).join(","));
      return { name: assembly.name || "unnamed", ok: false, issues: issues, instances: [],
        bom: [], totalMass: 0, totalCost: 0, power: null, stability: null, servoIds: {} };
    }
    var root = roots[0];
    root.world = root.pose ? fromPose(root.pose.slice(0, 3), root.pose.slice(3)) : identity();
    var used = {};
    function mark(parent, pname, dx, dy, child) {
      var key = parent.id + "|" + pname + "|" + dx.toFixed(3) + "|" + dy.toFixed(3);
      if (used[key]) {
        add(ERROR, "port.reuse", "孔位被 " + used[key] + " 占用", child.id);
        return false;
      }
      used[key] = child.id;
      var count = 0;
      Object.keys(used).forEach(function (k) {
        if (k.indexOf(parent.id + "|" + pname + "|") === 0) count++;
      });
      var port = portOf(parent.component, pname);
      if (count > port.max_uses) {
        add(ERROR, "port.max", parent.id + "." + pname + " 超过 max_uses=" + port.max_uses, child.id);
        return false;
      }
      return true;
    }
    function mate(parent, child) {
      if (!child.port) { add(ERROR, "port.missing", child.id + ": 缺少 parent 端口", child.id); return false; }
      var pp, cp;
      try { pp = portOf(parent.component, child.port); } catch (e) { add(ERROR, "port.unknown", e.message, child.id); return false; }
      try { cp = portOf(child.component, child.child_port); } catch (e) { add(ERROR, "port.unknown", e.message, child.id); return false; }
      if (pp.kind !== cp.kind) {
        add(ERROR, "port.kind", parent.id + "." + pp.name + " 是 " + pp.kind + "，" + child.id + "." + cp.name + " 是 " + cp.kind, child.id);
        return false;
      }
      if (!compatible(pp, cp)) { add(ERROR, "port.gender", "端口公母不匹配", child.id); return false; }
      if (pp.kind === "mech.grid") {
        if (!pp.grid) { add(ERROR, "grid.missing", parent.id + "." + pp.name + " 没有网格范围", parent.id); return false; }
        if (Math.abs(child.at[0]) > pp.grid[0] / 2 + 1e-9 || Math.abs(child.at[1]) > pp.grid[1] / 2 + 1e-9) {
          add(ERROR, "grid.range", child.id + ": at 超出网格范围", child.id); return false;
        }
        if (!gridOk(child.at[0]) || !gridOk(child.at[1])) {
          add(ERROR, "grid.pitch", child.id + ": at 必须是 20mm 整数倍", child.id); return false;
        }
      } else if (Math.abs(child.at[0]) > 1e-9 || Math.abs(child.at[1]) > 1e-9) {
        add(ERROR, "port.offset", child.id + ": 该端口不允许 at 偏移", child.id); return false;
      }
      if (Math.abs(child.spin / 90 - Math.round(child.spin / 90)) > 1e-7) {
        add(ERROR, "spin", child.id + ": spin 必须是 90° 整数倍", child.id); return false;
      }
      if (child.pose) { add(ERROR, "pose.parent", child.id + ": 有 parent 时不能给 pose", child.id); return false; }
      if (!mark(parent, pp.name, child.at[0], child.at[1], child)) return false;
      var want = multiply(parent.world, fromPose(pp.transform.slice(0, 3), pp.transform.slice(3)));
      want = multiply(want, translation(child.at[0], child.at[1], 0));
      want = multiply(want, rotZ(child.spin));
      want = multiply(want, fromPose([0, 0, 0], child.rot));
      child.world = multiply(want, invertRigid(fromPose(cp.transform.slice(0, 3), cp.transform.slice(3))));
      return true;
    }
    var unresolved = {};
    instances.forEach(function (i) { if (i !== root && !i.offboard) unresolved[i.id] = i; });
    var guard = 0;
    while (Object.keys(unresolved).length && guard++ < 10000) {
      var progressed = false;
      Object.keys(unresolved).forEach(function (id) {
        var i = unresolved[id];
        var p = byId[i.parent];
        if (!p) { add(ERROR, "parent.unknown", i.id + ": 父组件不存在", i.id); delete unresolved[id]; progressed = true; return; }
        if (!p.world || !p.component) return;
        mate(p, i);
        delete unresolved[id];
        progressed = true;
      });
      if (!progressed) break;
    }
    Object.keys(unresolved).forEach(function (id) { add(ERROR, "cycle", id + ": 父链有环或无法求解", id); });

    var solved = instances.filter(function (i) { return i.world && i.component; });
    if (solved.length !== instances.length) add(ERROR, "solve.incomplete", (instances.length - solved.length) + " 个组件未求解");

    // AABB 碰撞
    for (var a = 0; a < solved.length; a++) for (var b = a + 1; b < solved.length; b++) {
      var ia = solved[a], ib = solved[b];
      if (ia.offboard || ib.offboard) continue;
      if (ia.parent === ib.id || ib.parent === ia.id) continue;
      if (ignore[[ia.id, ib.id].sort().join("|")]) continue;
      var ba = aabb(ia.world, ia.component.bbox), bb = aabb(ib.world, ib.component.bbox);
      var ov = [Math.min(ba[3], bb[3]) - Math.max(ba[0], bb[0]),
        Math.min(ba[4], bb[4]) - Math.max(ba[1], bb[1]),
        Math.min(ba[5], bb[5]) - Math.max(ba[2], bb[2])];
      if (ov.every(function (v) { return v > 1; })) {
        var vol = ov[0] * ov[1] * ov[2];
        add(((opts.strict || assembly.strict) && vol > 500) ? ERROR : WARN, "collision.aabb",
          ia.id + " 与 " + ib.id + " 包围盒重叠约 " + Math.round(vol) + "mm³", ia.id);
      }
    }

    // 舵机 ID / 容量
    var servoIds = {}, usedIds = {}, next = 1;
    var maxServos = null;
    solved.forEach(function (i) {
      if (i.component.max_servos) maxServos = maxServos == null ? i.component.max_servos : Math.min(maxServos, i.component.max_servos);
    });
    solved.forEach(function (i) {
      if (!i.joint) return;
      var sid = i.servo_id;
      if (sid == null) { while (usedIds[next]) next++; sid = next; }
      if (usedIds[sid]) { add(ERROR, "servo.duplicate", "舵机 ID " + sid + " 重复", i.id); return; }
      usedIds[sid] = i.id; i.servo_id = sid; servoIds[i.id] = sid;
    });
    if (maxServos != null && Object.keys(servoIds).length > maxServos) {
      add(ERROR, "controller.capacity", Object.keys(servoIds).length + " 个舵机超过控制器上限 " + maxServos);
    }

    // 工具/载荷
    var tools = solved.filter(function (i) { return i.component.tool && !i.offboard; });
    var payload = Number(assembly.payload_g || 0);
    var payloadAt = null;
    if (tools.length) {
      var t = tools[tools.length - 1];
      payloadAt = apply(t.world, t.component.tool.tip.slice(0, 3));
      if (payload > t.component.tool.max_payload_g) {
        add(ERROR, "payload.max", "载荷 " + payload + "g > " + t.id + " 标称 " + t.component.tool.max_payload_g + "g", t.id);
      }
    } else if (payload > 0) add(WARN, "payload.no_tool", "设置了载荷但没有工具");

    // BOM / 质量
    var bomMap = {}, totalMass = 0, totalCost = 0;
    solved.forEach(function (i) {
      totalMass += i.component.mass_g || 0;
      (i.component.bom || []).forEach(function (b) {
        var key = b.name + "|" + b.spec;
        if (!bomMap[key]) bomMap[key] = { name: b.name, spec: b.spec, qty: 0, unit_cost: b.unit_cost, mass_g: 0, category: b.category };
        bomMap[key].qty += b.qty;
        bomMap[key].mass_g += b.mass_g; // b.mass_g 已经是该行总质量
      });
    });
    var bom = Object.keys(bomMap).map(function (k) {
      var x = bomMap[k];
      x.cost = x.qty * x.unit_cost;
      return x;
    }).sort(function (a, b) { return a.category.localeCompare(b.category) || a.name.localeCompare(b.name); });
    totalCost = bom.reduce(function (s, x) { return s + x.cost; }, 0);

    // 功率
    var idle = 0, peak = 0, supply = 0, sources = [];
    solved.forEach(function (i) {
      var p = i.component.power;
      if (!p) return;
      if ((p.supply_a || 0) > 0) { supply = Math.max(supply, p.supply_a); sources.push(i.id); }
      else { idle += p.idle_a || 0; peak += p.peak_a || 0; }
    });
    var planning = idle + 0.25 * Math.max(0, peak - idle);
    if (supply <= 0) add(WARN, "power.source", "没有电源组件（power.*）");
    else {
      if (planning > supply) add(ERROR, "power.planning", "规划电流 " + planning.toFixed(2) + "A > 电源 " + supply.toFixed(1) + "A");
      if (peak > supply) add(WARN, "power.peak", "峰值电流 " + peak.toFixed(2) + "A > 电源 " + supply.toFixed(1) + "A");
    }

    // 重心/支撑
    var sx = 0, sy = 0, sz = 0, mt = 0;
    solved.forEach(function (i) {
      if (i.offboard) return;
      var bb = i.component.bbox;
      var c = apply(i.world, [(bb[0] + bb[3]) / 2, (bb[1] + bb[4]) / 2, (bb[2] + bb[5]) / 2]);
      var m = i.component.mass_g || 0;
      mt += m; sx += c[0] * m; sy += c[1] * m; sz += c[2] * m;
    });
    if (payloadAt && payload > 0) { mt += payload; sx += payloadAt[0] * payload; sy += payloadAt[1] * payload; sz += payloadAt[2] * payload; }
    var com = mt > 0 ? [sx / mt, sy / mt, sz / mt] : null;
    var support = root.component.support;
    if (!support) {
      var rb = root.component.bbox;
      support = [[rb[0], rb[1]], [rb[3], rb[1]], [rb[3], rb[4]], [rb[0], rb[4]]];
    }
    var poly = support.map(function (p) { return apply(root.world, [p[0], p[1], 0]).slice(0, 2); });
    var hull = convexHull(poly);
    var inside = true, margin = null;
    if (com && hull.length >= 3) {
      inside = pointInPoly([com[0], com[1]], hull);
      margin = minEdge([com[0], com[1]], hull);
      if (!inside) { margin = -margin; add(ERROR, "stability.outside", "整机重心在支撑多边形外", root.id); }
      else if (margin < 10) add(WARN, "stability.margin", "重心离支撑边仅 " + margin.toFixed(1) + "mm", root.id);
    }
    var tip = (com && margin != null) ? 9.81 * Math.max(0, margin) / Math.max(1, com[2]) : null;

    // 关节静载
    var loads = [];
    solved.forEach(function (i) {
      if (!i.joint || i.joint.mode !== "position") return;
      var ids = {}; ids[i.id] = true;
      var changed = true;
      while (changed) {
        changed = false;
        solved.forEach(function (x) { if (!ids[x.id] && x.parent && ids[x.parent]) { ids[x.id] = true; changed = true; } });
      }
      var sub = solved.filter(function (x) { return ids[x.id] && x.id !== i.id; });
      var mass = sub.reduce(function (s, x) { return s + (x.component.mass_g || 0); }, 0);
      var wx = 0, wy = 0;
      sub.forEach(function (x) {
        var bb = x.component.bbox;
        var c = apply(x.world, [(bb[0] + bb[3]) / 2, (bb[1] + bb[4]) / 2, 0]);
        wx += c[0] * (x.component.mass_g || 0); wy += c[1] * (x.component.mass_g || 0);
      });
      if (payloadAt && payload > 0) { mass += payload; wx += payloadAt[0] * payload; wy += payloadAt[1] * payload; }
      if (mass <= 0) return;
      var center = apply(i.world, i.joint.center || [0, 0, 30]);
      var arm = Math.hypot(wx / mass - center[0], wy / mass - center[1]);
      var load = mass / 1000 * 9.81 * arm / 1000;
      var ratio = load / Math.max(i.joint.rated_torque_nm || 1e-9, 1e-9);
      loads.push({ instance: i.id, name: i.joint.name, servo_id: i.servo_id, rated: i.joint.rated_torque_nm,
        load: load, ratio: ratio, mass: mass, arm: arm });
      if (ratio > 1) add(ERROR, "joint.overload", i.id + "(" + i.joint.name + ") 静载 " + load.toFixed(2) + "N·m > 额定", i.id);
      else if (ratio > 0.5) add(WARN, "joint.margin", i.id + "(" + i.joint.name + ") 静载超过额定 50%", i.id);
    });

    // 位置关节名唯一 + safety
    var names = {}, joints = {}, cal = {};
    solved.forEach(function (i) {
      if (!i.joint || i.joint.mode !== "position") return;
      if (names[i.joint.name]) add(ERROR, "joint.duplicate", "位置关节名重复：" + i.joint.name, i.id);
      names[i.joint.name] = true;
      joints[i.joint.name] = { servo_id: i.servo_id, min: i.joint.min, max: i.joint.max,
        unit: i.joint.unit, zero_ticks: i.joint.zero_ticks, dir: i.joint.dir,
        ticks_per_unit: i.joint.ticks_per_unit, max_step: i.joint.max_step };
      cal[i.joint.name] = { name: i.joint.name, servo_id: i.servo_id, zero_ticks: i.joint.zero_ticks,
        dir: i.joint.dir, min_deg: i.joint.unit === "deg" ? i.joint.min : 0,
        max_deg: i.joint.unit === "deg" ? i.joint.max : 1, speed_unit: 1 };
    });

    // 概念件提示
    solved.forEach(function (i) { if (i.component.status === "concept") add(WARN, "component.concept", i.id + "(" + i.component.id + ") 是 concept 级", i.id); });

    var report = {
      name: assembly.name || "unnamed", ok: issues.every(function (x) { return x.level !== ERROR; }),
      issues: issues, instances: solved, bom: bom, totalMass: totalMass, totalCost: totalCost,
      power: { supply: supply, idle: idle, peak: peak, planning: planning, sources: sources },
      stability: { com: com, support: hull, margin: margin, tip: tip, inside: inside },
      jointLoads: loads, servoIds: servoIds,
      safety: Object.keys(joints).length ? { robot: assembly.name || "unnamed", calibrated: false, joints: joints } : null,
      calibration: Object.keys(cal).length ? { robot: assembly.name || "unnamed", created: "", joints: cal } : null,
      payload: payload
    };
    return report;
  }

  function convexHull(points) {
    var pts = points.map(function (p) { return [p[0], p[1]]; }).sort(function (a, b) { return a[0] - b[0] || a[1] - b[1]; });
    if (pts.length <= 1) return pts;
    function cross(o, a, b) { return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]); }
    var lo = [], up = [];
    pts.forEach(function (p) { while (lo.length >= 2 && cross(lo[lo.length - 2], lo[lo.length - 1], p) <= 0) lo.pop(); lo.push(p); });
    pts.slice().reverse().forEach(function (p) { while (up.length >= 2 && cross(up[up.length - 2], up[up.length - 1], p) <= 0) up.pop(); up.push(p); });
    lo.pop(); up.pop();
    return lo.concat(up);
  }
  function pointInPoly(p, poly) {
    var x = p[0], y = p[1], inside = false;
    for (var i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      var xi = poly[i][0], yi = poly[i][1], xj = poly[j][0], yj = poly[j][1];
      if (((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi)) inside = !inside;
    }
    return inside;
  }
  function minEdge(p, poly) {
    var best = Infinity;
    for (var i = 0; i < poly.length; i++) {
      var a = poly[i], b = poly[(i + 1) % poly.length];
      var dx = b[0] - a[0], dy = b[1] - a[1], den = dx * dx + dy * dy;
      var t = den < 1e-12 ? 0 : Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / den));
      best = Math.min(best, Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy)));
    }
    return best;
  }

  function svgReport(report, width, height) {
    width = width || 1000; height = height || 620;
    var boxes = report.instances.filter(function (i) { return !i.offboard; }).map(function (i) {
      return { i: i, b: aabb(i.world, i.component.bbox) };
    });
    if (!boxes.length) return '<svg xmlns="http://www.w3.org/2000/svg" width="' + width + '" height="' + height + '"></svg>';
    var minx = Math.min.apply(null, boxes.map(function (x) { return x.b[0]; }));
    var maxx = Math.max.apply(null, boxes.map(function (x) { return x.b[3]; }));
    var miny = Math.min.apply(null, boxes.map(function (x) { return x.b[1]; }));
    var maxy = Math.max.apply(null, boxes.map(function (x) { return x.b[4]; }));
    var minz = Math.min.apply(null, boxes.map(function (x) { return x.b[2]; }));
    var maxz = Math.max.apply(null, boxes.map(function (x) { return x.b[5]; }));
    var pad = 30, top = 70, bottom = 30;
    var panelW = (width - pad * 3) / 2, panelH = height - top - bottom;
    var scale = Math.min(panelW / Math.max(1, maxx - minx), panelH / Math.max(1, maxy - miny),
      panelW / Math.max(1, maxx - minx), panelH / Math.max(1, maxz - minz));
    var colors = { frame: "#7aa6c2", joint: "#e0a458", link: "#8fb573", adapter: "#b9a3c9", drive: "#6b8e9e", tool: "#d97b7b", sensor: "#c9b458", electronics: "#7f9f7f", power: "#a88b6a" };
    function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
    var out = ['<svg xmlns="http://www.w3.org/2000/svg" width="' + width + '" height="' + height + '" viewBox="0 0 ' + width + ' ' + height + '" font-family="sans-serif">',
      '<rect width="100%" height="100%" fill="#f7f6f2"/>',
      '<text x="30" y="32" font-size="20" font-weight="bold">装配预览 · ' + esc(report.name) + '</text>',
      '<text x="30" y="55" font-size="13" fill="#555">' + (report.ok ? "PASS" : "BLOCK") + ' · ' + report.instances.length + ' 组件 · ' + Math.round(report.totalMass) + 'g · ¥' + Math.round(report.totalCost) + '</text>',
      '<text x="' + pad + '" y="' + (top - 12) + '" font-size="13" fill="#666">俯视 XY</text>',
      '<text x="' + (pad * 2 + panelW) + '" y="' + (top - 12) + '" font-size="13" fill="#666">侧视 XZ</text>'];
    [[pad, top], [pad * 2 + panelW, top]].forEach(function (o) {
      out.push('<rect x="' + o[0] + '" y="' + o[1] + '" width="' + panelW + '" height="' + panelH + '" fill="#fff" stroke="#ddd"/>');
    });
    boxes.forEach(function (x) {
      var b = x.b, color = colors[x.i.component.category] || "#999";
      [[pad, top, 0, 1, minx, miny], [pad * 2 + panelW, top, 0, 2, minx, minz]].forEach(function (o) {
        var px = o[0] + (b[o[2]] - o[4]) * scale + 4;
        var py = o[1] + panelH - (b[o[3] + 3] - o[5]) * scale - 4;
        var w = Math.max(2, (b[o[2] + 3] - b[o[2]]) * scale);
        var h = Math.max(2, (b[o[3] + 3] - b[o[3]]) * scale);
        out.push('<rect x="' + px.toFixed(1) + '" y="' + py.toFixed(1) + '" width="' + w.toFixed(1) + '" height="' + h.toFixed(1) + '" fill="' + color + '" fill-opacity="0.35" stroke="' + color + '"/>');
        if (o[3] === 1) out.push('<text x="' + (px + 2).toFixed(1) + '" y="' + (py + 11).toFixed(1) + '" font-size="9" fill="#333">' + esc(x.i.id) + '</text>');
      });
    });
    if (report.stability && report.stability.support && report.stability.support.length) {
      var pts = report.stability.support.map(function (p) {
        return (pad + (p[0] - minx) * scale + 4).toFixed(1) + "," + (top + panelH - (p[1] - miny) * scale - 4).toFixed(1);
      }).join(" ");
      out.push('<polygon points="' + pts + '" fill="none" stroke="#2b7a4b" stroke-width="2" stroke-dasharray="5 4"/>');
    }
    out.push('</svg>');
    return out.join("\n");
  }

  return {
    ERROR: ERROR, WARN: WARN, INFO: INFO, GRID: GRID,
    identity: identity, multiply: multiply, translation: translation,
    rotX: rotX, rotY: rotY, rotZ: rotZ, fromPose: fromPose,
    invertRigid: invertRigid, apply: apply, aabb: aabb,
    compatible: compatible, getComp: getComp, components: components,
    validate: validate, svgReport: svgReport, convexHull: convexHull,
    pointInPoly: pointInPoly, minEdge: minEdge
  };
});
