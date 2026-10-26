/* modkit 结构查看器：只读 3D 预览任意自由设计。
 *
 * 输入：view.html#d=<base64url JSON>，也接受 ?preset=m1 或空输入回退到 M1 演示。
 * 只做“看结构”：校验、树/端口求解、按组件元数据建网格、点选、适配视角。
 * 编辑/运动/导出仍在 design.html；这里不写任何设计数据。
 */
(function () {
  "use strict";
  var C = window.MODKIT_COMPONENTS || {};
  var A = window.MODKIT_ASSEMBLY;
  var CAT_COLOR = {
    frame: "#7aa6c2", joint: "#e0a458", link: "#8fb573", adapter: "#b9a3c9",
    drive: "#6b8e9e", tool: "#d97b7b", sensor: "#c9b458", electronics: "#7f9f7f", power: "#a88b6a"
  };
  var state = {
    assembly: null, report: null, source: "", root: null, groups: {},
    scene: null, camera: null, renderer: null, controls: null,
    raycaster: null, pointer: null, helper: null, ground: null, grid: null,
    materials: {}, ready: false, started: false,
    jointVisuals: [], gripperVisuals: [], wheelVisuals: [], angles: {},
    playing: false, playStart: 0, speed: 1, exploded: false, fitPending: true,
    reduceMotion: !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches)
  };

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function clone(x) { return JSON.parse(JSON.stringify(x)); }
  function b64decode(text) {
    var s = String(text).replace(/-/g, "+").replace(/_/g, "/");
    while (s.length % 4) s += "=";
    return decodeURIComponent(escape(atob(s)));
  }
  function b64encode(text) {
    return btoa(unescape(encodeURIComponent(text))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }
  function status(text, kind) {
    var el = $("view-status");
    if (!el) return;
    el.textContent = text;
    el.className = "view-status " + (kind || "");
  }
  function fail(message) {
    status("无法显示", "err");
    var empty = $("view-empty");
    if (empty) {
      empty.hidden = false;
      empty.innerHTML = '<div class="empty-card"><h2>无法显示这个设计</h2><p>' + esc(message) +
        '</p><p><a href="design.html">回到 Studio 修改</a> · <a href="view.html">看 M1 演示</a></p></div>';
    }
  }

  // ---------------------------------------------------------------- 输入
  function decodeHash(text) {
    var data = JSON.parse(b64decode(text));
    var shape = A.check(data);
    if (!shape.ok) throw new Error(shape.errors.slice(0, 3).join("；"));
    return data;
  }
  function readInput() {
    var m = /^#d=(.+)$/.exec(location.hash || "");
    if (m) {
      try { return { assembly: decodeHash(m[1]), source: "分享的装配" }; }
      catch (e) { return { error: "分享链接无效：" + e.message }; }
    }
    var q = new URLSearchParams(location.search);
    var preset = q.get("preset");
    if (preset && window.MODKIT_ASSEMBLIES && window.MODKIT_ASSEMBLIES[preset]) {
      return { assembly: clone(window.MODKIT_ASSEMBLIES[preset]), source: "预设 " + preset };
    }
    if (window.MODKIT_ASSEMBLIES && window.MODKIT_ASSEMBLIES.m1) {
      return { assembly: clone(window.MODKIT_ASSEMBLIES.m1), source: "M1 演示（未提供设计）" };
    }
    return { error: "没有设计数据，也没有 M1 演示。" };
  }

  // ---------------------------------------------------------------- 3D 基础
  function initThree() {
    var canvas = $("view");
    if (!window.THREE) { $("view-fallback").classList.add("show"); status("three.js 未加载", "err"); return false; }
    try {
      state.renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true });
      state.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      state.renderer.shadowMap.enabled = true;
      state.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      if (THREE.SRGBColorSpace) state.renderer.outputColorSpace = THREE.SRGBColorSpace;
      if (THREE.ACESFilmicToneMapping) {
        state.renderer.toneMapping = THREE.ACESFilmicToneMapping;
        state.renderer.toneMappingExposure = 1.0;
      }
    } catch (e) {
      $("view-fallback").classList.add("show");
      status("3D 不可用：" + e.message, "err");
      return false;
    }
    state.scene = new THREE.Scene();
    state.scene.background = new THREE.Color(0xeaeff6);
    state.camera = new THREE.PerspectiveCamera(38, 1, 1, 10000);
    state.camera.up.set(0, 0, 1);
    state.camera.position.set(320, -380, 280);
    if (THREE.OrbitControls) {
      state.controls = new THREE.OrbitControls(state.camera, canvas);
      state.controls.enableDamping = true;
      state.controls.dampingFactor = 0.08;
      state.controls.minDistance = 80;
      state.controls.maxDistance = 4000;
      state.controls.maxPolarAngle = Math.PI * 0.5;
    } else {
      state.controls = { target: new THREE.Vector3(), update: function () {} };
    }
    state.scene.add(new THREE.HemisphereLight(0xffffff, 0x9aa4b2, 0.95));
    var dir = new THREE.DirectionalLight(0xfff6ec, 1.0);
    dir.position.set(300, -420, 620);
    dir.castShadow = true;
    dir.shadow.mapSize.set(2048, 2048);
    dir.shadow.camera.near = 50;
    dir.shadow.camera.far = 4000;
    dir.shadow.camera.left = -800;
    dir.shadow.camera.right = 800;
    dir.shadow.camera.top = 800;
    dir.shadow.camera.bottom = -800;
    dir.shadow.bias = -0.0009;
    state.scene.add(dir);
    var dir2 = new THREE.DirectionalLight(0xffffff, 0.35);
    dir2.position.set(-300, 250, 300);
    state.scene.add(dir2);
    state.raycaster = new THREE.Raycaster();
    state.pointer = new THREE.Vector2();
    state.ground = new THREE.Mesh(
      new THREE.PlaneGeometry(2000, 2000),
      new THREE.MeshStandardMaterial({ roughness: 0.72, metalness: 0.04, color: 0xf7f9fc })
    );
    state.ground.receiveShadow = true;
    state.scene.add(state.ground);
    state.grid = new THREE.GridHelper(1200, 24, 0xc8d2e0, 0xdfe6ef);
    state.grid.rotation.x = Math.PI / 2;
    state.scene.add(state.grid);
    state.ready = true;
    return true;
  }
  function resize() {
    if (!state.renderer) return;
    var el = $("viewport");
    var w = Math.max(320, el.clientWidth), h = Math.max(260, el.clientHeight);
    state.renderer.setSize(w, h);
    state.camera.aspect = w / h;
    state.camera.updateProjectionMatrix();
  }

  // ---------------------------------------------------------------- 几何
  function mat(cat) {
    if (!state.materials[cat]) {
      state.materials[cat] = new THREE.MeshStandardMaterial({
        color: new THREE.Color(CAT_COLOR[cat] || "#9aa4b2"),
        roughness: 0.62, metalness: 0.08
      });
    }
    return state.materials[cat];
  }
  function darker(hex, f) {
    var c = new THREE.Color(hex || "#9aa4b2");
    c.multiplyScalar(f || 0.72);
    return new THREE.MeshStandardMaterial({ color: c, roughness: 0.7, metalness: 0.08 });
  }
  function boxPart(g, w, d, h, m, x, y, z) {
    var mesh = new THREE.Mesh(new THREE.BoxGeometry(Math.max(0.8, w), Math.max(0.8, d), Math.max(0.8, h)), m);
    mesh.position.set(x || 0, y || 0, z || 0);
    mesh.castShadow = true; mesh.receiveShadow = true;
    g.add(mesh);
    return mesh;
  }
  function cylPart(g, r, h, m, x, y, z, axis) {
    var mesh = new THREE.Mesh(new THREE.CylinderGeometry(r, r, Math.max(0.8, h), 24), m);
    mesh.position.set(x || 0, y || 0, z || 0);
    if (axis === "x") mesh.rotation.z = Math.PI / 2;
    else if (axis === "z") mesh.rotation.x = Math.PI / 2;
    mesh.castShadow = true; mesh.receiveShadow = true;
    g.add(mesh);
    return mesh;
  }
  function edges(mesh, color) {
    if (!mesh || !mesh.geometry) return;
    var e = new THREE.LineSegments(
      new THREE.EdgesGeometry(mesh.geometry, 28),
      new THREE.LineBasicMaterial({ color: color || 0x34495e, transparent: true, opacity: 0.22 })
    );
    e.position.copy(mesh.position);
    e.rotation.copy(mesh.rotation);
    if (mesh.parent) mesh.parent.add(e);
  }

  function geometryFor(inst) {
    var c = inst.component, cat = c.category, b = c.bbox, d = c.dims;
    var g = new THREE.Group();
    var m = mat(cat), md = darker(CAT_COLOR[cat]);
    var W = b[3] - b[0], D = b[4] - b[1], H = b[5] - b[2];
    var cx = (b[0] + b[3]) / 2, cy = (b[1] + b[4]) / 2, cz = (b[2] + b[5]) / 2;
    var cad = c.cad || "";
    if (cat === "frame" && cad === "chassis") {
      boxPart(g, W, D, Math.max(3, H), m, cx, cy, cz);
      boxPart(g, W * 0.96, D * 0.96, 1.2, darker("#eef3f8", 0.98), cx, cy, b[5] + 0.6);
      boxPart(g, 2, D, 1.5, darker(CAT_COLOR[cat], 0.55), cx, cy, b[5] + 1.2);
    } else if (cat === "frame" || cat === "link" || (cat === "adapter" && cad !== "disc_grid")) {
      boxPart(g, Math.max(4, W), Math.max(4, D), Math.max(3, H), m, cx, cy, cz);
      edges(g.children[0], 0x34495e);
    } else if (cat === "adapter") {
      boxPart(g, 40, 40, 8, m, 0, 0, 4);
      cylPart(g, 16, 2, md, 0, 0, 8.5, "z");
    } else if (cat === "joint") {
      var bw = Math.min(56, Math.max(40, W * 0.86));
      var bd = Math.min(52, Math.max(36, D * 0.86));
      boxPart(g, bw, bd, 32, m, 0, 0, 20);
      boxPart(g, bw + 4, bd + 4, 4, md, 0, 0, 3);
      cylPart(g, 19, 6, md, 0, 0, 38, "z");
      cylPart(g, 8, 4, mat("electronics"), 0, 0, 41, "z");
      boxPart(g, 5, bd + 12, 20, md, -bw / 2 - 2, 0, 18);
      boxPart(g, 5, bd + 12, 20, md, bw / 2 + 2, 0, 18);
    } else if (cat === "drive" && cad === "wheel") {
      var r = Math.max(10, b[3]);
      var tire = cylPart(g, r, Math.max(12, D), darker("#33383f"), 0, 0, cz, "y");
      var hub = cylPart(g, r * 0.34, Math.max(14, D + 3), mat("electronics"), 0, 0, cz, "y");
      g.userData.wheel = tire;
      g.userData.hub = hub;
      edges(tire, 0x111111);
    } else if (cat === "drive" && cad === "caster") {
      boxPart(g, Math.min(40, W), Math.min(36, D), 8, m, 0, 0, -1);
      var ball = new THREE.Mesh(new THREE.SphereGeometry(9, 20, 14), md);
      ball.position.set(0, 0, b[2] + 7); ball.castShadow = true; g.add(ball);
    } else if (cat === "tool" && c.tool && c.tool.kind === "gripper") {
      boxPart(g, 60, 40, 40, m, 0, 0, 20);
      cylPart(g, 15, 6, md, 0, 0, 41, "z");
      var open = String(c.id).indexOf("70") >= 0 ? 70 : 40;
      var closed = open * 0.67;
      var jawLen = 54;
      var jawA = boxPart(g, 54, 6, jawLen, m, 0, 0, 42 + jawLen / 2);
      var jawB = boxPart(g, 54, 6, jawLen, m, 0, 0, 42 + jawLen / 2);
      g.userData.jaws = { a: jawA, b: jawB, open: open, closed: closed };
      g.userData.toolKind = "gripper";
      cylPart(g, 10, 5, md, 0, 0, 2, "z");
    } else if (cat === "tool" && c.tool && c.tool.kind === "pen") {
      boxPart(g, 34, 30, 34, m, 0, 0, 17);
      cylPart(g, 5, 44, mat("electronics"), 0, 0, 52, "z");
      var tip = new THREE.Mesh(new THREE.ConeGeometry(4, 10, 18), darker("#2f3b45"));
      tip.position.set(0, 0, 76); tip.rotation.x = Math.PI / 2; tip.castShadow = true; g.add(tip);
    } else if (cat === "tool" && c.tool && c.tool.kind === "vacuum") {
      boxPart(g, 40, 34, 32, m, 0, 0, 16);
      cylPart(g, 14, 8, md, 0, 0, 36, "z");
      cylPart(g, 10, 22, mat("electronics"), 0, 0, 51, "z");
      var cup = new THREE.Mesh(new THREE.CylinderGeometry(16, 13, 7, 24), darker("#b3261e"));
      cup.position.set(0, 0, 65); cup.castShadow = true; g.add(cup);
    } else if (cat === "sensor") {
      boxPart(g, Math.max(14, W), Math.max(12, D), Math.max(8, H), m, cx, cy, cz);
      cylPart(g, Math.min(7, W * 0.2), 4, darker("#243746"), cx, cy, b[5] + 1, "z");
      edges(g.children[0], 0x34495e);
    } else if (cat === "electronics" || cat === "power") {
      boxPart(g, Math.max(18, W), Math.max(16, D), Math.max(8, H), m, cx, cy, cz);
      boxPart(g, Math.min(10, W * 0.25), 4, 4, mat("adapter"), b[3] - 3, cy, cz + 2);
      edges(g.children[0], 0x34495e);
    } else {
      boxPart(g, Math.max(8, W), Math.max(8, D), Math.max(6, H), m, cx, cy, cz);
    }
    g.traverse(function (o) {
      if (o.isMesh) { o.userData.instanceId = inst.id; o.castShadow = true; o.receiveShadow = true; }
    });
    return g;
  }

  function clearVisual() {
    if (state.helper) {
      state.scene.remove(state.helper);
      state.helper.geometry.dispose();
      state.helper.material.dispose();
      state.helper = null;
    }
    if (!state.root) return;
    state.scene.remove(state.root);
    state.root.traverse(function (o) {
      if (o.geometry) o.geometry.dispose();
      // 材质是跨实例共享的（mat(cat)），不能在这里 dispose；
      // 查看器只做单次装配，少量材质泄漏比复用已释放材质安全。
    });
    state.root = null;
    state.groups = {};
    state.jointVisuals = [];
    state.gripperVisuals = [];
    state.wheelVisuals = [];
  }

  function buildVisual() {
    clearVisual();
    var r = state.report;
    if (!r || !r.instances.length) return;
    state.root = new THREE.Group();
    var map = {};
    r.instances.forEach(function (i) { map[i.id] = i; });
    var children = {};
    r.instances.forEach(function (i) {
      if (i.offboard) return;
      if (i.parent && map[i.parent]) (children[i.parent] = children[i.parent] || []).push(i);
    });
    function build(inst, parentWorld) {
      var node = new THREE.Group();
      var local = parentWorld ? A.multiply(A.invertRigid(parentWorld), inst.world) : inst.world;
      node.matrixAutoUpdate = false;
      node.matrix.fromArray(local);
      var geo;
      try { geo = geometryFor(inst); }
      catch (e) {
        geo = new THREE.Group();
        boxPart(geo, 20, 20, 20, mat("frame"), 0, 0, 0);
      }
      node.add(geo);
      state.groups[inst.id] = node;
      geo.userData.basePos = geo.position.clone();
      if (geo.userData.toolKind === "gripper") state.gripperVisuals.push({ inst: inst, geo: geo });
      if (geo.userData.wheel) state.wheelVisuals.push({ inst: inst, wheel: geo.userData.wheel, hub: geo.userData.hub });
      if (inst.joint && inst.joint.mode === "position") {
        var center = inst.joint.center || [0, 0, 30];
        var pivot = new THREE.Group();
        pivot.position.set(center[0], center[1], center[2]);
        node.add(pivot);
        state.jointVisuals.push({ inst: inst, pivot: pivot });
        var pivotWorld = A.multiply(inst.world, A.translation(center[0], center[1], center[2]));
        (children[inst.id] || []).forEach(function (ch) { pivot.add(build(ch, pivotWorld)); });
      } else {
        (children[inst.id] || []).forEach(function (ch) { node.add(build(ch, inst.world)); });
      }
      return node;
    }
    r.instances.forEach(function (i) {
      if (i.offboard) return;
      if (!i.parent || !map[i.parent]) state.root.add(build(i, null));
    });
    state.scene.add(state.root);
    state.root.updateMatrixWorld(true);
    state.angles = {};
    applyMotion();
    renderJoints();
    fit();
  }

  function fmtVal(v, j) {
    if (j.unit === "ratio") return (v * 100).toFixed(0) + "%";
    return Number(v).toFixed(j.unit === "deg" ? 1 : 0);
  }
  function applyMotion() {
    var t = state.playing ? ((performance.now() - state.playStart) / 1000) * state.speed : 0;
    state.jointVisuals.forEach(function (j) {
      var ang = state.angles[j.inst.id];
      if (ang == null) {
        ang = j.inst.joint.unit === "ratio" ? 1 : 0;
        state.angles[j.inst.id] = ang;
      }
      if (j.inst.joint.unit === "deg") j.pivot.rotation.z = ang * Math.PI / 180;
    });
    state.gripperVisuals.forEach(function (g) {
      var v = state.angles[g.inst.id];
      if (v == null) v = 1;
      var jaw = g.geo.userData.jaws;
      if (!jaw) return;
      var gap = jaw.closed + (jaw.open - jaw.closed) * Math.max(0, Math.min(1, v));
      jaw.a.position.y = gap / 2 + 3;
      jaw.b.position.y = -(gap / 2 + 3);
    });
    state.wheelVisuals.forEach(function (w) {
      if (!state.playing) return;
      var spin = t * 8;
      w.wheel.rotation.y = spin;
      if (w.hub) w.hub.rotation.y = spin;
    });
  }
  function renderJoints() {
    var host = $("view-joints");
    if (!host) return;
    var joints = state.report.instances.filter(function (i) { return i.joint && i.joint.mode === "position"; });
    if (!joints.length) {
      host.innerHTML = '<p class="muted">当前装配没有可动位置关节。</p>';
      return;
    }
    host.innerHTML = joints.map(function (i) {
      var j = i.joint, val = state.angles[i.id];
      if (val == null) val = j.unit === "ratio" ? 1 : 0;
      var unit = j.unit === "ratio" ? "" : (j.unit === "deg" ? "°" : j.unit);
      return '<div class="jrow"><label for="vj-' + esc(i.id) + '" title="' + esc(i.id) + '">' + esc(j.name) + '</label>' +
        '<input id="vj-' + esc(i.id) + '" data-inst="' + esc(i.id) + '" type="range" min="' + j.min + '" max="' + j.max +
        '" step="' + (j.unit === "ratio" ? 0.01 : 1) + '" value="' + val + '">' +
        '<output for="vj-' + esc(i.id) + '" data-out="' + esc(i.id) + '">' + fmtVal(val, j) + unit + '</output></div>';
    }).join("");
    Array.prototype.forEach.call(host.querySelectorAll("input[type=range]"), function (el) {
      el.addEventListener("input", function () {
        state.angles[el.getAttribute("data-inst")] = parseFloat(el.value);
        if (state.playing) stopPlay();
        applyMotion();
        var inst = null;
        state.jointVisuals.forEach(function (j) { if (j.inst.id === el.getAttribute("data-inst")) inst = j.inst; });
        var out = host.querySelector('[data-out="' + el.getAttribute("data-inst") + '"]');
        if (out && inst) out.textContent = fmtVal(parseFloat(el.value), inst.joint) + (inst.joint.unit === "deg" ? "°" : "");
      });
    });
  }
  function playText(running) {
    var en = window.MODKIT_I18N && window.MODKIT_I18N.lang === "en";
    if (running) return en ? "■ Stop" : "■ 停止";
    return en ? "▶ Play" : "▶ 播放";
  }
  function startPlay() {
    if (!state.report || !state.report.ok) { status("先修正校验错误再播放", "err"); return; }
    if (state.reduceMotion) {
      status("系统已开启“减少动态”；请用滑杆逐帧查看", "err"); return;
    }
    if (!state.jointVisuals.length && !state.wheelVisuals.length) { status("没有可动关节或驱动轮", "err"); return; }
    state.playing = true;
    state.playStart = performance.now();
    var b = $("view-play");
    if (b) { b.textContent = playText(true); b.setAttribute("aria-pressed", "true"); }
    status("运动演示中 · 仅运动学示意", "ok");
  }
  function stopPlay() {
    state.playing = false;
    var b = $("view-play");
    if (b) { b.textContent = playText(false); b.setAttribute("aria-pressed", "false"); }
    if (state.report) status("结构就绪 · 可旋转/点选", "ok");
  }
  function resetMotion() {
    stopPlay();
    state.angles = {};
    state.wheelVisuals.forEach(function (w) { w.wheel.rotation.y = 0; if (w.hub) w.hub.rotation.y = 0; });
    renderJoints();
    applyMotion();
    status("关节已复位", "ok");
  }
  function toggleExplode() {
    state.exploded = !state.exploded;
    var center = new THREE.Vector3();
    if (state.root) {
      var box = new THREE.Box3().setFromObject(state.root);
      if (!box.isEmpty()) box.getCenter(center);
    }
    state.root.updateMatrixWorld(true);
    Object.keys(state.groups).forEach(function (id) {
      var node = state.groups[id];
      var geo = node && node.children[0];
      if (!geo) return;
      var base = geo.userData.basePos || new THREE.Vector3();
      if (!state.exploded) { geo.position.copy(base); return; }
      var inst = null;
      state.report.instances.forEach(function (i) { if (i.id === id) inst = i; });
      if (!inst || !inst.parent) return; // 根件留在原位
      var origin = new THREE.Vector3().setFromMatrixPosition(node.matrixWorld);
      var dir = origin.clone().sub(center);
      if (dir.lengthSq() < 1) dir.set(0, 0, 1);
      dir.z += 0.35;
      dir.normalize().multiplyScalar(20);
      var localOrigin = node.worldToLocal(origin.clone());
      var localTarget = node.worldToLocal(origin.clone().add(dir));
      geo.position.copy(base).add(localTarget.sub(localOrigin));
    });
    var b = $("view-explode");
    if (b) { b.textContent = state.exploded ? "收起爆炸" : "爆炸视图"; b.setAttribute("aria-pressed", state.exploded ? "true" : "false"); }
    fit();
  }

  function fit() {
    if (!state.ready || !state.root) return;
    var b = new THREE.Box3().setFromObject(state.root);
    if (b.isEmpty()) return;
    var c = b.getCenter(new THREE.Vector3());
    var s = b.getSize(new THREE.Vector3());
    var r = Math.max(80, Math.max(s.x, s.y, s.z));
    state.controls.target.copy(c);
    state.camera.position.set(c.x + r * 1.65, c.y - r * 1.85, c.z + r * 1.25);
    state.camera.near = Math.max(0.5, r / 100);
    state.camera.far = r * 60;
    state.camera.updateProjectionMatrix();
    state.controls.update();
    var z = b.min.z - Math.max(1.5, r * 0.01);
    state.ground.position.z = z;
    state.grid.position.z = z + 0.1;
    var gs = Math.max(800, r * 4);
    state.ground.geometry.dispose();
    state.ground.geometry = new THREE.PlaneGeometry(gs, gs);
    state.grid.scale.setScalar(Math.max(0.5, r / 120));
  }

  function select(id) {
    if (state.helper) {
      state.scene.remove(state.helper);
      state.helper.geometry.dispose();
      state.helper.material.dispose();
      state.helper = null;
    }
    var g = state.groups[id];
    if (!g) return;
    state.helper = new THREE.BoxHelper(g, 0x2f80ed);
    state.scene.add(state.helper);
    var inst = null;
    state.report.instances.forEach(function (i) { if (i.id === id) inst = i; });
    var hud = $("view-hud");
    if (hud && inst) {
      hud.textContent = id + " · " + (inst.component && inst.component.name || inst.type);
    }
  }

  // ---------------------------------------------------------------- 交互/信息
  function copyLink() {
    var url = location.href;
    function done() { status("链接已复制", "ok"); }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(done).catch(function () { window.prompt("复制链接", url); });
    } else {
      window.prompt("复制链接", url);
    }
  }

  function updateInfo() {
    var a = state.assembly, r = state.report;
    document.title = (a.name || "未命名装配") + " · modkit 结构查看器";
    $("view-title").textContent = a.name || "未命名装配";
    $("view-sub").textContent = a.description || "自由设计的只读结构预览。";
    var budget = a.budget_cny != null ? Number(a.budget_cny) : 1000;
    var joints = r.instances.filter(function (i) { return i.joint && i.joint.mode === "position"; }).length;
    $("view-meta").innerHTML =
      '<div><b>' + r.instances.length + '</b><span>组件</span></div>' +
      '<div><b>' + Math.round(r.totalMass) + 'g</b><span>估算质量</span></div>' +
      '<div><b>¥' + Math.round(r.totalCost) + '</b><span>BOM</span></div>' +
      '<div><b>' + joints + '</b><span>位置关节</span></div>' +
      '<div><b>¥' + Math.round(budget) + '</b><span>预算</span></div>' +
      '<div><b>' + (r.totalCost > budget ? "超 " + Math.round(r.totalCost - budget) : "余 " + Math.round(budget - r.totalCost)) +
      '</b><span>预算差</span></div>';
    var errors = r.issues.filter(function (x) { return x.level === "error"; });
    var warns = r.issues.filter(function (x) { return x.level === "warn"; });
    var host = $("view-issues");
    if (!errors.length && !warns.length) {
      host.innerHTML = '<p class="ok">没有发现校验问题；AABB/静载仍是保守估算。</p>';
    } else {
      host.innerHTML = '<p class="summary">' + errors.length + ' 个错误 · ' + warns.length + ' 个警告</p>' +
        r.issues.slice(0, 6).map(function (x) {
          return '<div class="issue ' + esc(x.level) + '"><b>' + esc(x.code) + '</b> ' +
            esc(x.message) + (x.instance ? ' <code>' + esc(x.instance) + '</code>' : '') + '</div>';
        }).join("");
    }
    $("view-source").textContent = state.source;
    $("view-edit").href = "design.html#d=" + b64encode(JSON.stringify(a));
    $("view-edit").hidden = false;
    var empty = $("view-empty");
    if (empty) empty.hidden = true;
    $("view-fallback").classList.remove("show");
  }

  function load(input) {
    if (!input || input.error) { fail(input && input.error || "没有设计数据"); return; }
    var data = clone(input.assembly);
    var report;
    try { report = A.validate(data); }
    catch (e) { fail("装配求解失败：" + e.message); return; }
    if (!report.instances.length) {
      fail((report.issues || []).map(function (x) { return x.message; }).join("；") || "装配没有可显示的实例");
      return;
    }
    state.assembly = data;
    state.report = report;
    state.source = input.source || "";
    buildVisual();
    updateInfo();
    status(report.ok ? "结构就绪 · 可旋转/点选" : "有校验错误 · 仍显示已求解几何", report.ok ? "ok" : "warn");
  }

  function onClick(e) {
    if (!state.ready || !state.root) return;
    var rect = state.renderer.domElement.getBoundingClientRect();
    state.pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    state.pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    state.raycaster.setFromCamera(state.pointer, state.camera);
    var hits = state.raycaster.intersectObjects(state.root.children, true);
    for (var i = 0; i < hits.length; i++) {
      var o = hits[i].object;
      while (o && !o.userData.instanceId) o = o.parent;
      if (o && o.userData.instanceId) { select(o.userData.instanceId); return; }
    }
  }

  function loop() {
    if (!state.ready) return;
    requestAnimationFrame(loop);
    if (state.playing && state.report && state.report.ok) {
      var t = (performance.now() - state.playStart) / 1000 * state.speed;
      state.jointVisuals.forEach(function (j, k) {
        var jj = j.inst.joint;
        var u = 0.5 + 0.5 * Math.sin(t * 1.1 + k * 1.15);
        var v = jj.unit === "ratio" ? u : jj.min + (jj.max - jj.min) * u;
        state.angles[j.inst.id] = v;
        var slider = document.getElementById("vj-" + j.inst.id);
        if (slider) slider.value = v;
        var out = document.querySelector('#view-joints [data-out="' + j.inst.id + '"]');
        if (out) out.textContent = fmtVal(v, jj) + (jj.unit === "deg" ? "°" : "");
      });
      applyMotion();
    }
    state.controls.update();
    state.renderer.render(state.scene, state.camera);
    if (state.helper) state.helper.update();
  }

  function boot() {
    if (!A) { fail("缺少 assembly-core.js"); return; }
    var input = readInput();
    if (!initThree()) { if ($("view-empty")) $("view-empty").hidden = true; return; }
    resize();
    window.addEventListener("resize", resize);
    if (window.ResizeObserver) new ResizeObserver(resize).observe($("viewport"));
    $("view").addEventListener("click", onClick);
    $("view-fit").addEventListener("click", function () { fit(); status("视角已适配", "ok"); });
    $("view-copy").addEventListener("click", copyLink);
    if ($("view-play")) $("view-play").addEventListener("click", function () { state.playing ? stopPlay() : startPlay(); });
    window.addEventListener("modkit:lang", function () {
      if ($("view-play") && !state.playing) $("view-play").textContent = playText(false);
    });
    if ($("view-reset")) $("view-reset").addEventListener("click", resetMotion);
    if ($("view-explode")) $("view-explode").addEventListener("click", toggleExplode);
    if ($("view-reload")) {
      $("view-reload").addEventListener("click", function () { location.href = "view.html" + location.hash; });
    }
    window.addEventListener("hashchange", function () {
      load(readInput());
    });
    load(input);
    if (!state.started) { state.started = true; loop(); }
  }

  window.MODKIT_VIEW = { state: state, fit: fit, load: load, select: select };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
