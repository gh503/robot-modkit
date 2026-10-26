/* modkit World：三维世界查看器。
 *
 * 定位：场景/流体属性的可视化和导入导出；真正的浅水/水箱/管道求解在
 * `modkit world run`。这里的水面动画只是视觉预览，不能当仿真结果。
 */
(function () {
  "use strict";

  var VERSION = "1.32.0";
  var PRESETS = ["pool", "lab", "kitchen", "greenhouse", "pipeline", "factory", "outdoor", "aquarium"];
  var $ = function (id) { return document.getElementById(id); };
  var state = {
    world: null, fluids: {}, selected: null, playing: true, t: 0,
    scene: null, camera: null, renderer: null, root: null, water: [],
    heightMesh: null, frames: null, frameIdx: 0, lastFrameAt: 0,
    theta: 0.8, phi: 1.05, radius: 12, target: new THREE.Vector3(0, 0.8, 0),
    drag: null, schema: "modkit.world/1"
  };

  function toast(msg) {
    var el = $("toast"); el.textContent = msg; el.classList.add("show");
    clearTimeout(toast._t); toast._t = setTimeout(function () { el.classList.remove("show"); }, 2400);
  }
  function fmt(v, n) {
    if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
    return Number(v).toFixed(n === undefined ? 3 : n);
  }
  function deg(d) { return (Number(d) || 0) * Math.PI / 180; }
  function vec(x, y, z) { return new THREE.Vector3(Number(x) || 0, Number(z) || 0, -(Number(y) || 0)); }

  // ------------------------------------------------------------ 世界几何
  function addEdges(mesh, color) {
    var e = new THREE.LineSegments(
      new THREE.EdgesGeometry(mesh.geometry, 25),
      new THREE.LineBasicMaterial({ color: color || 0x9fb3c8, transparent: true, opacity: 0.35 })
    );
    e.position.copy(mesh.position); e.rotation.copy(mesh.rotation); e.scale.copy(mesh.scale);
    state.root.add(e);
    return e;
  }

  function objectMesh(o) {
    var mat = new THREE.MeshPhongMaterial({
      color: new THREE.Color(o.color || "#8a96a8"),
      shininess: 18, transparent: (o.opacity !== undefined && o.opacity < 1),
      opacity: o.opacity === undefined ? 1 : o.opacity,
      side: THREE.DoubleSide, depthWrite: (o.opacity === undefined || o.opacity >= 1)
    });
    var mesh, x = o.position[0], y = o.position[1], z = o.position[2];
    if (o.type === "plane") {
      mesh = new THREE.Mesh(new THREE.PlaneGeometry(o.size[0], o.size[1]), mat);
      mesh.rotation.x = -Math.PI / 2;
      mesh.position.set(x, z, -y);
    } else if (o.type === "cylinder") {
      var r = Number(o.radius) || 0.2, h = Number(o.height) || 1;
      mesh = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, 28), mat);
      if (o.semantic === "pipe") {
        mesh.rotation.z = Math.PI / 2;
        mesh.position.set(x, z, -y);
      } else {
        mesh.position.set(x, z + h / 2, -y);
      }
    } else if (o.type === "sphere") {
      var rr = Number(o.radius) || 0.2;
      mesh = new THREE.Mesh(new THREE.SphereGeometry(rr, 24, 16), mat);
      mesh.position.set(x, z + rr, -y);
    } else if (o.type === "mesh" || o.type === "heightfield") {
      var s = o.size || [1, 1, 1];
      mesh = new THREE.Mesh(new THREE.BoxGeometry(s[0], s[2], s[1]), mat);
      mesh.position.set(x, z + s[2] / 2, -y);
      mesh.material.wireframe = true;
      mesh.material.opacity = 0.35;
      mesh.material.transparent = true;
      if (o.type === "mesh" && o.source && /\.obj(\?|$)/i.test(o.source)) loadOBJ(o, mesh);
    } else {
      var b = o.size || [1, 1, 1];
      mesh = new THREE.Mesh(new THREE.BoxGeometry(b[0], b[2], b[1]), mat);
      mesh.position.set(x, z + b[2] / 2, -y);
    }
    mesh.rotation.x = deg(o.rotation && o.rotation[0]);
    mesh.rotation.z = deg(o.rotation && o.rotation[1]);
    mesh.rotation.y = -deg(o.rotation && o.rotation[2]);
    mesh.userData.worldObject = o.id;
    state.root.add(mesh);
    var objLoading = o.type === "mesh" && o.source && /\.obj(\?|$)/i.test(o.source);
    if (!objLoading && (o.opacity === undefined || o.opacity > 0.2)) addEdges(mesh, o.semantic === "floor" ? 0x546a80 : 0x9fb3c8);
    return mesh;
  }

  function loadOBJ(o, placeholder) {
    var url = o.source;
    fetch(url, { cache: "no-store" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.text();
    }).then(function (text) {
      var verts = [], faces = [], lines = text.split(/\r?\n/);
      for (var i = 0; i < lines.length; i++) {
        var line = lines[i].trim();
        if (!line || line[0] === "#") continue;
        var parts = line.split(/\s+/);
        if (parts[0] === "v" && parts.length >= 4) {
          verts.push([parseFloat(parts[1]), parseFloat(parts[2]), parseFloat(parts[3])]);
        } else if (parts[0] === "f" && parts.length >= 4) {
          var f = [];
          for (var k = 1; k < parts.length; k++) {
            var idx = parseInt(parts[k].split("/")[0], 10);
            if (!isNaN(idx)) f.push(idx > 0 ? idx - 1 : verts.length + idx);
          }
          for (var t = 1; t + 1 < f.length; t++) faces.push([f[0], f[t], f[t + 1]]);
        }
      }
      if (!verts.length || !faces.length) throw new Error("OBJ 没有顶点/面");
      var pos = [], min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
      verts.forEach(function (v) {
        for (var j = 0; j < 3; j++) { min[j] = Math.min(min[j], v[j]); max[j] = Math.max(max[j], v[j]); }
      });
      var size = o.size || [1, 1, 1];
      var span = [max[0] - min[0] || 1, max[1] - min[1] || 1, max[2] - min[2] || 1];
      var scale = Math.min(size[0] / span[0], size[1] / span[1], size[2] / span[2]);
      var cx = (min[0] + max[0]) / 2, cy = (min[1] + max[1]) / 2, zmin = min[2];
      verts.forEach(function (v) {
        // OBJ 常见 Z-up；直接映射到世界 X/Y/Z，再转 Three Y-up
        pos.push((v[0] - cx) * scale, (v[2] - zmin) * scale, -(v[1] - cy) * scale);
      });
      var geo = new THREE.BufferGeometry();
      geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
      var idx = [];
      faces.forEach(function (f) { idx.push(f[0], f[1], f[2]); });
      geo.setIndex(idx); geo.computeVertexNormals();
      var mesh = new THREE.Mesh(geo, new THREE.MeshPhongMaterial({
        color: new THREE.Color(o.color || "#8a96a8"), shininess: 20,
        transparent: o.opacity < 1, opacity: o.opacity, side: THREE.DoubleSide
      }));
      mesh.position.set(o.position[0], o.position[2], -o.position[1]);
      mesh.rotation.y = -deg(o.rotation && o.rotation[2]);
      mesh.userData.worldObject = o.id;
      state.root.remove(placeholder);
      placeholder.geometry.dispose(); placeholder.material.dispose();
      state.root.add(mesh);
      addEdges(mesh, 0x7192ad);
    }).catch(function (e) {
      console.warn("OBJ 载入失败", url, e);
      if (placeholder.material) { placeholder.material.wireframe = true; placeholder.material.color.set(0xf85149); }
    });
  }

  function waterMesh(f, fluid) {
    if (!f || f.level <= 0) return null;
    var col = new THREE.Color((fluid && fluid.color) || f.color || "#3d8fd1");
    var op = (fluid && fluid.opacity !== undefined) ? fluid.opacity : (f.opacity === undefined ? 0.55 : f.opacity);
    var mat = new THREE.MeshPhongMaterial({
      color: col, transparent: true, opacity: Math.max(0.12, Math.min(0.9, op)),
      shininess: 90, specular: 0x9ed8ff, side: THREE.DoubleSide, depthWrite: false
    });
    var mesh, depth;
    if (f.type === "pipe") {
      var r = Number(f.radius) || 0.2, len = Number(f.height) || 1;
      mesh = new THREE.Mesh(new THREE.CylinderGeometry(r * Math.min(1, f.level + 0.35), r * Math.min(1, f.level + 0.35), len, 24), mat);
      mesh.rotation.z = Math.PI / 2;
      mesh.position.set(f.position[0], f.position[2], -f.position[1]);
      mesh.userData.isWater = true;
      state.root.add(mesh);
      return mesh;
    }
    if (f.type === "tank" && f.radius && f.height) {
      var tr = Number(f.radius), th = Number(f.height), td = th * f.level;
      mesh = new THREE.Mesh(new THREE.CylinderGeometry(tr, tr, Math.max(0.004, td), 28), mat);
      mesh.position.set(f.position[0], f.position[2] + Math.max(0.002, td) / 2, -f.position[1]);
      mesh.userData.isWater = true;
      state.root.add(mesh);
      return mesh;
    }
    var sx = f.size[0], sy = f.size[1], sz = f.size[2];
    depth = sz * (f.level === undefined ? 1 : f.level);
    mesh = new THREE.Mesh(new THREE.BoxGeometry(sx, Math.max(0.004, depth), sy), mat);
    mesh.position.set(f.position[0], f.position[2] + Math.max(0.002, depth) / 2, -f.position[1]);
    mesh.userData.isWater = true;
    state.root.add(mesh);
    // 水面高光片
    var surf = new THREE.Mesh(new THREE.PlaneGeometry(sx, sy),
      new THREE.MeshBasicMaterial({ color: 0xbfe6ff, transparent: true, opacity: 0.10, side: THREE.DoubleSide, depthWrite: false }));
    surf.rotation.x = -Math.PI / 2;
    surf.position.set(f.position[0], f.position[2] + Math.max(0.004, depth) + 0.002, -f.position[1]);
    surf.userData.isWaterSurface = true;
    state.root.add(surf);
    mesh.userData.surface = surf;
    return mesh;
  }

  function robotMesh() {
    var r = state.world.robot || { position: [0, 0, 0], yaw_deg: 0 };
    var g = new THREE.Group();
    var base = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.16, 0.22),
      new THREE.MeshPhongMaterial({ color: 0x2d6fa3, shininess: 50 }));
    base.position.y = 0.08; g.add(base);
    var mast = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.025, 0.42, 12),
      new THREE.MeshPhongMaterial({ color: 0x9aa7b8 }));
    mast.position.y = 0.37; g.add(mast);
    var arm = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.035, 0.045),
      new THREE.MeshPhongMaterial({ color: 0xd29922 }));
    arm.position.set(0.16, 0.56, 0); arm.rotation.z = -0.35; g.add(arm);
    var tip = new THREE.Mesh(new THREE.SphereGeometry(0.035, 12, 8),
      new THREE.MeshPhongMaterial({ color: 0xf0c674 }));
    tip.position.set(0.31, 0.50, 0); g.add(tip);
    g.position.set(Number(r.position[0]) || 0, Number(r.position[2]) || 0, -(Number(r.position[1]) || 0));
    g.rotation.y = -deg(r.yaw_deg);
    g.userData.robot = true;
    state.root.add(g);
    return g;
  }

  function sensorMesh(s) {
    var m = new THREE.Mesh(new THREE.SphereGeometry(0.035, 10, 8),
      new THREE.MeshBasicMaterial({ color: 0x3fb950 }));
    m.position.set(s.position[0], s.position[2] + 0.04, -s.position[1]);
    state.root.add(m);
    return m;
  }

  function clearRoot() {
    while (state.root.children.length) {
      var c = state.root.children.pop();
      c.traverse(function (o) {
        if (o.geometry) o.geometry.dispose();
        if (o.material) { if (Array.isArray(o.material)) o.material.forEach(function (x) { x.dispose(); }); else o.material.dispose(); }
      });
    }
    state.water = []; state.heightMesh = null;
  }

  function boundsCenter(w) {
    var min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
    (w.objects || []).forEach(function (o) {
      var p = o.position, s = o.size || [1, 1, 1];
      var dims = o.type === "cylinder" ? [2 * (o.radius || 0), 2 * (o.radius || 0), o.height || 0] :
        o.type === "sphere" ? [2 * (o.radius || 0), 2 * (o.radius || 0), 2 * (o.radius || 0)] :
        o.type === "plane" ? [s[0], s[1], 0] : s;
      for (var i = 0; i < 3; i++) { min[i] = Math.min(min[i], p[i]); max[i] = Math.max(max[i], p[i] + dims[i]); }
    });
    if (!isFinite(min[0])) return { c: [0, 0, 0], size: 8 };
    return { c: [(min[0] + max[0]) / 2, (min[1] + max[1]) / 2, (min[2] + max[2]) / 2],
      size: Math.max(2, max[0] - min[0], max[1] - min[1], max[2] - min[2]) };
  }

  function rebuild() {
    if (!state.world) return;
    clearRoot();
    var w = state.world;
    var center = boundsCenter(w);
    state.target.set(center.c[0], center.c[2], -center.c[1]);
    state.radius = Math.max(4, center.size * 1.4);
    (w.objects || []).forEach(objectMesh);
    (w.fluids || []).forEach(function (f) {
      var fluid = state.fluids[f.fluid];
      var m = waterMesh(f, fluid);
      if (m) state.water.push({ mesh: m, body: f });
    });
    robotMesh();
    (w.sensors || []).forEach(sensorMesh);
    rebuildStats();
    $("world-desc").textContent = w.description || "";
    $("json").value = JSON.stringify(w, null, 2);
    $("schema-badge").textContent = w.schema || state.schema;
    $("preset").value = PRESETS.indexOf(w.environment) >= 0 ? w.environment : "pool";
    populateBodies();
    // 场景替代色
    if (w.lighting && w.lighting.sky) {
      state.scene.background = new THREE.Color(w.lighting.sky);
      state.scene.fog = new THREE.Fog(new THREE.Color(w.lighting.sky), state.radius * 2.5, state.radius * 9);
    }
    $("legend").innerHTML = (w.fluids || []).slice(0, 5).map(function (f) {
      var fl = state.fluids[f.fluid] || {};
      return '<div><span class="sw" style="background:' + (fl.color || f.color || "#3d8fd1") + '"></span>' +
        (f.name || f.id) + " · " + (fl.name || f.fluid) + "</div>";
    }).join("") || '<div>无流体对象</div>';
  }

  function rebuildStats() {
    var w = state.world, vol = 0;
    (w.fluids || []).forEach(function (f) {
      if (f.volume_m3 !== undefined && f.volume_m3 !== null) vol += Number(f.volume_m3) || 0;
      else if (f.type === "pipe") vol += Math.PI * Math.pow(f.radius || 0, 2) * (f.height || 0) * (f.level || 0);
      else vol += (f.size[0] * f.size[1] * f.size[2]) * (f.level || 0);
    });
    var errs = validateBasic(w);
    $("stats").innerHTML =
      "<dt>对象</dt><dd>" + (w.objects || []).length + "</dd>" +
      "<dt>流体</dt><dd>" + (w.fluids || []).length + "</dd>" +
      "<dt>传感器</dt><dd>" + (w.sensors || []).length + "</dd>" +
      "<dt>水体积</dt><dd>" + fmt(vol, 2) + " m³</dd>" +
      "<dt>校验</dt><dd style=\"color:" + (errs.length ? "var(--bad)" : "var(--ok)") + "\">" +
      (errs.length ? errs.length + " 问题" : "PASS") + "</dd>";
  }

  function validateBasic(w) {
    var e = [];
    if (!w || w.schema !== "modkit.world/1") e.push("schema");
    if (w && w.units !== "m") e.push("units");
    if (!w || !Array.isArray(w.objects)) e.push("objects");
    if (!w || !Array.isArray(w.fluids)) e.push("fluids");
    (w && w.fluids || []).forEach(function (f) {
      if (!(f.level >= 0 && f.level <= 1)) e.push(f.id + ":level");
      if (!state.fluids[f.fluid] && !(w.custom_fluids || []).some(function (x) { return x.key === f.fluid; })) e.push(f.id + ":fluid");
    });
    return e;
  }

  function populateBodies() {
    var sel = $("body"); sel.innerHTML = "";
    (state.world.fluids || []).forEach(function (f) {
      var o = document.createElement("option");
      o.value = f.id; o.textContent = (f.name || f.id) + " (" + f.type + ")";
      sel.appendChild(o);
    });
    state.selected = state.world.fluids && state.world.fluids.length ? state.world.fluids[0].id : null;
    if (state.selected) sel.value = state.selected;
    syncBody();
  }

  function syncBody() {
    var f = (state.world.fluids || []).filter(function (x) { return x.id === state.selected; })[0];
    if (!f) return;
    $("level").value = Math.round((f.level === undefined ? 1 : f.level) * 100);
    $("level-out").textContent = $("level").value + "%";
    $("temp").value = f.temperature_c === undefined ? 20 : f.temperature_c;
    $("salinity").value = f.salinity_ppt === undefined ? 0 : f.salinity_ppt;
    $("fluid").value = f.fluid;
    showProps();
  }

  function showProps() {
    var key = $("fluid").value || "water";
    var fl = state.fluids[key] || { key: key, name: key, density_kg_m3: 0, viscosity_pa_s: 0,
      surface_tension_n_m: 0, yield_stress_pa: 0, category: "?" };
    var temp = Number($("temp").value) || 20, sal = Number($("salinity").value) || 0;
    var rho = Number(fl.density_kg_m3) || 0;
    var mu = Number(fl.viscosity_pa_s) || 0;
    if (fl.category === "water" && sal) rho += 0.8 * sal;
    if (fl.category === "water" && temp !== 20) rho = rho / (1 + 2.07e-4 * (temp - 20));
    $("props").innerHTML =
      "<dt>材料</dt><dd>" + (fl.name || key) + "</dd>" +
      "<dt>类别</dt><dd>" + (fl.category || "?") + "</dd>" +
      "<dt>密度</dt><dd>" + fmt(rho, 1) + " kg/m³</dd>" +
      "<dt>动力粘度</dt><dd>" + fmt(mu, 5) + " Pa·s</dd>" +
      "<dt>运动粘度</dt><dd>" + fmt(mu / (rho || 1), 7) + " m²/s</dd>" +
      "<dt>表面张力</dt><dd>" + fmt(fl.surface_tension_n_m, 4) + " N/m</dd>" +
      "<dt>屈服应力</dt><dd>" + fmt(fl.yield_stress_pa, 2) + " Pa</dd>" +
      "<dt>温度/盐度</dt><dd>" + temp + " °C / " + sal + " ppt</dd>";
  }

  // ------------------------------------------------------------ 载入
  function loadFluids() {
    return fetch("./data/fluids.json", { cache: "no-store" }).then(function (r) { return r.json(); })
      .then(function (rows) {
        state.fluids = {}; rows.forEach(function (f) { state.fluids[f.key] = f; });
        var sel = $("fluid"); sel.innerHTML = "";
        rows.forEach(function (f) {
          var o = document.createElement("option"); o.value = f.key;
          o.textContent = f.name + " · " + f.category; sel.appendChild(o);
        });
      });
  }

  function loadPreset(key) {
    return fetch("./data/world-" + key + ".json", { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("没有 world-" + key + ".json"); return r.json(); })
      .then(function (w) { setWorld(w); toast("已加载 " + (w.name || key)); });
  }

  function setWorld(w) {
    state.world = w;
    state.frames = null; state.frameIdx = 0;
    rebuild();
    $("run-label").textContent = "视觉预览";
  }

  function loadFile(file, asFrames) {
    var reader = new FileReader();
    reader.onload = function () {
      try {
        var d = JSON.parse(String(reader.result));
        if (asFrames) { loadFrames(d); return; }
        setWorld(d); toast("已导入 " + (d.name || "世界"));
      } catch (e) { toast("JSON 解析失败：" + e.message); }
    };
    reader.readAsText(file);
  }

  function loadFrames(d) {
    // 支持 {body: [frames...]} 或单个 body 的 frames 数组
    var bodyId = null, frames = null;
    if (Array.isArray(d)) { frames = d; bodyId = state.selected; }
    else {
      var keys = Object.keys(d || {});
      if (!keys.length) { toast("frames.json 为空"); return; }
      bodyId = state.selected && d[state.selected] ? state.selected : keys[0];
      frames = d[bodyId];
    }
    if (!Array.isArray(frames) || !frames.length) { toast("没有帧"); return; }
    state.frames = { bodyId: bodyId, rows: frames }; state.frameIdx = frames.length - 1;
    drawHeightFrame();
    $("frames-note").textContent = "已载入 " + frames.length + " 帧（" + bodyId + "）；这是求解器输出快照。";
    toast("已载入 " + frames.length + " 帧");
  }

  function drawHeightFrame() {
    if (!state.frames) return;
    if (state.heightMesh) { state.root.remove(state.heightMesh); state.heightMesh.geometry.dispose(); state.heightMesh.material.dispose(); state.heightMesh = null; }
    var fr = state.frames.rows[Math.min(state.frameIdx, state.frames.rows.length - 1)];
    if (!fr || !fr.height_m) return;
    var body = (state.world.fluids || []).filter(function (f) { return f.id === state.frames.bodyId; })[0];
    var sx = body ? body.size[0] : (fr.nx - 1) * fr.dx;
    var sy = body ? body.size[1] : (fr.ny - 1) * fr.dx;
    var z0 = body ? body.position[2] : 0;
    var ox = body ? body.position[0] - sx / 2 : 0;
    var oy = body ? body.position[1] - sy / 2 : 0;
    var geo = new THREE.BufferGeometry();
    var pos = [], col = [], idx = [];
    var hmax = 1e-6;
    fr.height_m.forEach(function (row) { row.forEach(function (h) { hmax = Math.max(hmax, h); }); });
    for (var y = 0; y < fr.ny; y++) {
      for (var x = 0; x < fr.nx; x++) {
        var h = fr.height_m[y][x];
        pos.push(ox + (x + 0.5) * sx / fr.nx, z0 + h, -(oy + (y + 0.5) * sy / fr.ny));
        var t = Math.max(0, Math.min(1, h / hmax));
        col.push(0.12 + 0.3 * t, 0.35 + 0.45 * t, 0.6 + 0.35 * t);
      }
    }
    for (var yy = 0; yy < fr.ny - 1; yy++) {
      for (var xx = 0; xx < fr.nx - 1; xx++) {
        var a = yy * fr.nx + xx, b = a + 1, c = a + fr.nx, d = c + 1;
        idx.push(a, c, b, b, c, d);
      }
    }
    geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    geo.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
    geo.setIndex(idx); geo.computeVertexNormals();
    var mat = new THREE.MeshPhongMaterial({ vertexColors: true, side: THREE.DoubleSide,
      transparent: true, opacity: 0.82, shininess: 60, depthWrite: false });
    state.heightMesh = new THREE.Mesh(geo, mat);
    state.root.add(state.heightMesh);
    state.water.forEach(function (w) { w.mesh.visible = false; });
  }

  // ------------------------------------------------------------ 交互
  function applyFluid() {
    var f = (state.world.fluids || []).filter(function (x) { return x.id === state.selected; })[0];
    if (!f) { toast("没有选中流体"); return; }
    f.fluid = $("fluid").value;
    f.level = Number($("level").value) / 100;
    f.temperature_c = Number($("temp").value);
    f.salinity_ppt = Number($("salinity").value);
    rebuild();
    toast("已应用：液位 " + Math.round(f.level * 100) + "%，" + f.fluid);
  }

  function applyJson() {
    try {
      var d = JSON.parse($("json").value);
      var e = validateBasic(d);
      if (e.length) { toast("校验失败：" + e.join("，")); return; }
      setWorld(d); toast("JSON 已应用");
    } catch (err) { toast("JSON 解析失败：" + err.message); }
  }

  function exportJson() {
    var blob = new Blob([JSON.stringify(state.world, null, 2) + "\n"], { type: "application/json" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "world-" + (state.world.environment || "custom") + ".json";
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
    toast("已导出 JSON");
  }

  function copyJson() {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(JSON.stringify(state.world, null, 2))
        .then(function () { toast("已复制"); }).catch(function () { toast("复制失败"); });
    } else { toast("浏览器不支持剪贴板"); }
  }

  // ------------------------------------------------------------ 相机/渲染
  function initThree() {
    var canvas = $("canvas");
    state.scene = new THREE.Scene();
    state.scene.background = new THREE.Color(0x0b1017);
    state.camera = new THREE.PerspectiveCamera(45, 1, 0.02, 400);
    state.renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: false });
    state.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    state.root = new THREE.Group(); state.scene.add(state.root);
    var hemi = new THREE.HemisphereLight(0xbfe6ff, 0x2a3440, 0.75); state.scene.add(hemi);
    var sun = new THREE.DirectionalLight(0xffffff, 1.0); sun.position.set(8, 14, 6); state.scene.add(sun);
    var fill = new THREE.DirectionalLight(0x7fb7e6, 0.35); fill.position.set(-6, 5, -8); state.scene.add(fill);
    var grid = new THREE.GridHelper(40, 40, 0x33465c, 0x1c2a3a);
    grid.position.y = 0.001; state.scene.add(grid);
    resize();
    window.addEventListener("resize", resize);
    canvas.addEventListener("pointerdown", function (e) {
      state.drag = { x: e.clientX, y: e.clientY, button: e.button };
      canvas.setPointerCapture(e.pointerId);
    });
    canvas.addEventListener("pointermove", function (e) {
      if (!state.drag) return;
      var dx = e.clientX - state.drag.x, dy = e.clientY - state.drag.y;
      if (state.drag.button === 2) {
        var right = new THREE.Vector3().subVectors(state.camera.position, state.target).cross(new THREE.Vector3(0, 1, 0)).normalize();
        var up = new THREE.Vector3(0, 1, 0);
        state.target.addScaledVector(right, -dx * state.radius * 0.0015);
        state.target.addScaledVector(up, dy * state.radius * 0.0015);
      } else {
        state.theta -= dx * 0.005;
        state.phi = Math.max(0.18, Math.min(1.5, state.phi - dy * 0.004));
      }
      state.drag.x = e.clientX; state.drag.y = e.clientY;
    });
    canvas.addEventListener("pointerup", function () { state.drag = null; });
    canvas.addEventListener("contextmenu", function (e) { e.preventDefault(); });
    canvas.addEventListener("wheel", function (e) {
      e.preventDefault(); state.radius = Math.max(1.5, Math.min(80, state.radius * (1 + e.deltaY * 0.0012)));
    }, { passive: false });
    animate();
  }

  function resize() {
    if (!state.renderer) return;
    var el = $("stage"), w = el.clientWidth, h = el.clientHeight;
    state.renderer.setSize(w, h, false);
    state.camera.aspect = w / Math.max(1, h);
    state.camera.updateProjectionMatrix();
  }

  function updateCamera() {
    var s = Math.sin(state.phi), c = Math.cos(state.phi);
    state.camera.position.set(
      state.target.x + state.radius * s * Math.sin(state.theta),
      state.target.y + state.radius * c,
      state.target.z + state.radius * s * Math.cos(state.theta)
    );
    state.camera.lookAt(state.target);
  }

  function animate(now) {
    requestAnimationFrame(animate);
    state.t += 0.016;
    updateCamera();
    if (state.playing && !state.frames) {
      state.water.forEach(function (w, i) {
        if (w.mesh.userData.surface) w.mesh.userData.surface.position.y += Math.sin(state.t * 2 + i) * 0.00008;
      });
    }
    if (state.frames && state.playing && now - state.lastFrameAt > 180) {
      state.lastFrameAt = now;
      state.frameIdx = (state.frameIdx + 1) % state.frames.rows.length;
      drawHeightFrame();
    }
    state.renderer.render(state.scene, state.camera);
  }

  // ------------------------------------------------------------ 绑定
  function bind() {
    $("preset").addEventListener("change", function () { loadPreset(this.value); });
    $("load-preset").addEventListener("click", function () { loadPreset($("preset").value); });
    $("file").addEventListener("change", function () { if (this.files[0]) loadFile(this.files[0], false); this.value = ""; });
    $("body").addEventListener("change", function () { state.selected = this.value; syncBody(); });
    $("fluid").addEventListener("change", showProps);
    $("temp").addEventListener("input", showProps);
    $("salinity").addEventListener("input", showProps);
    $("level").addEventListener("input", function () { $("level-out").textContent = this.value + "%"; });
    $("apply").addEventListener("click", applyFluid);
    $("apply-json").addEventListener("click", applyJson);
    $("copy-json").addEventListener("click", copyJson);
    $("export").addEventListener("click", exportJson);
    $("play").addEventListener("click", function () {
      state.playing = !state.playing;
      this.textContent = state.playing ? "暂停" : "播放";
      this.setAttribute("aria-pressed", state.playing ? "true" : "false");
      $("run-label").textContent = state.playing ? (state.frames ? "帧回放" : "视觉预览") : "已暂停";
    });
    $("reset-view").addEventListener("click", function () {
      var c = boundsCenter(state.world || { objects: [] });
      state.target.set(c.c[0], c.c[2], -c.c[1]);
      state.theta = 0.8; state.phi = 1.05; state.radius = Math.max(4, c.size * 1.4);
    });
    $("load-frames").addEventListener("click", function () { $("frames-file").click(); });
    $("frames-file").addEventListener("change", function () { if (this.files[0]) loadFile(this.files[0], true); this.value = ""; });
  }

  function boot() {
    initThree(); bind();
    loadFluids().then(function () {
      var q = new URLSearchParams(location.search).get("world");
      if (q) return fetch(q, { cache: "no-store" }).then(function (r) { return r.json(); }).then(setWorld);
      return loadPreset("pool");
    }).catch(function (e) {
      console.error(e); toast("载入失败：" + e.message);
    });
  }

  window.MODKIT_WORLD = {
    version: VERSION, state: state, presets: PRESETS,
    loadPreset: loadPreset, setWorld: setWorld, applyFluid: applyFluid,
    applyJson: applyJson, validateBasic: validateBasic
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
