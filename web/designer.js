/* modkit Studio：浏览器端装配设计 + 运动学预览 + 导出。
 *
 * 不依赖后端；组件元数据、预设和 STEP 由 tools/export_web_design.py 生成。
 * 浏览器只做"设计/校验/预览/网格导出"，参数化 STEP 仍由 CAD 工具链重建。
 */
(function () {
  "use strict";
  var C = window.MODKIT_COMPONENTS || {};
  var P = window.MODKIT_ASSEMBLIES || {};
  var A = window.MODKIT_ASSEMBLY;
  if (!A) { document.body.insertAdjacentHTML("beforeend", '<p style="padding:20px">缺少 assembly-core.js</p>'); return; }

  var $ = function (id) { return document.getElementById(id); };
  var CAT_LABEL = {
    frame: "结构", joint: "关节", link: "连杆", adapter: "转接",
    drive: "驱动", tool: "工具", sensor: "感知", electronics: "电控", power: "电源"
  };
  var CAT_COLOR = {
    frame: "#7aa6c2", joint: "#e0a458", link: "#8fb573", adapter: "#b9a3c9",
    drive: "#6b8e9e", tool: "#d97b7b", sensor: "#c9b458", electronics: "#7f9f7f", power: "#a88b6a"
  };
  var state = {
    assembly: null, report: null, selected: null, replaceMode: false,
    angles: {}, playing: false, playStart: 0, speed: 1, dirty: false, optimizer: null,
    plan: null, history: [], historyIndex: -1, historyLimit: 40,
    reduceMotion: !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches)
  };
  var view = {
    scene: null, camera: null, renderer: null, controls: null, root: null,
    raycaster: null, pointer: null, jointVisuals: [], gripperVisuals: [], wheelVisuals: [],
    instanceGroups: {}, selectedHelper: null, issueHelpers: [],
    materials: {}, fitPending: true, ready: false, clipboard: null,
    projectId: null
  };
  var toastTimer = 0;
  var STUDIO_VERSION = "1.32.0";

  function toast(msg, kind) {
    var el = $("toast");
    el.textContent = msg;
    el.className = "toast show " + (kind || "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.className = "toast " + (kind || ""); }, 2600);
  }
  function clone(x) { return JSON.parse(JSON.stringify(x)); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function comp(id) { return C[id] || null; }
  function rawById(id) {
    if (!state.assembly) return null;
    for (var i = 0; i < state.assembly.components.length; i++) if (state.assembly.components[i].id === id) return state.assembly.components[i];
    return null;
  }
  function solvedById(id) {
    if (!state.report) return null;
    for (var i = 0; i < state.report.instances.length; i++) if (state.report.instances[i].id === id) return state.report.instances[i];
    return null;
  }
  function childIds(id) {
    var out = [];
    state.assembly.components.forEach(function (c) { if (c.parent === id) out.push(c.id); });
    return out;
  }
  function subtreeIds(id, seen) {
    seen = seen || {};
    if (seen[id]) return [];
    seen[id] = true;
    var out = [id];
    childIds(id).forEach(function (k) { out = out.concat(subtreeIds(k, seen)); });
    return out;
  }
  function uniqueId(type) {
    var base = String(type).split(".").pop().replace(/[^a-zA-Z0-9_]/g, "_") || "part";
    if (!rawById(base)) return base;
    var n = 2;
    while (rawById(base + "_" + n)) n++;
    return base + "_" + n;
  }

  // ---------------------------------------------------------------- 3D
  function initThree() {
    if (typeof THREE === "undefined") { $("fallback").classList.add("show"); return false; }
    try {
      var el = $("viewport");
      var scene = new THREE.Scene();
      scene.background = new THREE.Color(0xeaeff6);
      scene.fog = new THREE.Fog(0xeaeff6, 1800, 4200);
      var camera = new THREE.PerspectiveCamera(38, 1, 1, 12000);
      camera.up.set(0, 0, 1);
      var renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.setSize(el.clientWidth || 800, el.clientHeight || 500);
      renderer.shadowMap.enabled = true;
      renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      el.appendChild(renderer.domElement);
      var controls = new THREE.OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.dampingFactor = 0.08;
      controls.screenSpacePanning = true;
      controls.target.set(0, 0, 80);

      scene.add(new THREE.HemisphereLight(0xffffff, 0x8794a6, 0.85));
      var key = new THREE.DirectionalLight(0xffffff, 1.0);
      key.position.set(650, -850, 1100);
      key.castShadow = true;
      key.shadow.mapSize.set(2048, 2048);
      key.shadow.camera.left = -900; key.shadow.camera.right = 900;
      key.shadow.camera.top = 900; key.shadow.camera.bottom = -900;
      key.shadow.camera.near = 100; key.shadow.camera.far = 3000;
      scene.add(key);
      var fill = new THREE.DirectionalLight(0xffffff, 0.45);
      fill.position.set(-700, 500, 600);
      scene.add(fill);
      var amb = new THREE.AmbientLight(0xffffff, 0.25);
      scene.add(amb);

      var ground = new THREE.Mesh(
        new THREE.PlaneGeometry(3600, 3600),
        new THREE.MeshBasicMaterial({ color: 0xdfe6ef })
      );
      ground.position.z = -55.2;
      ground.receiveShadow = true;
      scene.add(ground);
      var grid = new THREE.GridHelper(1600, 40, 0x9fb0c3, 0xbfcbd8);
      grid.rotation.x = Math.PI / 2;
      grid.position.z = -55.0;
      scene.add(grid);
      var axes = new THREE.AxesHelper(70);
      axes.position.z = -54.9;
      scene.add(axes);

      var root = new THREE.Group();
      scene.add(root);
      view.scene = scene; view.camera = camera; view.renderer = renderer;
      view.controls = controls; view.root = root;
      view.raycaster = new THREE.Raycaster();
      view.pointer = new THREE.Vector2();
      view.ready = true;
      window.addEventListener("resize", resize);
      if (window.ResizeObserver) new ResizeObserver(resize).observe(el);
      renderer.domElement.addEventListener("pointerdown", onPointerDown);
      renderer.domElement.addEventListener("pointerup", onPointerUp);
      return true;
    } catch (e) {
      console.error(e);
      $("fallback").classList.add("show");
      return false;
    }
  }
  function resize() {
    if (!view.renderer) return;
    var el = $("viewport");
    var w = Math.max(320, el.clientWidth), h = Math.max(260, el.clientHeight);
    view.renderer.setSize(w, h);
    view.camera.aspect = w / h;
    view.camera.updateProjectionMatrix();
  }
  function mat(cat) {
    if (!view.materials[cat]) {
      view.materials[cat] = new THREE.MeshStandardMaterial({
        color: new THREE.Color(CAT_COLOR[cat] || "#9aa4b2"),
        roughness: 0.62, metalness: 0.08
      });
    }
    return view.materials[cat];
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
    if (!mesh.geometry) return;
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
      // 顶面浅色甲板 + 接缝
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
      // 侧耳
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
      // 腕部
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
      var lens = cylPart(g, Math.min(7, W * 0.2), 4, darker("#243746"), cx, cy, b[5] + 1, "z");
      edges(g.children[0], 0x34495e);
    } else if (cat === "electronics" || cat === "power") {
      boxPart(g, Math.max(18, W), Math.max(16, D), Math.max(8, H), m, cx, cy, cz);
      // 小接口/端子
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

  function clearRoot() {
    if (!view.root) return;
    var old = view.root.children.slice();
    old.forEach(function (g) {
      view.root.remove(g);
      g.traverse(function (o) {
        if (o.geometry) o.geometry.dispose();
        if (o.isLineSegments && o.material) o.material.dispose();
      });
    });
    view.jointVisuals = []; view.gripperVisuals = []; view.wheelVisuals = [];
    view.instanceGroups = {};
    clearHighlights();
  }

  function clearHighlights() {
    if (view.selectedHelper) {
      view.scene.remove(view.selectedHelper);
      view.selectedHelper.geometry.dispose();
      view.selectedHelper.material.dispose();
      view.selectedHelper = null;
    }
    view.issueHelpers.forEach(function (h) {
      view.scene.remove(h);
      h.geometry.dispose();
      h.material.dispose();
    });
    view.issueHelpers = [];
  }
  function renderHighlights() {
    if (!view.ready) return;
    clearHighlights();
    if (!state.report) return;
    var order = { error: 0, warn: 1 };
    state.report.issues.forEach(function (x) {
      if (!x.instance || order[x.level] == null) return;
      var g = view.instanceGroups[x.instance];
      if (!g) return;
      var color = x.level === "error" ? 0xd93025 : 0xf29900;
      var h = new THREE.BoxHelper(g, color);
      h.material.transparent = true;
      h.material.opacity = 0.9;
      view.scene.add(h);
      view.issueHelpers.push(h);
    });
    if (state.selected && view.instanceGroups[state.selected]) {
      view.selectedHelper = new THREE.BoxHelper(view.instanceGroups[state.selected], 0x2f80ed);
      view.selectedHelper.material.depthTest = false;
      view.selectedHelper.renderOrder = 10;
      view.scene.add(view.selectedHelper);
    }
  }
  function buildVisual() {
    if (!view.ready) return;
    clearRoot();
    if (!state.report || !state.report.instances.length) { view.renderer.render(view.scene, view.camera); return; }
    var map = {};
    state.report.instances.forEach(function (i) { map[i.id] = i; });
    var children = {};
    state.report.instances.forEach(function (i) {
      if (i.offboard) return;
      if (i.parent && map[i.parent]) (children[i.parent] = children[i.parent] || []).push(i);
    });
    function build(inst, parentWorld) {
      var local = parentWorld ? A.multiply(A.invertRigid(parentWorld), inst.world) : inst.world;
      var node = new THREE.Group();
      node.matrixAutoUpdate = false;
      node.matrix.fromArray(local);
      var geo = geometryFor(inst);
      node.add(geo);
      view.instanceGroups[inst.id] = node;
      if (inst.joint && inst.joint.mode === "position") {
        var center = inst.joint.center || [0, 0, 30];
        var pivot = new THREE.Group();
        pivot.position.set(center[0], center[1], center[2]);
        node.add(pivot);
        var pivotWorld = A.multiply(inst.world, A.translation(center[0], center[1], center[2]));
        (children[inst.id] || []).forEach(function (ch) { pivot.add(build(ch, pivotWorld)); });
        view.jointVisuals.push({ inst: inst, pivot: pivot });
      } else {
        (children[inst.id] || []).forEach(function (ch) { node.add(build(ch, inst.world)); });
      }
      if (geo.userData.toolKind === "gripper") {
        view.gripperVisuals.push({ inst: inst, geo: geo });
      }
      if (geo.userData.wheel) view.wheelVisuals.push({ inst: inst, wheel: geo.userData.wheel, hub: geo.userData.hub });
      return node;
    }
    state.report.instances.forEach(function (i) {
      if (i.offboard) return;
      if (!i.parent || !map[i.parent]) view.root.add(build(i, null));
    });
    view.root.updateMatrixWorld(true);
    applyMotion();
    if (view.fitPending) { fitCamera(); view.fitPending = false; }
    view.renderer.render(view.scene, view.camera);
  }

  function fitCamera() {
    if (!view.ready || !view.root.children.length) return;
    var b = new THREE.Box3().setFromObject(view.root);
    if (b.isEmpty()) return;
    var c = b.getCenter(new THREE.Vector3());
    var s = b.getSize(new THREE.Vector3());
    var r = Math.max(80, Math.max(s.x, s.y, s.z));
    view.controls.target.copy(c);
    view.camera.position.set(c.x + r * 1.7, c.y - r * 1.9, c.z + r * 1.35);
    view.camera.near = Math.max(0.5, r / 100);
    view.camera.far = r * 30;
    view.camera.updateProjectionMatrix();
    view.controls.update();
    view.renderer.render(view.scene, view.camera);
  }

  function applyMotion() {
    var t = state.playing ? ((performance.now() - state.playStart) / 1000) * state.speed : 0;
    view.jointVisuals.forEach(function (j, idx) {
      var id = j.inst.id;
      var ang = state.angles[id];
      if (ang == null) {
        ang = j.inst.joint.unit === "ratio" ? 1 : 0;
        state.angles[id] = ang;
      }
      var unit = j.inst.joint.unit;
      if (unit === "deg") j.pivot.rotation.z = ang * Math.PI / 180;
      else if (unit === "ratio" || unit === "mm") {
        // 夹爪：ratio 0..1 -> 闭合..张开
      }
    });
    view.gripperVisuals.forEach(function (g) {
      var v = state.angles[g.inst.id];
      if (v == null) v = 1;
      var j = g.geo.userData.jaws;
      var gap = j.closed + (j.open - j.closed) * Math.max(0, Math.min(1, v));
      j.a.position.y = gap / 2 + 3;
      j.b.position.y = -(gap / 2 + 3);
    });
    view.wheelVisuals.forEach(function (w) {
      if (!state.playing) return;
      var spin = t * 8;
      w.wheel.rotation.y = spin;
      if (w.hub) w.hub.rotation.y = spin;
    });
    updateHud();
  }

  function updateHud() {
    if (!state.report) { $("hud").textContent = "—"; return; }
    var r = state.report;
    var budget = state.assembly && state.assembly.budget_cny != null ? state.assembly.budget_cny : 1000;
    $("hud").textContent = r.instances.length + " 组件 · " + Math.round(r.totalMass) + "g · ¥" + Math.round(r.totalCost) +
      (r.totalCost > budget ? " · 超预算 ¥" + Math.round(r.totalCost - budget) : " · 余 ¥" + Math.round(budget - r.totalCost)) +
      (r.stability && r.stability.margin != null ? " · 支撑余量 " + r.stability.margin.toFixed(1) + "mm" : "");
  }

  function onPointerDown(e) { view.pointer.set(e.clientX, e.clientY); }
  function onPointerUp(e) {
    if (!view.ready || !state.report) return;
    if (Math.hypot(e.clientX - view.pointer.x, e.clientY - view.pointer.y) > 5) return;
    var rect = view.renderer.domElement.getBoundingClientRect();
    view.pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    view.pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    view.raycaster.setFromCamera(view.pointer, view.camera);
    var hits = view.raycaster.intersectObjects(view.root.children, true);
    for (var i = 0; i < hits.length; i++) {
      var o = hits[i].object;
      while (o && !o.userData.instanceId) o = o.parent;
      if (o && o.userData.instanceId) { select(o.userData.instanceId); return; }
    }
  }

  // ---------------------------------------------------------------- 装配操作
  function loadPreset(name) {
    var asm = P[name];
    if (!asm) { toast("没有预设 " + name, "err"); return; }
    state.projectId = null;
    state.assembly = migrateAssembly(clone(asm));
    if (!state.assembly.name) state.assembly.name = name;
    if (state.assembly.budget_cny == null) state.assembly.budget_cny = 1000;
    pushHistory("载入预设 " + name);
    state.selected = state.assembly.components.length ? state.assembly.components[0].id : null;
    state.angles = {}; state.playing = false; state.fitPending = true;
    $("preset").value = P[name] ? name : "m1";
    revalidate();
    toast("已加载预设：" + (state.assembly.name || name), "ok");
  }
  function b64encode(text) {
    return btoa(unescape(encodeURIComponent(text))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }
  function b64decode(text) {
    var s = String(text).replace(/-/g, "+").replace(/_/g, "/");
    while (s.length % 4) s += "=";
    return decodeURIComponent(escape(atob(s)));
  }
  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
    return new Promise(function (resolve, reject) {
      try {
        var ta = document.createElement("textarea");
        ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
        document.body.appendChild(ta); ta.select();
        var ok = document.execCommand("copy");
        ta.remove();
        ok ? resolve() : reject(new Error("浏览器不允许复制"));
      } catch (e) { reject(e); }
    });
  }
  function shareDesign() {
    if (!state.assembly) return;
    var url = location.origin + location.pathname + "#d=" + b64encode(JSON.stringify(state.assembly));
    if (url.length > 60000) { toast("装配太大，链接超过 60000 字符；请导出 JSON", "err"); return; }
    copyText(url).then(function () {
      toast("分享链接已复制；打开时会自动载入这份装配", "ok");
    }).catch(function (e) {
      window.prompt("复制分享链接：", url);
      toast("无法自动复制，已弹出链接：" + (e.message || e), "");
    });
  }
  function viewerURL() {
    if (!state.assembly) return "";
    var u = new URL("view.html", location.href);
    u.hash = "#d=" + b64encode(JSON.stringify(state.assembly));
    return u.href;
  }
  function openViewer() {
    var url = viewerURL();
    if (!url) return;
    if (url.length > 60000) { toast("装配太大，查看器链接超过 60000 字符；请导出 JSON", "err"); return; }
    var w = window.open(url, "_blank");
    if (!w) { location.href = url; return; }
    try { w.opener = null; } catch (e) { /* 跨域/隐私模式 */ }
    toast("已在新标签页打开结构查看器", "ok");
  }
  function loadShared() {
    var m = /^#d=(.+)$/.exec(location.hash || "");
    if (!m) return false;
    try {
      var data = migrateAssembly(JSON.parse(b64decode(m[1])));
      var shape = A.check(data);
      if (!shape.ok) throw new Error(shape.errors.slice(0, 3).join("；"));
      state.assembly = data;
      state.projectId = null;
      state.selected = data.components.length ? data.components[0].id : null;
      state.angles = {}; state.playing = false; state.fitPending = true;
      $("preset").value = "";
      pushHistory("打开分享链接");
      // 分享链接是快照：不要覆盖本地草稿，也不要把 #d= 留在地址栏
      // （否则刷新会把后续编辑重置回快照）。
      var prevSuppress = state.suppressSave;
      state.suppressSave = true;
      try { revalidate(); } finally { state.suppressSave = prevSuppress; }
      try { history.replaceState(null, "", location.pathname + location.search); } catch (e) { /* file:// */ }
      toast("已从分享链接载入：" + (data.name || "未命名") + "；地址栏已清理", "ok");
      return true;
    } catch (e) {
      toast("分享链接无效：" + e.message, "err");
      return false;
    }
  }
  function initDragDrop() {
    var depth = 0;
    function hasFiles(e) {
      return !!(e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types || [], "Files") >= 0);
    }
    function reset() { depth = 0; document.body.classList.remove("drop-active"); }
    window.addEventListener("dragenter", function (e) {
      if (!hasFiles(e)) return;
      e.preventDefault(); depth++; document.body.classList.add("drop-active");
    });
    window.addEventListener("dragover", function (e) { if (hasFiles(e)) e.preventDefault(); });
    window.addEventListener("dragleave", function (e) {
      if (!hasFiles(e)) return;
      depth = Math.max(0, depth - 1);
      if (!depth) reset();
    });
    window.addEventListener("dragend", reset);
    window.addEventListener("blur", reset);
    window.addEventListener("drop", function (e) {
      if (!hasFiles(e)) return;
      e.preventDefault(); reset();
      var files = e.dataTransfer.files;
      if (!files || !files.length) return;
      var f = files[0];
      if (!/\.json$/i.test(f.name)) { toast("只支持导入 .json 装配文件", "err"); return; }
      importDesign(f);
    });
  }
  function importDesign(file) {
    if (!file) return;
    var rd = new FileReader();
    rd.onload = function () {
      try {
        var data = migrateAssembly(JSON.parse(String(rd.result)));
        var shape = A.check(data);
        if (!shape.ok) throw new Error(shape.errors.slice(0, 3).join("；"));
        state.assembly = data;
        state.projectId = null;
        state.selected = data.components[0].id;
        state.angles = {}; state.playing = false; state.fitPending = true;
        $("preset").value = "";
        pushHistory("导入装配");
        revalidate();
        toast("已导入装配：" + (data.name || "未命名"), "ok");
      } catch (e) { toast("导入失败：" + e.message, "err"); }
    };
    rd.readAsText(file);
  }
  function newDesign() {
    state.projectId = null;
    state.assembly = {
      schema_version: SCHEMA_VERSION,
      name: "未命名装配", budget_cny: 1000, description: "从底盘开始，自由添加组件。",
      components: [{ id: "chassis", type: "frame.chassis_160", parent: null, child_port: "top", at: [0, 0], spin: 0 }]
    };
    state.selected = "chassis"; state.angles = {}; state.playing = false; state.fitPending = true;
    $("preset").value = "";
    pushHistory("新建空白装配");
    revalidate(); toast("已新建空白装配：chassis", "ok");
  }

  function portCandidates(parent, childComp) {
    var out = [];
    var used = {};
    state.assembly.components.forEach(function (c) {
      if (c.parent === parent.id && c.port) used[c.port] = (used[c.port] || 0) + 1;
    });
    var prank = { out: 0, top: 1, tool: 2, drive_left: 3, drive_right: 4, lid: 5, mount: 9 };
    var crank = { mount: 0, disc: 1, tool: 2 };
    (parent.component.ports || []).forEach(function (pp) {
      if (pp.kind.indexOf("elec.") === 0) return;
      if ((used[pp.name] || 0) >= (pp.max_uses || 1)) return;
      (childComp.ports || []).forEach(function (cp) {
        if (cp.kind.indexOf("elec.") === 0) return;
        if (pp.kind !== cp.kind) return;
        if (!A.compatible(pp, cp)) return;
        out.push({ pp: pp, cp: cp,
          rank: (prank[pp.name] == null ? 6 : prank[pp.name]) * 10 + (crank[cp.name] == null ? 5 : crank[cp.name]) });
      });
    });
    out.sort(function (a, b) { return a.rank - b.rank; });
    return out;
  }
  function occupied(parentId, portName, dx, dy) {
    return state.assembly.components.some(function (c) {
      return c.parent === parentId && c.port === portName && Math.abs((c.at || [0, 0])[0] - dx) < 1e-6 && Math.abs((c.at || [0, 0])[1] - dy) < 1e-6;
    });
  }
  function freeGrid(pp) {
    var gx = (pp.grid && pp.grid[0]) || 20, gy = (pp.grid && pp.grid[1]) || 20;
    var xs = [], ys = [];
    for (var x = -Math.floor(gx / 2 / 20) * 20; x <= Math.floor(gx / 2 / 20) * 20; x += 20) xs.push(x);
    for (var y = -Math.floor(gy / 2 / 20) * 20; y <= Math.floor(gy / 2 / 20) * 20; y += 20) ys.push(y);
    xs.sort(function (a, b) { return Math.abs(a) - Math.abs(b); });
    ys.sort(function (a, b) { return Math.abs(a) - Math.abs(b); });
    for (var i = 0; i < xs.length; i++) for (var j = 0; j < ys.length; j++) {
      if (!occupied(state.selected, pp.name, xs[i], ys[j])) return [xs[i], ys[j]];
    }
    return [0, 0];
  }
  function copySelected() {
    var raw = rawById(state.selected);
    if (!raw) { toast("先选中要复制的组件", "err"); return; }
    var ids = subtreeIds(raw.id);
    var comps = state.assembly.components.filter(function (c) { return ids.indexOf(c.id) >= 0; }).map(clone);
    state.clipboard = { name: state.assembly.name || "未命名", rootId: raw.id, components: comps };
    var payload = JSON.stringify({ name: "modkit-clipboard", components: comps, root: raw.id });
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(payload).catch(function () {});
    toast("已复制 " + ids.length + " 个组件；选中父件后可粘贴", "ok");
  }
  function cloneFromClipboard(parentRaw, pair, at) {
    var cb = state.clipboard;
    var map = {};
    cb.components.forEach(function (c) { map[c.id] = uniqueId(c.type); });
    return cb.components.map(function (c) {
      var n = clone(c);
      n.id = map[c.id];
      if (c.id === cb.rootId) {
        n.parent = parentRaw.id;
        n.port = pair.pp.name;
        n.child_port = pair.cp.name;
        n.at = at.slice();
        n.spin = 0;
      } else if (c.parent && map[c.parent]) {
        n.parent = map[c.parent];
      }
      return n;
    });
  }
  function pasteClipboard() {
    var cb = state.clipboard;
    if (!cb || !cb.components || !cb.components.length) { toast("剪贴板为空：先选中组件按 Ctrl+C", "err"); return; }
    var parentRaw = rawById(state.selected);
    if (!parentRaw) { toast("先选中要挂接的父件", "err"); return; }
    var rootRaw = null, rootComp = null;
    cb.components.forEach(function (c) { if (c.id === cb.rootId) { rootRaw = c; rootComp = comp(c.type); } });
    if (!rootRaw || !rootComp) { toast("剪贴板数据损坏", "err"); return; }
    var parentSolved = solvedById(parentRaw.id);
    if (!parentSolved) { toast("父件尚未求解，先修正上游错误", "err"); return; }
    var pairs = portCandidates(parentSolved, rootComp);
    if (!pairs.length) { toast("与 " + parentRaw.id + " 没有可用机械端口", "err"); return; }
    var pair = null;
    for (var i = 0; i < pairs.length; i++) if (pairs[i].cp.name === rootRaw.child_port) { pair = pairs[i]; break; }
    if (!pair) pair = pairs[0];
    var at = pair.pp.kind === "mech.grid" ? freeGrid(pair.pp) : [0, 0];
    var added = cloneFromClipboard(parentRaw, pair, at);
    state.assembly.components = state.assembly.components.concat(added);
    var newRoot = added.filter(function (c) { return c.parent === parentRaw.id && c.port === pair.pp.name && c.type === rootRaw.type; })[0];
    state.selected = newRoot ? newRoot.id : added[0].id;
    state.fitPending = true;
    pushHistory("粘贴组件");
    revalidate();
    toast("已粘贴 " + added.length + " 个组件到 " + parentRaw.id, "ok");
  }
  function duplicateSelected() {
    var raw = rawById(state.selected);
    if (!raw) { toast("先选中要复制的组件", "err"); return; }
    if (!raw.parent) { toast("根组件不能原地复制；请选中子件或先复制再粘贴", "err"); return; }
    var parentRaw = rawById(raw.parent);
    var parentSolved = parentRaw ? solvedById(parentRaw.id) : null;
    if (!parentSolved) { toast("父件尚未求解", "err"); return; }
    var c = comp(raw.type);
    var pairs = portCandidates(parentSolved, c);
    if (!pairs.length) { toast("父件没有多余机械端口可挂复制件", "err"); return; }
    var pair = pairs[0];
    var at = pair.pp.kind === "mech.grid" ? freeGrid(pair.pp) : [0, 0];
    var ids = subtreeIds(raw.id);
    var saved = state.clipboard;
    state.clipboard = { name: state.assembly.name || "未命名", rootId: raw.id,
      components: state.assembly.components.filter(function (x) { return ids.indexOf(x.id) >= 0; }).map(clone) };
    var added = cloneFromClipboard(parentRaw, pair, at);
    state.clipboard = saved;
    state.assembly.components = state.assembly.components.concat(added);
    var dupRoot = added.filter(function (c) { return c.parent === parentRaw.id && c.port === pair.pp.name && c.type === raw.type; })[0];
    state.selected = dupRoot ? dupRoot.id : added[0].id;
    state.fitPending = true;
    pushHistory("复制一份");
    revalidate();
    toast("已复制一份到 " + parentRaw.id + "." + pair.pp.name, "ok");
  }

  function addComponent(type) {
    var c = comp(type);
    if (!c) { toast("未知组件 " + type, "err"); return; }
    if (!state.assembly || !state.assembly.components.length) {
      state.assembly = { name: "未命名装配", components: [] };
      var root = { id: uniqueId(type), type: type, parent: null, child_port: "mount", at: [0, 0], spin: 0 };
      state.assembly.components.push(root);
      state.selected = root.id; state.fitPending = true;
      pushHistory("添加 " + type);
      revalidate(); toast("已创建根组件 " + root.id, "ok"); return;
    }
    var parentRaw = rawById(state.selected);
    if (!parentRaw) { toast("先在装配树里选中父件", "err"); return; }
    var parentSolved = solvedById(parentRaw.id);
    if (!parentSolved) { toast("父件尚未求解，先修正上游错误", "err"); return; }
    var pairs = portCandidates(parentSolved, c);
    if (!pairs.length) { toast("与 " + parentRaw.id + " 没有可用的机械端口", "err"); return; }
    var pair = pairs[0];
    var at = pair.pp.kind === "mech.grid" ? freeGrid(pair.pp) : [0, 0];
    var inst = { id: uniqueId(type), type: type, parent: parentRaw.id, port: pair.pp.name,
      child_port: pair.cp.name, at: at, spin: 0 };
    state.assembly.components.push(inst);
    state.selected = inst.id;
    state.fitPending = true;
    pushHistory("添加 " + type);
    revalidate();
    toast("已添加 " + inst.id + " → " + parentRaw.id + "." + pair.pp.name, "ok");
  }
  function replaceSelected(type) {
    var raw = rawById(state.selected);
    var c = comp(type);
    if (!raw) { toast("先选中要替换的组件", "err"); return; }
    if (!c) { toast("未知组件", "err"); return; }
    raw.type = type;
    if (!(c.ports || []).some(function (p) { return p.name === raw.child_port; })) {
      raw.child_port = (c.ports && c.ports[0] && c.ports[0].name) || "mount";
    }
    state.replaceMode = false;
    updatePaletteHint();
    state.fitPending = true;
    pushHistory("替换为 " + type);
    revalidate();
    toast("已替换为 " + type, "ok");
  }
  function deleteSelected() {
    var raw = rawById(state.selected);
    if (!raw) return;
    var ids = subtreeIds(raw.id);
    if (ids.length > 1 && !window.confirm("删除 " + raw.id + " 及其 " + (ids.length - 1) + " 个子件？")) return;
    var parent = raw.parent;
    state.assembly.components = state.assembly.components.filter(function (c) { return ids.indexOf(c.id) < 0; });
    state.selected = parent && rawById(parent) ? parent : (state.assembly.components[0] ? state.assembly.components[0].id : null);
    state.fitPending = true;
    pushHistory("删除选中组件");
    revalidate();
  }

  var LOCAL_KEY = "modkit.design.v1";
  var STORE_KEY = "modkit.workspace.v2";
  var SCHEMA_VERSION = 2;
  var MAX_PROJECTS = 20;
  var MAX_VERSIONS = 20;
  var workspace = { schema: SCHEMA_VERSION, active: null, projects: [] };

  function migrateAssembly(data) {
    if (!data || typeof data !== "object") throw new Error("不是对象");
    data.schema_version = SCHEMA_VERSION;
    if (data.budget_cny == null && data.budget != null) data.budget_cny = data.budget;
    if (data.payload_g == null && data.payload != null) data.payload_g = data.payload;
    (data.components || []).forEach(function (c) {
      if (!Array.isArray(c.at)) c.at = [0, 0];
      if (c.spin == null) c.spin = 0;
      if (c.parent === undefined) c.parent = null;
    });
    return data;
  }
  function projectById(id) {
    for (var i = 0; i < workspace.projects.length; i++) if (workspace.projects[i].id === id) return workspace.projects[i];
    return null;
  }
  function newProjectId() { return "p_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 6); }
  function projectName() {
    return (state.assembly && state.assembly.name) || "未命名装配";
  }
  function persistWorkspace() {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(workspace)); }
    catch (e) { toast("浏览器存储已满；项目没有保存", "err"); }
  }
  function trimWorkspace() {
    workspace.projects = workspace.projects.slice(0, MAX_PROJECTS);
    workspace.projects.forEach(function (p) {
      p.versions = (p.versions || []).slice(0, MAX_VERSIONS);
    });
    if (!projectById(workspace.active)) workspace.active = workspace.projects[0] ? workspace.projects[0].id : null;
  }
  function loadWorkspace() {
    try {
      var raw = JSON.parse(localStorage.getItem(STORE_KEY) || "null");
      if (raw && Array.isArray(raw.projects)) {
        workspace = { schema: SCHEMA_VERSION, active: raw.active || null, projects: raw.projects };
      }
    } catch (e) { /* 损坏则重建 */ }
    workspace.projects.forEach(function (p) {
      p.versions = p.versions || [];
      try { migrateAssembly(p.assembly); } catch (e) { /* 保留原样，加载时再报 */ }
    });
    if (!workspace.projects.length) {
      try {
        var old = JSON.parse(localStorage.getItem(LOCAL_KEY) || "null");
        var data = old && old.assembly ? old.assembly : old;
        if (data) {
          migrateAssembly(data);
          var shape = A.check(data);
          if (shape.ok) {
            var p = { id: newProjectId(), name: data.name || "恢复的本地草稿", updatedAt: new Date().toISOString(),
              assembly: data, versions: [] };
            workspace.projects.push(p); workspace.active = p.id;
          }
        }
      } catch (e) { /* 忽略旧草稿 */ }
    }
    trimWorkspace();
  }
  function ensureProject() {
    var p = state.projectId ? projectById(state.projectId) : null;
    if (p) return p;
    if (!state.assembly) return null;
    p = { id: newProjectId(), name: projectName(), updatedAt: new Date().toISOString(),
      assembly: clone(state.assembly), versions: [] };
    workspace.projects.unshift(p);
    state.projectId = p.id;
    workspace.active = p.id;
    trimWorkspace();
    return p;
  }
  function saveLocal() {
    if (!state.assembly) return;
    var p = ensureProject();
    if (!p) return;
    p.name = projectName();
    p.updatedAt = new Date().toISOString();
    p.assembly = clone(state.assembly);
    p.assembly.schema_version = SCHEMA_VERSION;
    workspace.active = p.id;
    trimWorkspace();
    persistWorkspace();
    try {
      localStorage.setItem(LOCAL_KEY, JSON.stringify({
        schema: SCHEMA_VERSION, savedAt: new Date().toISOString(), assembly: p.assembly
      }));
    } catch (e) { /* 兼容旧恢复入口；失败不影响项目存储 */ }
    renderProjects();
  }
  function loadProject(id, opts) {
    var p = projectById(id);
    if (!p) { toast("项目不存在", "err"); return false; }
    var data = clone(p.assembly);
    try { migrateAssembly(data); } catch (e) { toast("项目数据损坏：" + e.message, "err"); return false; }
    var shape = A.check(data);
    if (!shape.ok) { toast("项目无效：" + shape.errors.slice(0, 2).join("；"), "err"); return false; }
    state.assembly = data;
    state.projectId = p.id;
    workspace.active = p.id;
    state.selected = data.components[0] ? data.components[0].id : null;
    state.angles = {}; state.playing = false; state.fitPending = true;
    if ($("preset")) $("preset").value = "";
    var prev = state.suppressSave;
    if (opts && opts.silent) state.suppressSave = true;
    try {
      pushHistory("打开项目 " + p.name);
      revalidate();
    } finally { state.suppressSave = prev; }
    renderProjects();
    if (!(opts && opts.silent)) toast("已打开项目：" + p.name, "ok");
    return true;
  }
  function saveProject() {
    saveLocal();
    toast("项目已保存到浏览器", "ok");
  }
  function newProject() {
    var name = window.prompt("新项目名", projectName() + " 副本");
    if (name == null) return;
    name = name.trim() || "未命名装配";
    state.assembly.name = name;
    state.projectId = null;
    saveLocal();
    if ($("design-name")) $("design-name").value = name;
    toast("已另存为新项目：" + name, "ok");
    renderProjects();
  }
  function deleteProject() {
    var p = state.projectId ? projectById(state.projectId) : null;
    if (!p) { toast("当前没有已保存项目", "err"); return; }
    if (!window.confirm("删除项目「" + p.name + "」及其版本？")) return;
    workspace.projects = workspace.projects.filter(function (x) { return x.id !== p.id; });
    state.projectId = null;
    workspace.active = workspace.projects[0] ? workspace.projects[0].id : null;
    persistWorkspace();
    if (workspace.active) loadProject(workspace.active, { silent: true });
    else { state.assembly = null; revalidate(); }
    renderProjects();
    toast("项目已删除", "ok");
  }
  function snapshotVersion() {
    var p = ensureProject();
    if (!p) return;
    var label = window.prompt("版本说明", new Date().toLocaleString("zh-CN"));
    if (label == null) return;
    p.versions = p.versions || [];
    p.versions.unshift({ at: new Date().toISOString(), label: label.trim() || "快照", assembly: clone(state.assembly) });
    p.updatedAt = new Date().toISOString();
    trimWorkspace();
    persistWorkspace();
    renderProjects();
    toast("已保存版本：" + (label.trim() || "快照"), "ok");
  }
  function restoreVersion() {
    var p = state.projectId ? projectById(state.projectId) : null;
    var sel = $("version-select");
    if (!p || !sel || !sel.value) { toast("当前项目没有可恢复版本", "err"); return; }
    var v = p.versions[Number(sel.value)];
    if (!v) { toast("版本不存在", "err"); return; }
    var data = clone(v.assembly);
    try { migrateAssembly(data); } catch (e) { toast("版本损坏：" + e.message, "err"); return; }
    var shape = A.check(data);
    if (!shape.ok) { toast("版本无效：" + shape.errors.slice(0, 2).join("；"), "err"); return; }
    state.assembly = data;
    state.selected = data.components[0] ? data.components[0].id : null;
    state.angles = {}; state.playing = false; state.fitPending = true;
    pushHistory("恢复版本 " + v.label);
    revalidate();
    toast("已恢复版本：" + v.label, "ok");
  }
  function renderProjects() {
    if (!$("project-select")) return;
    var active = state.projectId ? projectById(state.projectId) : null;
    $("project-select").innerHTML = '<option value="">（未保存草稿）</option>' +
      workspace.projects.map(function (p) {
        var t = (p.updatedAt || "").slice(5, 16).replace("T", " ");
        return '<option value="' + esc(p.id) + '">' + esc(p.name) + (t ? " · " + esc(t) : "") + '</option>';
      }).join("");
    $("project-select").value = active ? active.id : "";
    var vs = $("version-select");
    if (vs) {
      vs.innerHTML = active && active.versions.length
        ? active.versions.map(function (v, i) {
          return '<option value="' + i + '">' + esc(v.label) + " · " + esc((v.at || "").slice(5, 16).replace("T", " ")) + '</option>';
        }).join("")
        : '<option value="">（没有版本）</option>';
    }
    if ($("project-note")) {
      $("project-note").textContent = active
        ? "自动保存到浏览器 localStorage；建议重要节点“保存版本”。"
        : "当前未保存；编辑后自动创建项目。清站点数据会丢。";
    }
  }
  function restoreLocal() {
    if (workspace.active && projectById(workspace.active)) { loadProject(workspace.active); return; }
    try {
      var raw = JSON.parse(localStorage.getItem(LOCAL_KEY) || "null");
      var data = raw && raw.assembly ? raw.assembly : raw;
      if (!data) { toast("没有可恢复的本地草稿", "err"); return; }
      migrateAssembly(data);
      var shape = A.check(data);
      if (!shape.ok) { toast("本地草稿无效：" + shape.errors.slice(0, 2).join("；"), "err"); return; }
      state.assembly = data;
      state.projectId = null;
      state.selected = data.components[0].id;
      state.angles = {}; state.playing = false; state.fitPending = true;
      $("preset").value = "";
      pushHistory("恢复本地草稿");
      revalidate(); toast("已恢复上次本地草稿", "ok");
    } catch (e) { toast("恢复失败：" + e.message, "err"); }
  }
  function pushHistory(label) {
    if (!state.assembly) return;
    var snap = clone(state.assembly);
    if (state.historyIndex >= 0) {
      var prev = state.history[state.historyIndex];
      if (prev && JSON.stringify(prev.assembly) === JSON.stringify(snap)) return;
    }
    state.history = state.history.slice(0, state.historyIndex + 1);
    state.history.push({ label: label || "编辑", assembly: snap });
    if (state.history.length > state.historyLimit) state.history.shift();
    state.historyIndex = state.history.length - 1;
    renderHistory();
  }

  function renderHistory() {
    var u = $("undo"), r = $("redo");
    if (u) u.disabled = state.historyIndex <= 0;
    if (r) r.disabled = state.historyIndex < 0 || state.historyIndex >= state.history.length - 1;
    if (u) u.title = state.historyIndex > 0 ? ("撤销：" + state.history[state.historyIndex].label + " (Ctrl+Z)") : "没有可撤销的编辑";
    if (r) r.title = state.historyIndex >= 0 && state.historyIndex < state.history.length - 1
      ? ("重做：" + state.history[state.historyIndex + 1].label + " (Ctrl+Shift+Z)") : "没有可重做的编辑";
  }

  function restoreHistory(index) {
    var entry = state.history[index];
    if (!entry) return;
    state.historyIndex = index;
    state.assembly = clone(entry.assembly);
    state.optimizer = null; state.angles = {}; state.playing = false; state.fitPending = true;
    if (state.selected && !rawById(state.selected)) {
      state.selected = state.assembly.components.length ? state.assembly.components[0].id : null;
    }
    revalidate();
    toast((index < state.history.length - 1 ? "已撤销：" : "已重做：") + entry.label, "ok");
  }

  function undo() {
    if (state.historyIndex <= 0) return;
    restoreHistory(state.historyIndex - 1);
  }

  function redo() {
    if (state.historyIndex < 0 || state.historyIndex >= state.history.length - 1) return;
    restoreHistory(state.historyIndex + 1);
  }

  function revalidate() {
    if (!state.assembly) return;
    if (state.assembly.budget_cny == null) state.assembly.budget_cny = 1000;
    state.optimizer = null; state.plan = null;
    // 保持选择有效
    if (state.selected && !rawById(state.selected)) state.selected = state.assembly.components[0] ? state.assembly.components[0].id : null;
    try {
      state.report = A.validate(state.assembly);
    } catch (e) {
      state.report = {
        ok: false, issues: [{ level: "error", code: "internal", message: "校验异常：" + e.message }],
        instances: [], bom: [], totalMass: 0, totalCost: 0, payload: 0,
        power: { planning: 0, supply: 0, peak: 0, idle: 0 },
        stability: { margin: null, com: null, tip: null, support: null }
      };
      toast("校验异常：" + e.message, "err");
    }
    // 删除已不存在实例的角度
    var valid = {};
    state.report.instances.forEach(function (i) { valid[i.id] = true; });
    Object.keys(state.angles).forEach(function (k) { if (!valid[k]) delete state.angles[k]; });
    if (!state.suppressSave) saveLocal();
    buildVisual();
    renderAll();
  }

  // ---------------------------------------------------------------- UI
  function renderPalette() {
    var q = ($("search").value || "").trim().toLowerCase();
    var groups = {};
    Object.keys(C).sort(function (a, b) { return (C[a].category + C[a].id).localeCompare(C[b].category + C[b].id); }).forEach(function (id) {
      var c = C[id];
      if (q && (id + " " + c.name + " " + (CAT_LABEL[c.category] || c.category)).toLowerCase().indexOf(q) < 0) return;
      (groups[c.category] = groups[c.category] || []).push(c);
    });
    var html = "";
    Object.keys(groups).sort(function (a, b) { return Object.keys(CAT_LABEL).indexOf(a) - Object.keys(CAT_LABEL).indexOf(b); }).forEach(function (cat) {
      html += '<div class="cat"><h2>' + esc(CAT_LABEL[cat] || cat) + '</h2>';
      groups[cat].forEach(function (c) {
        var tag = c.status === "concept" ? ' <span class="tag badge-concept">concept</span>' : "";
        html += '<button class="pitem" type="button" data-type="' + esc(c.id) + '" title="' + esc(c.description) + '">' +
          '<span class="mark" style="background:' + (CAT_COLOR[cat] || "#1d5f96") + '">' + esc((c.id.split(".")[0] || "?").slice(0, 2).toUpperCase()) + '</span>' +
          '<span class="meta"><b>' + esc(c.name) + tag + '</b><small>' + esc(c.id) + ' · ' + c.mass_g + 'g · ¥' + c.cost_cny + '</small></span></button>';
      });
      html += '</div>';
    });
    $("palette-list").innerHTML = html || '<div class="empty-note">没有匹配组件</div>';
    Array.prototype.forEach.call($("palette-list").querySelectorAll(".pitem"), function (btn) {
      btn.addEventListener("click", function () {
        if (state.replaceMode) replaceSelected(btn.getAttribute("data-type"));
        else addComponent(btn.getAttribute("data-type"));
      });
    });
  }
  function updatePaletteHint() {
    var foot = document.querySelector(".palette-foot");
    if (!foot) return;
    foot.innerHTML = state.replaceMode
      ? '<b style="color:var(--warn)">替换模式</b>：点一个组件替换当前选中件；再点右侧“取消替换”退出。'
      : '选中父件后点击组件。<b>替换</b>模式见右侧装配面板。';
  }

  function treeHtml(id, depth, seen) {
    seen = seen || {};
    if (seen[id]) return "";
    seen[id] = true;
    var raw = rawById(id); if (!raw) return "";
    var c = comp(raw.type);
    var solved = solvedById(id);
    var off = raw.offboard ? ' <span class="mini">offboard</span>' : "";
    var html = '<li><div class="node' + (id === state.selected ? " sel" : "") + '" data-id="' + esc(id) + '">' +
      '<span class="dot' + (raw.offboard ? " off" : "") + '"></span>' +
      '<span class="id">' + esc(id) + '</span>' +
      '<span class="ty">' + esc((c && c.name) || raw.type) + off + '</span>' +
      '<button type="button" data-del="' + esc(id) + '" title="删除">✕</button></div>';
    var kids = childIds(id);
    if (kids.length) html += '<ul>' + kids.map(function (k) { return treeHtml(k, depth + 1, seen); }).join("") + '</ul>';
    return html + '</li>';
  }
  function renderTree() {
    if (!state.assembly || !state.assembly.components.length) {
      $("tree").innerHTML = '<div class="empty-note">还没有组件。点“新建”，或从左侧组件库添加根件。</div>';
      return;
    }
    var roots = state.assembly.components.filter(function (c) { return !c.parent; });
    $("tree").innerHTML = '<ul class="tree">' + roots.map(function (r) { return treeHtml(r.id, 0); }).join("") + '</ul>';
    Array.prototype.forEach.call($("tree").querySelectorAll(".node"), function (n) {
      n.addEventListener("click", function (e) {
        if (e.target && e.target.getAttribute("data-del")) return;
        select(n.getAttribute("data-id"));
      });
    });
    Array.prototype.forEach.call($("tree").querySelectorAll("[data-del]"), function (b) {
      b.addEventListener("click", function (e) {
        e.stopPropagation(); select(b.getAttribute("data-del")); deleteSelected();
      });
    });
  }

  function renderSelected() {
    var raw = rawById(state.selected);
    if (!raw) { $("selected").innerHTML = '<div class="empty-note">选一个组件查看/编辑参数</div>'; return; }
    var c = comp(raw.type);
    var sc = solvedById(raw.id);
    var p = raw.parent ? rawById(raw.parent) : null;
    var pc = p ? comp(p.type) : null;
    var parentPorts = (pc && pc.ports) || [];
    var ownPorts = (c && c.ports) || [];
    var joint = (sc && sc.joint) || (c && c.joint) || null;
    var isGrid = false;
    for (var i = 0; i < parentPorts.length; i++) if (parentPorts[i].name === raw.port && parentPorts[i].kind === "mech.grid") isGrid = true;
    var html = '<div class="meta-card"><b>' + esc(c ? c.name : raw.type) + '</b> <span class="tag">' + esc(raw.type) + '</span>' +
      '<p>' + esc(c ? c.description : "") + '</p>' +
      '<div class="kv"><span>实例</span><span>' + esc(raw.id) + '</span><span>质量</span><span>' + (c ? c.mass_g + " g" : "—") + '</span>' +
      '<span>BOM</span><span>' + (c ? "¥" + c.cost_cny : "—") + '</span><span>状态</span><span>' + (sc ? "已求解" : "未求解") + '</span></div></div>';
    html += '<div class="form">' +
      '<div class="full"><label>父件</label><input value="' + esc(raw.parent || "— 根 —") + '" readonly></div>' +
      '<div><label>父端口</label><select id="f-port"' + (p ? "" : " disabled") + '>' +
      (p ? parentPorts.map(function (x) { return '<option value="' + esc(x.name) + '"' + (x.name === raw.port ? " selected" : "") + '>' + esc(x.name) + ' · ' + esc(x.kind) + '</option>'; }).join("") : '<option>—</option>') + '</select></div>' +
      '<div><label>子端口</label><select id="f-child-port">' +
      ownPorts.map(function (x) { return '<option value="' + esc(x.name) + '"' + (x.name === raw.child_port ? " selected" : "") + '>' + esc(x.name) + ' · ' + esc(x.kind) + '</option>'; }).join("") + '</select></div>' +
      '<div><label>at X (mm)</label><input id="f-atx" type="number" step="20" value="' + (raw.at ? raw.at[0] : 0) + '"' + (isGrid ? "" : " disabled") + '></div>' +
      '<div><label>at Y (mm)</label><input id="f-aty" type="number" step="20" value="' + (raw.at ? raw.at[1] : 0) + '"' + (isGrid ? "" : " disabled") + '></div>' +
      '<div><label>spin (°)</label><input id="f-spin" type="number" step="90" value="' + (raw.spin || 0) + '"></div>' +
      '<div><label>舵机 ID</label><input id="f-servo" type="number" min="1" step="1" value="' + (raw.servo_id == null ? "" : raw.servo_id) + '" placeholder="自动"></div>' +
      '<div class="full"><label>额外旋转 rot X/Y/Z (°)</label><div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:4px">' +
      '<input id="f-rx" type="number" step="5" value="' + ((raw.rot || [0, 0, 0])[0]) + '">' +
      '<input id="f-ry" type="number" step="5" value="' + ((raw.rot || [0, 0, 0])[1]) + '">' +
      '<input id="f-rz" type="number" step="5" value="' + ((raw.rot || [0, 0, 0])[2]) + '"></div></div>';
    if (joint) {
      html += '<div><label>关节名</label><input id="f-jname" value="' + esc(joint.name) + '"></div>' +
        '<div><label>单位</label><input value="' + esc(joint.unit) + '" readonly></div>' +
        '<div><label>min</label><input id="f-jmin" type="number" step="1" value="' + joint.min + '"></div>' +
        '<div><label>max</label><input id="f-jmax" type="number" step="1" value="' + joint.max + '"></div>';
    }
    html += '</div><div class="actions">' +
      '<button class="btn primary" id="apply-inst">应用参数</button>' +
      '<button class="btn" id="replace-inst">' + (state.replaceMode ? "取消替换" : "替换组件") + '</button>' +
      '<button class="btn danger" id="delete-inst">删除</button></div>';
    if (joint) html += '<div class="note">关节零位/方向/额定扭矩来自组件库；这里改的是实例限位。真机安全配置导出到 CLI 的 <code>safety.json</code>，网页不会写舵机。</div>';
    $("selected").innerHTML = html;
    $("apply-inst").addEventListener("click", applySelected);
    $("replace-inst").addEventListener("click", function () {
      state.replaceMode = !state.replaceMode;
      updatePaletteHint(); renderSelected();
      toast(state.replaceMode ? "替换模式：从左侧点新组件" : "已退出替换模式", state.replaceMode ? "" : "ok");
    });
    $("delete-inst").addEventListener("click", deleteSelected);
  }

  function applySelected() {
    var raw = rawById(state.selected);
    if (!raw) return;
    var atx = parseFloat($("f-atx").value), aty = parseFloat($("f-aty").value);
    raw.port = $("f-port") && !$("f-port").disabled ? $("f-port").value : raw.port;
    raw.child_port = $("f-child-port").value;
    raw.at = [isFinite(atx) ? atx : 0, isFinite(aty) ? aty : 0];
    raw.spin = parseFloat($("f-spin").value) || 0;
    raw.rot = [parseFloat($("f-rx").value) || 0, parseFloat($("f-ry").value) || 0, parseFloat($("f-rz").value) || 0];
    var sv = $("f-servo").value.trim();
    raw.servo_id = sv === "" ? null : parseInt(sv, 10);
    if ($("f-jmin") && $("f-jmax")) {
      var ov = raw.joint || {};
      ov.name = $("f-jname").value.trim() || ov.name;
      ov.min = parseFloat($("f-jmin").value);
      ov.max = parseFloat($("f-jmax").value);
      raw.joint = ov;
    }
    state.fitPending = true;
    pushHistory("修改组件参数");
    revalidate();
    toast("参数已应用", "ok");
  }

  function select(id) {
    if (!rawById(id)) return;
    state.selected = id;
    renderTree(); renderSelected();
    renderHighlights();
    updateHud();
  }

  function renderAll() {
    if ($("design-name") && document.activeElement !== $("design-name")) {
      $("design-name").value = state.assembly ? (state.assembly.name || "") : "";
    }
    if ($("strict")) $("strict").checked = !!(state.assembly && state.assembly.strict);
    renderTree();
    renderSelected();
    renderStatus();
    renderMetrics();
    renderTorque();
    renderIssues();
    renderBOM();
    renderPlan();
    renderOptimizer();
    renderJoints();
    renderExportState();
    renderHistory();
    renderHighlights();
    updateHud();
  }

  function renderStatus() {
    var r = state.report;
    var errs = r ? r.issues.filter(function (x) { return x.level === "error"; }).length : 0;
    var warns = r ? r.issues.filter(function (x) { return x.level === "warn"; }).length : 0;
    var budget = state.assembly && state.assembly.budget_cny != null ? state.assembly.budget_cny : 1000;
    var over = !!(r && r.totalCost > budget);
    var pill = $("validate-pill");
    pill.className = "validate-pill " + (errs ? "err" : (r ? (warns || over ? "warn" : "ok") : ""));
    pill.textContent = !r ? "未校验" : errs ? ("FAIL · " + errs + " 错误") :
      ((warns ? "PASS · " + warns + " 警告" : "PASS") + (over ? " · 超预算 ¥" + Math.round(r.totalCost - budget) : ""));
    var top = $("top-state"), txt = $("top-state-text");
    top.className = "status-pill " + (errs ? "err" : (warns || over ? "warn" : "ok"));
    txt.textContent = !r ? "未校验" : errs ? (errs + " 个错误") : "装配可求解";
    $("sim-state").textContent = state.playing ? ("运行中 · " + state.speed.toFixed(1) + "× · 运动学示意") : "待机 · 只做运动学示意";
    if (!state.playing) {
      $("play").textContent = "▶ 播放运动";
      $("play").setAttribute("aria-pressed", "false");
    }
  }

  function renderMetrics() {
    var r = state.report;
    if (!r) { $("metrics").innerHTML = ""; $("safety-note").textContent = ""; return; }
    var p = r.power, st = r.stability;
    var budget = state.assembly.budget_cny != null ? state.assembly.budget_cny : 1000;
    var over = r.totalCost > budget;
    var powerOk = p && p.supply > 0 && p.planning <= p.supply;
    var html = '<div class="metrics">' +
      '<div class="metric"><span>总质量</span><b>' + Math.round(r.totalMass) + ' g</b></div>' +
      '<div class="metric"><span>BOM 估算</span><b>¥' + Math.round(r.totalCost) + '</b></div>' +
      '<div class="metric' + (over ? " bad" : "") + '"><span>预算余量</span><b>' + (over ? "超 ¥" + Math.round(r.totalCost - budget) : "余 ¥" + Math.round(budget - r.totalCost)) + '</b></div>' +
      '<div class="metric' + (powerOk ? "" : (p && p.supply ? " warn" : " bad")) + '"><span>规划电流</span><b>' + (p ? p.planning.toFixed(2) : "—") + ' A</b></div>' +
      '<div class="metric"><span>电源</span><b>' + (p && p.supply ? p.supply.toFixed(1) + ' A' : "—") + '</b></div>' +
      '<div class="metric' + (st && st.margin != null && st.margin < 0 ? " bad" : (st && st.margin != null && st.margin < 10 ? " warn" : "")) + '"><span>支撑余量</span><b>' + (st && st.margin != null ? st.margin.toFixed(1) + ' mm' : "—") + '</b></div>' +
      '<div class="metric"><span>载荷</span><b>' + (r.payload || 0) + ' g</b></div></div>';
    html += '<div class="kv"><span>组件</span><span>' + r.instances.length + '</span>' +
      '<span>位置关节</span><span>' + r.instances.filter(function (i) { return i.joint && i.joint.mode === "position"; }).length + '</span>' +
      '<span>重心</span><span>' + (st && st.com ? st.com.map(function (v) { return v.toFixed(1); }).join(", ") : "—") + '</span>' +
      '<span>倾覆角估算</span><span>' + (st && st.tip != null ? st.tip.toFixed(1) + "°" : "—") + '</span></div>';
    html += '<div class="form" style="margin-top:7px"><div><label>工具载荷 / payload (g)</label>' +
      '<input id="payload" type="number" min="0" step="10" value="' + (r.payload || 0) + '"></div>' +
      '<div><label>预算 / budget (¥)</label><input id="budget" type="number" min="0" step="50" value="' + budget + '"></div></div>';
    $("metrics").innerHTML = html;
    var pi = $("payload");
    if (pi) pi.addEventListener("change", function () {
      state.assembly.payload_g = Math.max(0, parseFloat(pi.value) || 0);
      revalidate();
    });
    var bi = $("budget");
    if (bi) bi.addEventListener("change", function () {
      var v = parseFloat(bi.value);
      if (!isFinite(v) || v < 0) v = 1000;
      state.assembly.budget_cny = v;
      revalidate();
    });
    $("safety-note").innerHTML = '<b>安全边界</b>：网页只做装配/运动学示意，不是动力学、不是网格碰撞，也不会写舵机。' +
      (r.safety ? ' 导出 JSON 后可运行 <code>modkit assemble plan</code> 生成 <code>safety.json</code>；真机仍需标定。' : '');
  }

  function renderTorque() {
    var host = $("torque"), note = $("torque-note");
    if (!host) return;
    var loads = (state.report && state.report.jointLoads) || [];
    if (!loads.length) {
      host.innerHTML = "";
      if (note) note.textContent = "当前装配没有位置关节；不评估舵机力矩。";
      return;
    }
    host.innerHTML = '<thead><tr><th>关节</th><th>下游 g</th><th>力臂 mm</th><th>重力 N·m</th>' +
      '<th>动态 N·m</th><th>合计</th><th>额定</th><th>比例</th></tr></thead><tbody>' +
      loads.map(function (j) {
        var cls = j.ratio > 1 ? "bad" : (j.ratio > 0.5 ? "warn" : "");
        return '<tr class="' + cls + '"><td>' + esc(j.name) + ' <small>#' + j.servo_id + '</small></td>' +
          '<td>' + Math.round(j.mass) + '</td><td>' + Math.round(j.arm) + '</td>' +
          '<td>' + j.gravity.toFixed(2) + '</td><td>' + j.dynamic.toFixed(2) + '</td>' +
          '<td><b>' + j.load.toFixed(2) + '</b></td><td>' + j.rated.toFixed(2) + '</td>' +
          '<td>' + j.ratio.toFixed(2) + '×</td></tr>';
      }).join("") + '</tbody>';
    if (note) {
      var worst = loads.reduce(function (a, b) { return a.ratio >= b.ratio ? a : b; });
      note.textContent = "最坏姿态估算：3D 力臂 × 全部下游质量；重力 + 设计加速度 " +
        (state.report.instances.length && state.assembly.max_accel_m_s2 != null ? state.assembly.max_accel_m_s2 : 0.5) +
        " m/s²。最大 " + worst.name + " " + worst.ratio.toFixed(2) + "× 额定；不含角加速度/惯量/摩擦。";
    }
  }

  function renderIssues() {
    var r = state.report;
    if (!r) { $("issues").innerHTML = ""; return; }
    if (!r.issues.length) { $("issues").innerHTML = '<li class="info"><span class="msg">没有发现问题。注意：AABB/静载是保守估算。</span></li>'; return; }
    var order = { error: 0, warn: 1, info: 2 };
    var list = r.issues.slice().sort(function (a, b) { return order[a.level] - order[b.level]; });
    $("issues").innerHTML = list.map(function (x) {
      return '<li class="' + esc(x.level) + '"' + (x.instance ? ' data-inst="' + esc(x.instance) + '" tabindex="0" role="button" title="选中 ' + esc(x.instance) + '"' : "") +
        '><span class="code">' + esc(x.code) + (x.instance ? " · " + esc(x.instance) : "") + '</span><span class="msg">' + esc(x.message) + '</span></li>';
    }).join("");
    Array.prototype.forEach.call($("issues").querySelectorAll("[data-inst]"), function (el) {
      function go() { select(el.getAttribute("data-inst")); }
      el.addEventListener("click", go);
      el.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
    });
  }

  function landedCost(r) {
    var parts = r.totalCost || 0;
    var spares = parts * 0.08;
    var shipping = 30, wire = 25;
    var total = parts + spares + shipping + wire;
    var budget = state.assembly && state.assembly.budget_cny != null ? state.assembly.budget_cny : 1000;
    var target = (budget - shipping - wire) / 1.08;
    return { parts: parts, spares: spares, shipping: shipping, wire: wire,
      total: total, budget: budget, target: Math.max(0, target), over: Math.max(0, total - budget) };
  }

  function renderBOM() {
    var r = state.report;
    if (!r || !r.bom.length) { $("bom").innerHTML = ""; if ($("landed")) $("landed").innerHTML = ""; $("bom-note").textContent = ""; return; }
    var html = '<thead><tr><th>物料</th><th>规格</th><th>数量</th><th>单价</th><th>小计</th></tr></thead><tbody>';
    r.bom.forEach(function (b) {
      html += '<tr><td>' + esc(b.name) + '</td><td>' + esc(b.spec) + '</td><td class="n">' + b.qty + '</td><td class="n">¥' + b.unit_cost + '</td><td class="n">¥' + Math.round(b.cost) + '</td></tr>';
    });
    html += '</tbody>';
    $("bom").innerHTML = html;
    var e = landedCost(r);
    if ($("landed")) {
      $("landed").innerHTML = '<div class="landed-head">落地成本 <b>¥' + Math.round(e.total) +
        '</b><span class="' + (e.over > 0 ? "bad" : "ok") + '">' +
        (e.over > 0 ? '超预算 ¥' + Math.round(e.over) : '预算内 · 余 ¥' + Math.round(e.budget - e.total)) +
        '</span></div><div class="landed-grid">' +
        '<span>BOM ¥' + Math.round(e.parts) + '</span>' +
        '<span>备件 8% ¥' + Math.round(e.spares) + '</span>' +
        '<span>运费 ¥' + e.shipping + '</span>' +
        '<span>线材 ¥' + e.wire + '</span></div>';
    }
    $("bom-note").innerHTML = 'BOM <b>¥' + Math.round(r.totalCost) + '</b>、约 <b>' + Math.round(r.totalMass) +
      'g</b>；落地 <b>¥' + Math.round(e.total) + '</b>（含 8% 备件/¥' + e.shipping + ' 运费/¥' + e.wire +
      ' 线材端子）。预算 <b>¥' + Math.round(e.budget) + '</b>；' +
      (e.over > 0 ? '要落地 ≤ 预算，BOM 需 ≤ <b>¥' + Math.round(e.target) + '</b>（当前多 ¥' +
        Math.round(e.parts - e.target) + '）' : '当前落地价在预算内') +
      '。单价是组件库保守估算，不是供应商报价。';
  }

  function renderPlan() {
    var host = $("plan");
    if (!host) return;
    var p = state.plan;
    if (!p) { host.innerHTML = ""; return; }
    if (p.error) { host.innerHTML = '<div class="opt-empty">' + esc(p.error) + '</div>'; return; }
    var cls = (p.reached && p.feasible !== false) ? "ok" : "bad";
    var head = (p.reached && p.feasible !== false)
      ? ("目标 ¥" + Math.round(p.target) + " · " + p.steps.length + " 步可达 ¥" + Math.round(p.cost))
      : ("目标 ¥" + Math.round(p.target) + " · " + (p.feasible === false ? "约束未满足" : "最多到 ¥" + Math.round(p.cost) + "，仍差 ¥" + Math.round(p.remaining)));
    var html = '<div class="plan-card ' + cls + '"><div class="plan-head"><b>' + head + '</b>' +
      '<span class="plan-base">当前 ¥' + Math.round(p.baseCost) + '</span></div>';
    if (p.constraints && Object.keys(p.constraints).length) {
      var bits = [];
      if (p.constraints.minJoints != null) bits.push("≥" + p.constraints.minJoints + " 关节");
      if (p.constraints.minComponents != null) bits.push("≥" + p.constraints.minComponents + " 组件");
      if (p.constraints.maxMass != null) bits.push("≤" + Math.round(p.constraints.maxMass) + "g");
      if (p.constraints.maxRisk) bits.push("风险 ≤" + p.constraints.maxRisk);
      html += '<p class="opt-empty">约束：' + esc(bits.join("；")) + '</p>';
    }
    if (p.feasible === false) {
      html += '<p class="opt-empty">约束未满足：' + esc((p.violations || []).join("；")) + '</p>';
    }
    if (!p.steps.length) {
      html += '<p class="opt-empty">当前装配已经在预算内，不需要规划。</p>';
    } else {
      html += '<ol class="plan-steps">' + p.steps.map(function (s) {
        return '<li><span>' + esc(s.title) + '</span><em>¥' + Math.round(s.cost) +
          ' · 省 ¥' + Math.round(s.saving) + '</em></li>';
      }).join("") + '</ol>';
    }
    if (p.steps.length && p.reached) {
      html += '<div class="plan-actions"><button class="btn primary" id="apply-plan">应用全部</button>' +
        '<span class="note">会记一步撤销；可再导出报告/JSON</span></div>';
    } else if (p.steps.length) {
      html += '<p class="opt-empty">规划 ' + p.steps.length + ' 步后仍差 ¥' + Math.round(p.remaining) +
        '；需要更大幅度的结构改动，或先接受一个候选再继续规划。</p>';
    }
    if (p.truncated) {
      html += '<p class="opt-empty">搜索达到 ' + (p.nodes || 0) +
        ' 节点上限，结果可能不是全局最优；可减少步数或接受当前方案。</p>';
    }
    html += '</div>';
    host.innerHTML = html;
    var b = $("apply-plan");
    if (b) b.addEventListener("click", applyPlan);
  }

  function optimizerConstraints() {
    var c = {};
    var j = parseInt(($("c-min-joints") || {}).value, 10);
    var n = parseInt(($("c-min-components") || {}).value, 10);
    var m = parseFloat(($("c-max-mass") || {}).value);
    var r = ($("c-max-risk") || {}).value;
    if (j > 0) c.minJoints = j;
    if (n > 0) c.minComponents = n;
    if (m > 0) c.maxMass = m;
    if (r) c.maxRisk = r;
    return c;
  }

  function runPlan() {
    if (!state.assembly || !state.report) return;
    if (!window.MODKIT_BUDGET) { toast("预算优化器未加载", "err"); return; }
    var target = state.assembly.budget_cny != null ? state.assembly.budget_cny : 1000;
    try {
      state.plan = window.MODKIT_BUDGET.plan(state.assembly, target, 6,
        { maxNodes: 600, constraints: optimizerConstraints() });
    } catch (e) {
      state.plan = { error: "规划失败：" + e.message };
    }
    renderPlan();
    if (state.plan.error) toast(state.plan.error, "err");
    else if (state.plan.feasible === false) toast("约束未满足：" + (state.plan.violations || []).join("；"), "err");
    else if (state.plan.reached) toast("规划可达：¥" + Math.round(state.plan.cost), "ok");
    else toast("单步候选最多到 ¥" + Math.round(state.plan.cost) + "，仍差 ¥" + Math.round(state.plan.remaining), "err");
  }

  function applyPlan() {
    var p = state.plan;
    if (!p || !p.reached || p.feasible === false || !p.steps.length) return;
    var next = clone(p.assembly);
    next.name = (next.name || "design").replace(/-opt$/, "") + "-opt";
    next.description = "预算规划：" + p.steps.map(function (s) { return s.title; }).join(" → ") + "。" +
      (next.description || "");
    state.assembly = next;
    pushHistory("预算规划 " + p.steps.length + " 步");
    state.plan = null; state.optimizer = null;
    state.angles = {}; state.playing = false; state.fitPending = true;
    state.selected = next.components.length ? next.components[0].id : null;
    revalidate();
    toast("已应用预算规划：" + p.steps.length + " 步，¥" + Math.round(p.cost), "ok");
  }

  function renderOptimizer() {
    var host = $("optimizer"), note = $("optimizer-note");
    if (!host) return;
    var r = state.report;
    if (!r) { host.innerHTML = ""; if (note) note.textContent = ""; return; }
    var budget = state.assembly.budget_cny != null ? state.assembly.budget_cny : 1000;
    var over = r.totalCost > budget;
    if (note) note.textContent = over
      ? "当前超预算 ¥" + Math.round(r.totalCost - budget) + "；优先看高节省候选；◆ 为 (成本, 重量) Pareto 前沿。"
      : "当前在预算内；可勾选“同价减重”看成本不升、重量下降的候选；◆ 为 Pareto 前沿。";
    if (!state.optimizer) {
      host.innerHTML = '<div class="opt-empty">点“生成降本候选”，会基于当前装配逐个试算并重新校验。</div>';
      return;
    }
    if (!state.optimizer.length) {
      host.innerHTML = '<div class="opt-empty">没有找到既省钱又能通过校验的单步候选。可先换更小的工具/底盘，或接受当前预算。</div>';
      return;
    }
    var onlyPareto = !!($("pareto-only") && $("pareto-only").checked);
    var list = onlyPareto ? state.optimizer.filter(function (c) { return c.pareto; }) : state.optimizer;
    if (!list.length) {
      host.innerHTML = '<div class="opt-empty">没有 Pareto 非支配候选；取消“只看 Pareto”或放宽约束。</div>';
      return;
    }
    host.innerHTML = list.map(function (c) {
      var risk = c.risk || "medium";
      return '<div class="opt-card ' + esc(risk) + '">' +
        '<div class="opt-top"><b>' + esc(c.title) + (c.pareto ? '<span class="pareto-badge">◆ Pareto</span>' : '') +
        '</b><span class="opt-save">' +
        (c.saving > 0.01 ? '省 ¥' + Math.round(c.saving) : '成本不升') +
        (c.massSaving > 0.01 ? ' · 省重 ' + Math.round(c.massSaving) + 'g' : '') + '</span></div>' +
        '<p>' + esc(c.tradeoff) + '</p>' +
        '<div class="opt-meta"><span>¥' + Math.round(c.cost) + ' · ' + c.components + ' 组件 · ' + c.joints + ' 关节</span>' +
        '<button class="btn" data-opt="' + esc(c.id) + '">应用</button></div></div>';
    }).join("");
    Array.prototype.forEach.call(host.querySelectorAll("button[data-opt]"), function (b) {
      b.addEventListener("click", function () { applyOptimizer(b.getAttribute("data-opt")); });
    });
  }

  function runOptimizer() {
    if (!state.assembly || !state.report) return;
    if (!window.MODKIT_BUDGET) { toast("预算优化器未加载", "err"); return; }
    try {
      state.optimizer = window.MODKIT_BUDGET.suggest(state.assembly,
        { max: 24, includeMass: !!($("mass-mode") && $("mass-mode").checked),
          constraints: optimizerConstraints() });
    } catch (e) {
      state.optimizer = [];
      toast("优化计算失败：" + e.message, "err");
    }
    renderOptimizer();
    toast(state.optimizer.length ? ("生成 " + state.optimizer.length + " 个可验证候选") : "没有可验证的降本/减重候选", state.optimizer.length ? "ok" : "");
  }

  function exportOptimizerReport() {
    if (!state.optimizer && !state.plan) { toast("先生成候选或规划，再导出报告", ""); return; }
    var md = window.MODKIT_BUDGET.reportMarkdown(state.optimizer || [], state.report ? state.report.totalCost : 0,
      state.assembly ? state.assembly.name : "design", state.plan);
    download(designFileName("budget.md"), new Blob([md], { type: "text/markdown;charset=utf-8" }));
    toast("已导出预算优化报告（Markdown）", "ok");
  }

  function applyOptimizer(id) {
    if (!state.assembly || !state.optimizer) return;
    var c = null;
    state.optimizer.forEach(function (x) { if (x.id === id) c = x; });
    if (!c) return;
    var before = state.report ? state.report.totalCost : 0;
    var next = window.MODKIT_BUDGET.apply(state.assembly, c);
    if (!next) { toast("候选已失效，请重新生成", "err"); return; }
    next.name = (next.name || "design").replace(/-opt$/, "") + "-opt";
    next.description = "预算优化：应用「" + c.title + "」。" + (next.description || "");
    state.assembly = next;
    pushHistory("预算优化：" + c.title);
    state.optimizer = null;
    state.angles = {}; state.playing = false; state.fitPending = true;
    if (!next.components.some(function (x) { return x.id === state.selected; })) {
      state.selected = next.components.length ? next.components[0].id : null;
    }
    revalidate();
    state.optimizer = window.MODKIT_BUDGET.suggest(state.assembly,
      { max: 24, constraints: optimizerConstraints() });
    renderAll();
    toast("已应用：" + c.title + "，省 ¥" + Math.round(before - (state.report ? state.report.totalCost : before)), "ok");
  }

  function renderJoints() {
    var r = state.report;
    if (!r) { $("joints").innerHTML = ""; return; }
    var js = r.instances.filter(function (i) { return i.joint && i.joint.mode === "position"; });
    if (!js.length) { $("joints").innerHTML = '<div class="empty-note" style="border:0">当前装配没有可动的位置关节</div>'; return; }
    $("joints").innerHTML = js.map(function (i) {
      var j = i.joint, val = state.angles[i.id];
      if (val == null) val = j.unit === "ratio" ? 1 : 0;
      var unit = j.unit === "ratio" ? "" : (j.unit === "deg" ? "°" : j.unit);
      return '<div class="jrow"><label for="j-' + esc(i.id) + '" title="' + esc(i.id) + '">' + esc(j.name) + '</label>' +
        '<input id="j-' + esc(i.id) + '" data-inst="' + esc(i.id) + '" type="range" min="' + j.min + '" max="' + j.max + '" step="' + (j.unit === "ratio" ? 0.01 : 1) + '" value="' + val + '">' +
        '<output for="j-' + esc(i.id) + '" data-out="' + esc(i.id) + '">' + fmtVal(val, j) + unit + '</output></div>';
    }).join("");
    Array.prototype.forEach.call($("joints").querySelectorAll("input[type=range]"), function (el) {
      el.addEventListener("input", function () {
        state.angles[el.getAttribute("data-inst")] = parseFloat(el.value);
        if (state.playing) stopPlay();
        applyMotion();
        var out = $("joints").querySelector('[data-out="' + el.getAttribute("data-inst") + '"]');
        var inst = solvedById(el.getAttribute("data-inst"));
        if (out && inst) out.textContent = fmtVal(parseFloat(el.value), inst.joint) + (inst.joint.unit === "deg" ? "°" : "");
        updateHud();
      });
    });
  }
  function fmtVal(v, j) {
    if (j.unit === "ratio") return (v * 100).toFixed(0) + "%";
    return Number(v).toFixed(j.unit === "deg" ? 1 : 0);
  }

  function renderExportState() {
    var raw = rawById(state.selected);
    var c = raw ? comp(raw.type) : null;
    var btn = $("export-step");
    btn.disabled = !(c && c.cad_file);
    btn.textContent = c && c.cad_file ? ("下载 " + c.name + " STEP") : "选中件没有 STEP";
  }

  // ---------------------------------------------------------------- 导出
  function download(name, blob) {
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 10000);
  }
  function designFileName(ext) {
    var base = String(state.assembly.name || "design").replace(/[^\w\u4e00-\u9fa5-]+/g, "_").replace(/^modkit-/, "");
    return "modkit-" + base + "." + ext;
  }
  function exportJSON() {
    var data = clone(state.assembly);
    data.generator = "modkit Studio";
    data.schema_version = SCHEMA_VERSION;
    data.version = STUDIO_VERSION;
    data.exported = new Date().toISOString();
    download(designFileName("json"), new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    toast("已导出装配 JSON；可交给 modkit assemble plan", "ok");
  }
  function exportCSV() {
    if (!state.report) return;
    var rows = [["name", "spec", "qty", "unit_cost_cny", "cost_cny", "mass_g"]];
    state.report.bom.forEach(function (b) { rows.push([b.name, b.spec, b.qty, b.unit_cost, b.cost, b.mass_g]); });
    rows.push(["TOTAL", "", "", "", state.report.totalCost, state.report.totalMass]);
    var csv = rows.map(function (r) { return r.map(function (v) { return '"' + String(v).replace(/"/g, '""') + '"'; }).join(","); }).join("\n");
    download(designFileName("csv"), new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" }));
    toast("已导出 BOM CSV", "ok");
  }
  function exportProcure() {
    if (!state.report) return;
    var rows = [["类别", "物料", "规格", "用量", "采购/打印量", "备件", "单价", "小计", "备注"]];
    state.report.bom.forEach(function (b) {
      rows.push([b.category === "purchased" ? "采购" : "打印/自制", b.name, b.spec,
        b.qty, b.qty, 0, b.unit_cost, b.cost, b.category === "purchased" ? "采购" : "打印/自制"]);
    });
    var csv = rows.map(function (r) {
      return r.map(function (v) { return '"' + String(v).replace(/"/g, '""') + '"'; }).join(",");
    }).join("\n");
    download(designFileName("procure.csv"), new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" }));
    toast("已导出采购清单 CSV（备件预算见 BOM 说明）", "ok");
  }
  function exportSVG() {
    if (!state.report) return;
    download(designFileName("svg"), new Blob([A.svgReport(state.report)], { type: "image/svg+xml" }));
    toast("已导出 2D 装配预览 SVG", "ok");
  }
  function forEachTriangle(fn) {
    if (!view.ready || !state.report) return 0;
    view.root.updateMatrixWorld(true);
    var count = 0;
    var v0 = new THREE.Vector3(), v1 = new THREE.Vector3(), v2 = new THREE.Vector3();
    var n0 = new THREE.Vector3(), n1 = new THREE.Vector3(), n2 = new THREE.Vector3();
    var fnorm = new THREE.Vector3(), e1 = new THREE.Vector3(), e2 = new THREE.Vector3();
    view.root.traverse(function (o) {
      if (!o.isMesh || !o.geometry) return;
      var pos = o.geometry.attributes.position;
      if (!pos) return;
      var nor = o.geometry.attributes.normal;
      var idx = o.geometry.index;
      var nm = new THREE.Matrix3().getNormalMatrix(o.matrixWorld);
      var hex = o.material && o.material.color ? "#" + o.material.color.getHexString() : "#9aa4b2";
      var n = idx ? idx.count : pos.count;
      for (var i = 0; i + 2 < n; i += 3) {
        var i0 = idx ? idx.getX(i) : i, i1 = idx ? idx.getX(i + 1) : i + 1, i2 = idx ? idx.getX(i + 2) : i + 2;
        v0.fromBufferAttribute(pos, i0).applyMatrix4(o.matrixWorld);
        v1.fromBufferAttribute(pos, i1).applyMatrix4(o.matrixWorld);
        v2.fromBufferAttribute(pos, i2).applyMatrix4(o.matrixWorld);
        if (nor) {
          n0.fromBufferAttribute(nor, i0).applyMatrix3(nm).normalize();
          n1.fromBufferAttribute(nor, i1).applyMatrix3(nm).normalize();
          n2.fromBufferAttribute(nor, i2).applyMatrix3(nm).normalize();
        } else {
          e1.subVectors(v1, v0); e2.subVectors(v2, v0);
          fnorm.crossVectors(e1, e2).normalize();
          n0.copy(fnorm); n1.copy(fnorm); n2.copy(fnorm);
        }
        fn(v0, v1, v2, n0, n1, n2, hex);
        count++;
      }
    });
    return count;
  }

  // GLB：Z-up mm -> Y-up m；按材质颜色分 primitive。
  function buildGLB() {
    var groups = {}, triCount = 0;
    forEachTriangle(function (a, b, c, na, nb, nc, hex) {
      var g = groups[hex];
      if (!g) g = groups[hex] = { pos: [], nor: [], idx: [], color: hex };
      var base = g.pos.length / 3;
      [a, b, c].forEach(function (v) { g.pos.push(v.x * 0.001, v.z * 0.001, -v.y * 0.001); });
      [na, nb, nc].forEach(function (n) { g.nor.push(n.x, n.z, -n.y); });
      g.idx.push(base, base + 1, base + 2);
      triCount++;
    });
    if (!triCount) throw new Error("没有可导出的网格");
    var json = {
      asset: { version: "2.0", generator: "modkit Studio " + STUDIO_VERSION },
      scene: 0, scenes: [{ nodes: [0] }],
      nodes: [{ mesh: 0, name: state.assembly.name || "modkit assembly" }],
      meshes: [{ primitives: [] }], materials: [], accessors: [], bufferViews: [], buffers: []
    };
    var binParts = [], binLen = 0;
    function align4() {
      var pad = (4 - (binLen % 4)) % 4;
      if (pad) { binParts.push(new Uint8Array(pad)); binLen += pad; }
    }
    function addView(typed, target) {
      align4();
      var bytes = new Uint8Array(typed.buffer, typed.byteOffset, typed.byteLength);
      var view = { buffer: 0, byteOffset: binLen, byteLength: bytes.byteLength };
      if (target) view.target = target;
      json.bufferViews.push(view);
      binParts.push(bytes);
      binLen += bytes.byteLength;
      return json.bufferViews.length - 1;
    }
    function addAccessor(view, componentType, type, count, min, max) {
      var a = { bufferView: view, componentType: componentType, count: count, type: type };
      if (min) a.min = min;
      if (max) a.max = max;
      json.accessors.push(a);
      return json.accessors.length - 1;
    }
    var mi = 0;
    Object.keys(groups).forEach(function (hex) {
      var g = groups[hex];
      var p = new Float32Array(g.pos), n = new Float32Array(g.nor), ix = new Uint32Array(g.idx);
      var min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
      for (var i = 0; i < p.length; i += 3) {
        min[0] = Math.min(min[0], p[i]); max[0] = Math.max(max[0], p[i]);
        min[1] = Math.min(min[1], p[i + 1]); max[1] = Math.max(max[1], p[i + 1]);
        min[2] = Math.min(min[2], p[i + 2]); max[2] = Math.max(max[2], p[i + 2]);
      }
      var pv = addView(p, 34962), nv = addView(n, 34962), iv = addView(ix, 34963);
      var pa = addAccessor(pv, 5126, "VEC3", p.length / 3, min, max);
      var na = addAccessor(nv, 5126, "VEC3", n.length / 3);
      var ia = addAccessor(iv, 5125, "SCALAR", ix.length);
      var col = new THREE.Color(hex);
      json.materials.push({ name: "mat_" + hex.replace("#", ""), doubleSided: true,
        pbrMetallicRoughness: { baseColorFactor: [col.r, col.g, col.b, 1], metallicFactor: 0.08, roughnessFactor: 0.7 } });
      json.meshes[0].primitives.push({ attributes: { POSITION: pa, NORMAL: na }, indices: ia, material: mi++ });
    });
    align4();
    json.buffers.push({ byteLength: binLen });
    var jsonBytes = new TextEncoder().encode(JSON.stringify(json));
    var jsonPad = (4 - (jsonBytes.length % 4)) % 4;
    var jsonTotal = jsonBytes.length + jsonPad;
    var binPad = (4 - (binLen % 4)) % 4;
    var binTotal = binLen + binPad;
    var total = 12 + 8 + jsonTotal + 8 + binTotal;
    var out = new Uint8Array(total), dv = new DataView(out.buffer);
    dv.setUint32(0, 0x46546C67, true); dv.setUint32(4, 2, true); dv.setUint32(8, total, true);
    dv.setUint32(12, jsonTotal, true); dv.setUint32(16, 0x4E4F534A, true);
    out.set(jsonBytes, 20);
    for (var j = 0; j < jsonPad; j++) out[20 + jsonBytes.length + j] = 0x20;
    var o = 20 + jsonTotal;
    dv.setUint32(o, binTotal, true); dv.setUint32(o + 4, 0x004E4942, true);
    var off = o + 8;
    binParts.forEach(function (part) { out.set(part, off); off += part.byteLength; });
    return out.buffer;
  }
  function exportGLB() {
    try {
      var buf = buildGLB();
      download(designFileName("glb"), new Blob([buf], { type: "model/gltf-binary" }));
      toast("已导出 GLB（Y-up，米制）；可进 Blender/Three/AR", "ok");
    } catch (e) { toast("GLB 导出失败：" + e.message, "err"); }
  }

  // 3MF：Z-up mm；最小 ZIP store 容器。
  var CRC_TABLE = null;
  function crc32TextZip(bytes) {
    if (!CRC_TABLE) {
      CRC_TABLE = new Uint32Array(256);
      for (var n = 0; n < 256; n++) {
        var c = n;
        for (var k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1;
        CRC_TABLE[n] = c >>> 0;
      }
    }
    var crc = 0xFFFFFFFF;
    for (var i = 0; i < bytes.length; i++) crc = CRC_TABLE[(crc ^ bytes[i]) & 0xFF] ^ (crc >>> 8);
    return (crc ^ 0xFFFFFFFF) >>> 0;
  }
  function zipStoreText(files) {
    var enc = new TextEncoder(), locals = [], centrals = [], offset = 0;
    var DOS_DATE = 0x5C21, DOS_TIME = 0; // 2026-01-01
    files.forEach(function (f) {
      var name = enc.encode(f.name), data = enc.encode(f.text), crc = crc32(data);
      var lh = new Uint8Array(30 + name.length), dv = new DataView(lh.buffer);
      dv.setUint32(0, 0x04034B50, true); dv.setUint16(4, 20, true); dv.setUint16(6, 0, true);
      dv.setUint16(8, 0, true); dv.setUint16(10, DOS_TIME, true); dv.setUint16(12, DOS_DATE, true);
      dv.setUint32(14, crc, true); dv.setUint32(18, data.length, true); dv.setUint32(22, data.length, true);
      dv.setUint16(26, name.length, true); dv.setUint16(28, 0, true);
      lh.set(name, 30);
      locals.push(lh, data);
      var ch = new Uint8Array(46 + name.length), cv = new DataView(ch.buffer);
      cv.setUint32(0, 0x02014B50, true); cv.setUint16(4, 20, true); cv.setUint16(6, 20, true);
      cv.setUint16(8, 0, true); cv.setUint16(10, 0, true); cv.setUint16(12, DOS_TIME, true); cv.setUint16(14, DOS_DATE, true);
      cv.setUint32(16, crc, true); cv.setUint32(20, data.length, true); cv.setUint32(24, data.length, true);
      cv.setUint16(28, name.length, true); cv.setUint16(30, 0, true); cv.setUint16(32, 0, true);
      cv.setUint16(34, 0, true); cv.setUint16(36, 0, true); cv.setUint32(38, 0, true); cv.setUint32(42, offset, true);
      ch.set(name, 46);
      centrals.push(ch);
      offset += lh.length + data.length;
    });
    var cdSize = centrals.reduce(function (n, x) { return n + x.length; }, 0);
    var eocd = new Uint8Array(22), ev = new DataView(eocd.buffer);
    ev.setUint32(0, 0x06054B50, true); ev.setUint16(4, 0, true); ev.setUint16(6, 0, true);
    ev.setUint16(8, files.length, true); ev.setUint16(10, files.length, true);
    ev.setUint32(12, cdSize, true); ev.setUint32(16, offset, true); ev.setUint16(20, 0, true);
    var total = offset + cdSize + eocd.length, out = new Uint8Array(total), p = 0;
    locals.concat(centrals, [eocd]).forEach(function (x) { out.set(x, p); p += x.length; });
    return out;
  }
  function build3MF() {
    var verts = [], tris = [];
    var n = forEachTriangle(function (a, b, c) {
      var base = verts.length / 3;
      [a, b, c].forEach(function (v) { verts.push(v.x.toFixed(3), v.y.toFixed(3), v.z.toFixed(3)); });
      tris.push(base, base + 1, base + 2);
    });
    if (!n) throw new Error("没有可导出的网格");
    var vx = [], tx = [];
    for (var i = 0; i < verts.length; i += 3) vx.push('<vertex x="' + verts[i] + '" y="' + verts[i + 1] + '" z="' + verts[i + 2] + '"/>');
    for (var j = 0; j < tris.length; j += 3) tx.push('<triangle v1="' + tris[j] + '" v2="' + tris[j + 1] + '" v3="' + tris[j + 2] + '"/>');
    var title = esc(state.assembly.name || "modkit assembly");
    var model = '<?xml version="1.0" encoding="UTF-8"?>' +
      '<model unit="millimeter" xml:lang="zh-CN" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">' +
      '<metadata name="Title">' + title + '</metadata>' +
      '<metadata name="Application">modkit Studio ' + STUDIO_VERSION + '</metadata>' +
      '<resources><object id="1" type="model" name="' + title + '"><mesh><vertices>' + vx.join("") +
      '</vertices><triangles>' + tx.join("") + '</triangles></mesh></object></resources><build><item objectid="1"/></build></model>';
    return zipStoreText([
      { name: "[Content_Types].xml", text: '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>' },
      { name: "_rels/.rels", text: '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>' },
      { name: "3D/3dmodel.model", text: model }
    ]);
  }
  function export3MF() {
    try {
      var bytes = build3MF();
      download(designFileName("3mf"), new Blob([bytes], { type: "model/3mf" }));
      toast("已导出 3MF（Z-up，毫米）；可直接进切片器", "ok");
    } catch (e) { toast("3MF 导出失败：" + e.message, "err"); }
  }

  function buildPrintHTML() {
    var r = state.report;
    if (!r) throw new Error("尚未校验");
    var budget = state.assembly.budget_cny != null ? state.assembly.budget_cny : 1000;
    var rows = r.bom.map(function (b) {
      return '<tr><td>' + esc(b.name) + '</td><td>' + esc(b.spec) + '</td><td class="n">' + b.qty +
        '</td><td class="n">¥' + b.unit_cost + '</td><td class="n">¥' + Math.round(b.cost) + '</td></tr>';
    }).join("");
    var issues = r.issues.length ? r.issues.map(function (x) {
      return '<li class="' + esc(x.level) + '">[' + esc(x.level) + '] ' + esc(x.code) + ' · ' + esc(x.message) + '</li>';
    }).join("") : '<li>没有发现问题。</li>';
    return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>' + esc(state.assembly.name || "modkit") +
      ' · BOM</title><style>body{font:12px/1.5 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;color:#1b2430;margin:24px;}' +
      'h1{font-size:20px;margin:0 0 2px}h2{font-size:13px;margin:18px 0 6px}table{border-collapse:collapse;width:100%;}' +
      'th,td{border-bottom:1px solid #dbe3ed;padding:4px 5px;text-align:left;font-size:10.5px}th{background:#f4f7fb}.n{text-align:right;font-family:monospace}' +
      '.meta{color:#607086;font-size:11px}.total{font-weight:700}li{margin:2px 0;font-size:10px}.error{color:#c0392b}.warn{color:#a66b00}' +
      '@media print{body{margin:10mm}button{display:none}}</style></head><body>' +
      '<h1>' + esc(state.assembly.name || "未命名装配") + '</h1><div class="meta">modkit Studio ' + STUDIO_VERSION +
      ' · 导出于 ' + new Date().toLocaleString("zh-CN") + '</div>' +
      '<h2>汇总</h2><div class="meta">组件 ' + r.instances.length + ' · 质量 ' + Math.round(r.totalMass) +
      'g · BOM ¥' + Math.round(r.totalCost) + ' · 预算 ¥' + Math.round(budget) +
      ' · 预算差 ¥' + Math.round(budget - r.totalCost) + '</div>' +
      '<h2>BOM</h2><table><thead><tr><th>物料</th><th>规格</th><th class="n">数量</th><th class="n">单价</th><th class="n">小计</th></tr></thead><tbody>' +
      rows + '</tbody><tfoot><tr class="total"><td>TOTAL</td><td></td><td></td><td></td><td class="n">¥' + Math.round(r.totalCost) + '</td></tr></tfoot></table>' +
      '<h2>校验问题</h2><ul>' + issues + '</ul>' +
      '<p class="meta">AABB/静载是保守估算；这不是实物验证。打印本页可存为 PDF。</p>' +
      '</body></html>';
  }
  function printSheet() {
    var html;
    try { html = buildPrintHTML(); } catch (e) { toast(e.message, "err"); return; }
    var w = window.open("", "_blank");
    if (!w) {
      download(designFileName("bom.html"), new Blob([html], { type: "text/html;charset=utf-8" }));
      toast("弹窗被拦截，已下载可打印 HTML", "");
      return;
    }
    w.document.open(); w.document.write(html); w.document.close();
    w.focus();
    setTimeout(function () { try { w.print(); } catch (e) { /* 用户可手动打印 */ } }, 350);
  }

  function exportSTL() {
    if (!view.ready || !state.report) { toast("3D 未就绪", "err"); return; }
    var tris = [];
    view.root.updateMatrixWorld(true);
    view.root.traverse(function (o) {
      if (!o.isMesh || !o.geometry) return;
      var geo = o.geometry;
      var pos = geo.attributes.position;
      if (!pos) return;
      var idx = geo.index;
      var va = new THREE.Vector3(), vb = new THREE.Vector3(), vc = new THREE.Vector3();
      function vert(i) { var v = new THREE.Vector3().fromBufferAttribute(pos, i).applyMatrix4(o.matrixWorld); return v; }
      var n = idx ? idx.count : pos.count;
      for (var i = 0; i + 2 < n; i += 3) {
        var i0 = idx ? idx.getX(i) : i, i1 = idx ? idx.getX(i + 1) : i + 1, i2 = idx ? idx.getX(i + 2) : i + 2;
        va.copy(vert(i0)); vb.copy(vert(i1)); vc.copy(vert(i2));
        tris.push([va.clone(), vb.clone(), vc.clone()]);
      }
    });
    if (!tris.length) { toast("没有可导出的网格", "err"); return; }
    var buf = new ArrayBuffer(84 + tris.length * 50);
    var dv = new DataView(buf);
    var header = "modkit Studio assembled mesh - units mm - " + state.report.instances.length + " components";
    for (var i = 0; i < 80; i++) dv.setUint8(i, i < header.length ? header.charCodeAt(i) : 32);
    dv.setUint32(80, tris.length, true);
    var off = 84;
    tris.forEach(function (t) {
      var ab = new THREE.Vector3().subVectors(t[1], t[0]);
      var ac = new THREE.Vector3().subVectors(t[2], t[0]);
      var n = new THREE.Vector3().crossVectors(ab, ac).normalize();
      [n, t[0], t[1], t[2]].forEach(function (v) {
        dv.setFloat32(off, v.x, true); dv.setFloat32(off + 4, v.y, true); dv.setFloat32(off + 8, v.z, true);
        off += 12;
      });
      dv.setUint16(off, 0, true); off += 2;
    });
    download(designFileName("stl"), new Blob([buf], { type: "model/stl" }));
    toast("已导出装配 STL（" + tris.length + " 三角形，mm）", "ok");
  }
  function exportSTEP() {
    var raw = rawById(state.selected); var c = raw ? comp(raw.type) : null;
    if (!c || !c.cad_file) { toast("当前件没有可下载的 STEP", "err"); return; }
    var a = document.createElement("a");
    a.href = c.cad_file; a.download = c.cad_file.split("/").pop();
    document.body.appendChild(a); a.click(); a.remove();
    toast("已下载 " + c.name + " STEP", "ok");
  }
  function crc32(buf) {
    if (!crc32.table) {
      var t = new Uint32Array(256);
      for (var n = 0; n < 256; n++) { var c = n; for (var k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1); t[n] = c; }
      crc32.table = t;
    }
    var crc = 0xFFFFFFFF;
    for (var i = 0; i < buf.length; i++) crc = (crc >>> 8) ^ crc32.table[(crc ^ buf[i]) & 0xFF];
    return (crc ^ 0xFFFFFFFF) >>> 0;
  }
  function zipStore(entries) {
    var enc = new TextEncoder(), locals = [], centrals = [], offset = 0;
    entries.forEach(function (e) {
      var name = enc.encode(e.name), data = e.data, crc = crc32(data), n = data.length;
      var lh = new Uint8Array(30 + name.length);
      var dv = new DataView(lh.buffer);
      dv.setUint32(0, 0x04034b50, true); dv.setUint16(4, 20, true); dv.setUint16(6, 0, true);
      dv.setUint16(8, 0, true); dv.setUint16(10, 0, true); dv.setUint16(12, 0, true);
      dv.setUint32(14, crc, true); dv.setUint32(18, n, true); dv.setUint32(22, n, true);
      dv.setUint16(26, name.length, true); dv.setUint16(28, 0, true);
      lh.set(name, 30);
      locals.push(lh, data);
      var ch = new Uint8Array(46 + name.length); var cv = new DataView(ch.buffer);
      cv.setUint32(0, 0x02014b50, true); cv.setUint16(4, 20, true); cv.setUint16(6, 20, true);
      cv.setUint16(8, 0, true); cv.setUint16(10, 0, true); cv.setUint16(12, 0, true); cv.setUint16(14, 0, true);
      cv.setUint32(16, crc, true); cv.setUint32(20, n, true); cv.setUint32(24, n, true);
      cv.setUint16(28, name.length, true); cv.setUint16(30, 0, true); cv.setUint16(32, 0, true);
      cv.setUint16(34, 0, true); cv.setUint16(36, 0, true); cv.setUint32(38, 0, true);
      cv.setUint32(42, offset, true); ch.set(name, 46);
      centrals.push(ch);
      offset += 30 + name.length + n;
    });
    var centralSize = centrals.reduce(function (s, c) { return s + c.length; }, 0);
    var end = new Uint8Array(22); var ev = new DataView(end.buffer);
    ev.setUint32(0, 0x06054b50, true); ev.setUint16(8, entries.length, true); ev.setUint16(10, entries.length, true);
    ev.setUint32(12, centralSize, true); ev.setUint32(16, offset, true);
    return new Blob(locals.concat(centrals, [end]), { type: "application/zip" });
  }
  async function exportStepZip() {
    if (!state.report) { toast("先加载/校验装配", "err"); return; }
    var files = {};
    state.report.instances.forEach(function (i) { if (i.component.cad_file) files[i.component.cad_file] = true; });
    var list = Object.keys(files).sort();
    if (!list.length) { toast("装配里没有带 STEP 的零件", "err"); return; }
    var entries = [];
    for (var k = 0; k < list.length; k++) {
      try {
        var r = await fetch(list[k]);
        if (!r.ok) throw new Error("HTTP " + r.status);
        entries.push({ name: list[k].split("/").pop(), data: new Uint8Array(await r.arrayBuffer()) });
      } catch (e) {
        toast("读取 " + list[k] + " 失败：" + e.message, "err"); return;
      }
    }
    download(designFileName("step.zip"), zipStore(entries));
    toast("已导出 " + entries.length + " 个零件 STEP（ZIP）", "ok");
  }
  function copyPackCommand() {
    var name = String(state.assembly.name || "design").replace(/[^\w\u4e00-\u9fa5-]+/g, "_");
    var cmd = "cd robot-modkit/software && ../.venv/bin/python -m modkit.cli assemble pack ../" + name + ".json --out ../out/pack-" + name;
    function done() { toast("硬件包命令已复制；先导出 JSON 到 assemblies/", "ok"); }
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(cmd).then(done, function () { window.prompt("复制命令", cmd); });
    else window.prompt("复制命令", cmd);
  }
  function copyCommand() {
    var name = String(state.assembly.name || "design").replace(/[^\w\u4e00-\u9fa5-]+/g, "_");
    var cmd = "cd robot-modkit/software && ../.venv/bin/python -m modkit.cli assemble plan ../" + name + ".json --out ../cad/out/assemblies/" + name;
    function done() { toast("命令已复制；先导出 JSON 到 assemblies/", "ok"); }
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(cmd).then(done, function () { window.prompt("复制命令", cmd); });
    else window.prompt("复制命令", cmd);
  }

  // ---------------------------------------------------------------- 播放
  function playText(running) {
    var en = window.MODKIT_I18N && window.MODKIT_I18N.lang === "en";
    if (running) return en ? "■ Stop" : "■ 停止";
    return en ? "▶ Play motion" : "▶ 播放运动";
  }
  function startPlay() {
    if (!state.report) return;
    if (!state.report.ok) { toast("先修正校验错误再播放", "err"); return; }
    if (state.reduceMotion) {
      toast("系统已开启“减少动态”，播放已停用；请用关节滑杆逐帧查看", "err");
      return;
    }
    var js = state.report.instances.filter(function (i) { return i.joint && i.joint.mode === "position"; });
    if (!js.length && !view.wheelVisuals.length) { toast("没有可动的关节或驱动轮", "err"); return; }
    state.playing = true; state.playStart = performance.now();
    $("play").textContent = playText(true); $("play").setAttribute("aria-pressed", "true");
    renderStatus();
  }
  function stopPlay() {
    state.playing = false;
    $("play").textContent = playText(false); $("play").setAttribute("aria-pressed", "false");
    renderStatus();
  }
  window.addEventListener("modkit:lang", function () {
    if ($("play") && !state.playing) $("play").textContent = playText(false);
  });
  function animateLoop() {
    requestAnimationFrame(animateLoop);
    if (!view.ready) return;
    if (state.playing && state.report && state.report.ok) {
      var t = (performance.now() - state.playStart) / 1000 * state.speed;
      var js = state.report.instances.filter(function (i) { return i.joint && i.joint.mode === "position"; });
      js.forEach(function (i, k) {
        var j = i.joint;
        var phase = k * 1.15;
        var u = 0.5 + 0.5 * Math.sin(t * 1.1 + phase);
        var v = j.unit === "ratio" ? u : j.min + (j.max - j.min) * u;
        state.angles[i.id] = v;
        var slider = $("j-" + i.id);
        if (slider) slider.value = v;
        var out = $("joints").querySelector('[data-out="' + i.id + '"]');
        if (out) out.textContent = fmtVal(v, j) + (j.unit === "deg" ? "°" : "");
      });
      applyMotion();
    }
    if (view.selectedHelper) view.selectedHelper.update();
    view.issueHelpers.forEach(function (h) { h.update(); });
    if (view.controls) view.controls.update();
    if (view.renderer) view.renderer.render(view.scene, view.camera);
  }

  // ---------------------------------------------------------------- tabs
  function showTab(name) {
    ["build", "check", "bom", "export"].forEach(function (k) {
      $("tab-" + k).hidden = k !== name;
      var b = $("tab-btn-" + k);
      b.setAttribute("aria-selected", k === name ? "true" : "false");
      b.tabIndex = k === name ? 0 : -1;
    });
  }

  // ---------------------------------------------------------------- init
  function boot() {
    initThree();
    renderPalette();
    $("search").addEventListener("input", renderPalette);
    $("preset").addEventListener("change", function () { loadPreset($("preset").value); });
    $("new-design").addEventListener("click", newDesign);
    $("undo").addEventListener("click", undo);
    $("redo").addEventListener("click", redo);
    $("import-design").addEventListener("click", function () { $("import-file").click(); });
    initDragDrop();
    $("copy-part").addEventListener("click", copySelected);
    $("paste-part").addEventListener("click", pasteClipboard);
    $("dup-part").addEventListener("click", duplicateSelected);
    $("share-design").addEventListener("click", shareDesign);
    $("viewer-design").addEventListener("click", openViewer);
    window.addEventListener("hashchange", function () {
      if (/^#d=/.test(location.hash || "")) loadShared();
    });
    $("import-file").addEventListener("change", function () { importDesign($("import-file").files[0]); $("import-file").value = ""; });
    $("restore-design").addEventListener("click", restoreLocal);
    $("validate").addEventListener("click", function () { revalidate(); toast("已重新校验", "ok"); });
    $("strict").addEventListener("change", function () {
      if (!state.assembly) return;
      state.assembly.strict = $("strict").checked;
      revalidate();
    });
    $("design-name").addEventListener("change", function () {
      if (!state.assembly) return;
      state.assembly.name = $("design-name").value.trim() || "未命名装配";
      revalidate();
    });
    $("project-select").addEventListener("change", function () {
      if ($("project-select").value) loadProject($("project-select").value);
      else renderProjects();
    });
    $("project-save").addEventListener("click", saveProject);
    $("project-new").addEventListener("click", newProject);
    $("project-delete").addEventListener("click", deleteProject);
    $("version-save").addEventListener("click", snapshotVersion);
    $("version-restore").addEventListener("click", restoreVersion);
    $("play").addEventListener("click", function () { state.playing ? stopPlay() : startPlay(); });
    $("reset-motion").addEventListener("click", function () {
      stopPlay(); state.angles = {};
      view.wheelVisuals.forEach(function (w) { w.wheel.rotation.y = 0; if (w.hub) w.hub.rotation.y = 0; });
      renderJoints(); applyMotion(); toast("关节已复位", "ok");
    });
    $("speed").addEventListener("input", function () { state.speed = parseFloat($("speed").value) || 1; renderStatus(); });
    $("fit-view").addEventListener("click", fitCamera);
    var tabKeys = ["build", "check", "bom", "export"];
    tabKeys.forEach(function (k, idx) {
      var b = $("tab-btn-" + k);
      b.addEventListener("click", function () { showTab(k); });
      b.addEventListener("keydown", function (e) {
        var next = null;
        if (e.key === "ArrowRight") next = tabKeys[(idx + 1) % tabKeys.length];
        else if (e.key === "ArrowLeft") next = tabKeys[(idx - 1 + tabKeys.length) % tabKeys.length];
        else if (e.key === "Home") next = tabKeys[0];
        else if (e.key === "End") next = tabKeys[tabKeys.length - 1];
        if (!next) return;
        e.preventDefault();
        showTab(next);
        $("tab-btn-" + next).focus();
      });
    });
    $("optimize").addEventListener("click", runOptimizer);
    $("plan-budget").addEventListener("click", runPlan);
    $("pareto-only").addEventListener("change", renderOptimizer);
    $("export-optimizer").addEventListener("click", exportOptimizerReport);
    $("export-json").addEventListener("click", exportJSON);
    $("export-csv").addEventListener("click", exportCSV);
    if ($("export-procure")) $("export-procure").addEventListener("click", exportProcure);
    $("export-stl").addEventListener("click", exportSTL);
    $("export-glb").addEventListener("click", exportGLB);
    $("export-3mf").addEventListener("click", export3MF);
    $("export-print").addEventListener("click", printSheet);
    $("export-svg").addEventListener("click", exportSVG);
    $("export-step").addEventListener("click", exportSTEP);
    $("export-step-zip").addEventListener("click", exportStepZip);
    $("copy-command").addEventListener("click", copyCommand);
    $("copy-pack").addEventListener("click", copyPackCommand);
    document.addEventListener("keydown", function (e) {
      if (!(e.ctrlKey || e.metaKey)) return;
      var tag = (e.target && e.target.tagName || "").toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select") return;
      var k = String(e.key || "").toLowerCase();
      if (k === "z") { e.preventDefault(); e.shiftKey ? redo() : undo(); }
      else if (k === "y") { e.preventDefault(); redo(); }
      else if (k === "c") { e.preventDefault(); copySelected(); }
      else if (k === "v") { e.preventDefault(); pasteClipboard(); }
      else if (k === "d") { e.preventDefault(); duplicateSelected(); }
    });
    $("loading").style.display = "none";
    var q = new URLSearchParams(location.search);
    var preset = q.get("preset");
    if (!preset || !P[preset]) preset = "m1";
    loadWorkspace();
    state.suppressSave = true;
    if (loadShared()) {
      // 分享快照不覆盖项目
    } else if (workspace.active && projectById(workspace.active)) {
      loadProject(workspace.active, { silent: true });
    } else {
      loadPreset(preset);
    }
    state.suppressSave = false;
    renderProjects();
    try { $("restore-design").disabled = !localStorage.getItem(LOCAL_KEY) && !workspace.projects.length; } catch (e) {}
    requestAnimationFrame(animateLoop);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();

  // 轻量调试/自动化入口：不改变正常 UI，但让浏览器 QA 能检查求解和场景。
  window.MODKIT_STUDIO = {
    state: state, view: view, select: select, renderAll: renderAll, addComponent: addComponent, replaceSelected: replaceSelected,
    deleteSelected: deleteSelected, revalidate: revalidate, loadPreset: loadPreset,
    applyMotion: applyMotion, exportSTL: exportSTL, exportJSON: exportJSON,
    exportStepZip: exportStepZip, fitCamera: fitCamera,
    buildGLB: buildGLB, build3MF: build3MF, buildPrintHTML: buildPrintHTML,
    optimize: runOptimizer, applyOptimization: applyOptimizer,
    planBudget: runPlan, applyPlan: applyPlan,
    exportOptimizerReport: exportOptimizerReport, undo: undo, redo: redo,
    copySelected: copySelected, pasteClipboard: pasteClipboard, duplicateSelected: duplicateSelected,
    renderHighlights: renderHighlights, shareDesign: shareDesign, loadShared: loadShared,
    openViewer: openViewer, viewerURL: viewerURL,
    optimizerConstraints: optimizerConstraints,
    saveProject: saveProject, newProject: newProject, deleteProject: deleteProject,
    loadProject: loadProject, snapshotVersion: snapshotVersion, restoreVersion: restoreVersion,
    renderProjects: renderProjects, migrateAssembly: migrateAssembly,
    workspace: function () { return workspace; }
  };
})();
