/* modkit 实时查看器
 *
 * 三件事：
 * 1) 用 three.js 按 cad/params.py 的尺寸搭一台可动的机器人（不是贴图、不是预渲染）
 * 2) 拖动滑杆实时改关节角，右侧显示正解出来的末端位置
 * 3) 可选：用 Web Serial 直接连总线舵机（Chrome/Edge，需要 https 或 localhost）
 *
 * 所有数字来自 window.MODKIT_SCENE（sim/export_web.py 生成），这里不重复写尺寸。
 */
(function () {
  "use strict";

  var S = window.MODKIT_SCENE;
  if (!S) {
    document.getElementById("status").textContent = "缺少 scene.js，请先运行 sim/export_web.py";
    return;
  }
  var P = S.params, L = S.limits;

  function $(id) { return document.getElementById(id); }
  function setStatus(text, kind) {
    var el = $("status");
    el.textContent = text;
    el.className = "status " + (kind || "");
  }
  window.addEventListener("error", function (e) {
    setStatus("JS 错误：" + e.message, "err");
  });

  // ------------------------------------------------------------------ 场景
  var canvas = $("view");
  var renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

  var scene = new THREE.Scene();
  scene.background = new THREE.Color(0xeaeff6);

  var camera = new THREE.PerspectiveCamera(40, 1, 1, 5000);
  camera.up.set(0, 0, 1);
  camera.position.set(360, -420, 300);

  var controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.target.set(60, 0, 110);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;

  scene.add(new THREE.HemisphereLight(0xffffff, 0x9aa4b2, 0.95));
  var dir = new THREE.DirectionalLight(0xffffff, 0.75);
  dir.position.set(300, -400, 500);
  scene.add(dir);
  var dir2 = new THREE.DirectionalLight(0xffffff, 0.35);
  dir2.position.set(-300, 250, 200);
  scene.add(dir2);

  // 地面 + 网格（three 的 GridHelper 在 XZ 平面，转到 XY）
  var ground = new THREE.Mesh(
    new THREE.PlaneGeometry(1400, 1400),
    new THREE.MeshLambertMaterial({ color: 0xf7f9fc })
  );
  ground.position.z = -55.1;
  scene.add(ground);

  var grid = new THREE.GridHelper(800, 16, 0xc8d2e0, 0xdfe6ef);
  grid.rotation.x = Math.PI / 2;
  grid.position.z = -54.9;
  scene.add(grid);

  var MAT = {
    chassis: new THREE.MeshLambertMaterial({ color: 0xd8dee9 }),
    steel: new THREE.MeshLambertMaterial({ color: 0x4c78a8 }),
    joint: new THREE.MeshLambertMaterial({ color: 0x2f3b45 }),
    wheel: new THREE.MeshLambertMaterial({ color: 0x33383f }),
    bracket: new THREE.MeshLambertMaterial({ color: 0xe45756 }),
    gripper: new THREE.MeshLambertMaterial({ color: 0x54a24b }),
    wrist: new THREE.MeshLambertMaterial({ color: 0xf58518 }),
    servo: new THREE.MeshLambertMaterial({ color: 0x8c8c8c }),
    cam: new THREE.MeshLambertMaterial({ color: 0xb279a2 }),
    block: new THREE.MeshLambertMaterial({ color: 0xe45756 })
  };

  function box(w, d, h, mat) {
    return new THREE.Mesh(new THREE.BoxGeometry(w, d, h), mat);
  }
  function cyl(r, h, mat) {
    // three 的圆柱轴默认沿 Y，正好是轮轴方向
    return new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, 24), mat);
  }

  // ------------------------------------------------------------------ 机器人
  var robot = new THREE.Group();
  scene.add(robot);

  // 底盘
  var chassis = box(P.chassisX, P.chassisY, P.chassisT, MAT.chassis);
  chassis.position.z = -P.chassisT / 2;
  robot.add(chassis);

  // 接缝
  var seam = box(2, P.chassisY, P.chassisT + 0.5, MAT.joint);
  seam.position.z = -P.chassisT / 2;
  robot.add(seam);

  // 驱动轮 + 舵机 + 支架
  [-1, 1].forEach(function (s) {
    var wheel = cyl(P.wheelR, P.wheelW, MAT.wheel);
    wheel.position.set(0, s * P.wheelY, P.servoZ);
    robot.add(wheel);

    var hub = cyl(P.wheelR * 0.34, P.wheelW + 2, MAT.steel);
    hub.position.set(0, s * P.wheelY, P.servoZ);
    robot.add(hub);

    var servo = box(46, 25, 36, MAT.servo);
    servo.position.set(0, s * P.driveY, P.servoZ);
    robot.add(servo);

    var bracket = box(60, 44, 5, MAT.bracket);
    bracket.position.set(0, s * P.driveY, -2.5);
    robot.add(bracket);
  });

  // 相机
  var cam = box(30, 30, 22, MAT.cam);
  cam.position.set(P.camX, P.camY, 11);
  robot.add(cam);

  // 偏航组（绕 Z）
  var yawGroup = new THREE.Group();
  yawGroup.position.set(P.armX, 0, 0);
  robot.add(yawGroup);

  var column = cyl(P.columnR, P.baseH, MAT.steel);
  column.rotation.x = Math.PI / 2;          // 轴转到 Z
  column.position.z = P.baseH / 2;
  yawGroup.add(column);

  var baseJoint = cyl(19, 26, MAT.joint);
  baseJoint.rotation.x = Math.PI / 2;
  baseJoint.position.z = 4;
  yawGroup.add(baseJoint);

  // 肩组（绕 Y）
  var shoulderGroup = new THREE.Group();
  shoulderGroup.position.z = P.baseH;
  yawGroup.add(shoulderGroup);

  var shoulderJoint = cyl(15, 30, MAT.joint);
  shoulderJoint.rotation.z = Math.PI / 2;   // 轴转到 Y
  shoulderGroup.add(shoulderJoint);

  var upperArm = box(P.l1, P.linkW, P.linkT, MAT.steel);
  upperArm.position.x = P.l1 / 2;
  shoulderGroup.add(upperArm);

  // 肘组
  var elbowGroup = new THREE.Group();
  elbowGroup.position.x = P.l1;
  shoulderGroup.add(elbowGroup);

  var elbowJoint = cyl(14, 28, MAT.joint);
  elbowJoint.rotation.z = Math.PI / 2;
  elbowGroup.add(elbowJoint);

  var forearm = box(P.l2, P.linkW - 4, P.linkT - 2, MAT.steel);
  forearm.position.x = P.l2 / 2;
  elbowGroup.add(forearm);

  // 腕 + 夹爪
  var wristGroup = new THREE.Group();
  wristGroup.position.x = P.l2;
  elbowGroup.add(wristGroup);

  var wristBase = box(34, 44, 14, MAT.wrist);
  wristGroup.add(wristBase);

  var jawA = box(P.gripperLen, P.jawT, 46, MAT.gripper);
  var jawB = box(P.gripperLen, P.jawT, 46, MAT.gripper);
  jawA.position.x = P.gripperLen / 2;
  jawB.position.x = P.gripperLen / 2;
  wristGroup.add(jawA);
  wristGroup.add(jawB);

  var tipMark = new THREE.Mesh(new THREE.SphereGeometry(5, 16, 12),
    new THREE.MeshBasicMaterial({ color: 0xe45756 }));
  wristGroup.add(tipMark);

  // 被抓的方块（跟随动画时贴到指尖）
  var blockMesh = box(40, 40, 40, MAT.block);
  blockMesh.position.set(200, 0, 20);
  scene.add(blockMesh);

  // ------------------------------------------------------------------ 状态
  var state = {
    yaw: 0, shoulder: 35, elbow: -55, jaw: 1,
    playing: false, t: 0, held: false
  };

  function gapMm(jaw) {
    return P.jawOpen * jaw + P.jawClosed * (1 - jaw);
  }

  function applyState() {
    yawGroup.rotation.z = THREE.MathUtils.degToRad(state.yaw);
    shoulderGroup.rotation.y = -THREE.MathUtils.degToRad(state.shoulder);
    elbowGroup.rotation.y = -THREE.MathUtils.degToRad(state.elbow);

    var gap = gapMm(state.jaw);
    jawA.position.y = gap / 2 + P.jawT / 2;
    jawB.position.y = -(gap / 2 + P.jawT / 2);
    tipMark.position.x = P.gripperLen + 6;

    // 正解：指尖在底盘坐标系的位置（mm），与 software/modkit/kinematics.py 同式
    var sh = THREE.MathUtils.degToRad(state.shoulder);
    var el = THREE.MathUtils.degToRad(state.shoulder + state.elbow);
    var yaw = THREE.MathUtils.degToRad(state.yaw);
    var ex = P.l1 * Math.cos(sh), ez = P.l1 * Math.sin(sh);
    var wx = ex + P.l2 * Math.cos(el), wz = ez + P.l2 * Math.sin(el);
    var tx = wx + P.gripperLen * Math.cos(el);
    var tz = wz + P.gripperLen * Math.sin(el);
    $("fk").textContent =
      "x " + (P.armX + tx * Math.cos(yaw)).toFixed(0) +
      "  y " + (tx * Math.sin(yaw)).toFixed(0) +
      "  z " + (P.baseH + tz).toFixed(0) + " mm" +
      "   |   夹爪 " + gap.toFixed(0) + " mm";

    $("v-yaw").textContent = state.yaw.toFixed(0) + "°";
    $("v-shoulder").textContent = state.shoulder.toFixed(0) + "°";
    $("v-elbow").textContent = state.elbow.toFixed(0) + "°";
    $("v-jaw").textContent = gap.toFixed(0) + " mm";

    if (state.held) {
      var tip = new THREE.Vector3(P.gripperLen, 0, 0);
      wristGroup.localToWorld(tip);
      blockMesh.position.copy(tip);
    }
  }

  // ------------------------------------------------------------------ 滑杆
  var sliders = [
    ["yaw", "yaw", L.yaw[0], L.yaw[1], 1],
    ["shoulder", "shoulder", L.shoulder[0], L.shoulder[1], 1],
    ["elbow", "elbow", L.elbow[0], L.elbow[1], 1],
    ["jaw", "jaw", 0, 1, 0.01]
  ];
  sliders.forEach(function (s) {
    var name = s[0], el = $("s-" + name);
    el.min = s[2]; el.max = s[3]; el.step = s[4];
    el.value = state[name];
    el.addEventListener("input", function () {
      state[name] = parseFloat(el.value);
      state.playing = false;
      $("play").textContent = "▶ 播放抓取动画";
      applyState();
    });
  });

  $("reset").addEventListener("click", function () {
    state.yaw = 0; state.shoulder = 35; state.elbow = -55; state.jaw = 1;
    state.playing = false; state.held = false;
    blockMesh.position.set(200, 0, 20);
    $("s-yaw").value = state.yaw; $("s-shoulder").value = state.shoulder;
    $("s-elbow").value = state.elbow; $("s-jaw").value = state.jaw;
    $("play").textContent = "▶ 播放抓取动画";
    applyState();
  });

  // ------------------------------------------------------------------ 动画
  var KF = S.keyframes;
  var SEG = 1.25;                            // 每段秒数

  $("play").addEventListener("click", function () {
    state.playing = !state.playing;
    state.held = false;
    blockMesh.position.set(200, 0, 20);
    if (state.playing) state.t = 0;
    $("play").textContent = state.playing ? "⏸ 暂停" : "▶ 播放抓取动画";
  });

  function poseAt(t) {
    var f = t / SEG;
    var i = Math.max(0, Math.min(KF.length - 2, Math.floor(f)));
    var u = Math.min(1, Math.max(0, f - i));
    var a = KF[i], b = KF[i + 1];
    u = u * u * (3 - 2 * u);                  // smoothstep，避免阶跃看起来"抽"
    state.yaw = a.yaw + (b.yaw - a.yaw) * u;
    state.shoulder = a.shoulder + (b.shoulder - a.shoulder) * u;
    state.elbow = a.elbow + (b.elbow - a.elbow) * u;
    state.jaw = a.jaw + (b.jaw - a.jaw) * u;

    var label = u < 0.5 ? a.label : b.label;
    state.held = t > SEG * 3.2 && t < SEG * 6.9;
    if (state.held) label = "夹住方块";
    $("phase").textContent = label;
    applyState();
  }

  function tickAnim(dt) {
    if (!state.playing) return;
    state.t += dt;
    var total = (KF.length - 1) * SEG - 0.6;
    if (state.t > total) {
      state.t = 0;
      state.held = false;
      blockMesh.position.set(200, 0, 20);
    }
    poseAt(state.t);
  }

  // ------------------------------------------------------------------ 视角
  var VIEWS = {
    iso: [[360, -420, 300], [60, 0, 110]],
    front: [[560, 0, 180], [60, 0, 110]],
    side: [[0, -560, 160], [60, 0, 110]],
    top: [[40, -30, 700], [60, 0, 40]]
  };
  Object.keys(VIEWS).forEach(function (k) {
    $("view-" + k).addEventListener("click", function () {
      var v = VIEWS[k];
      camera.position.set(v[0][0], v[0][1], v[0][2]);
      controls.target.set(v[1][0], v[1][1], v[1][2]);
      controls.update();
    });
  });

  // ------------------------------------------------------------------ Web Serial
  var port = null, writer = null, reader = null, reading = false;

  function frame(id, instr, params) {
    var len = params.length + 2;
    var sum = id + len + instr;
    params.forEach(function (p) { sum += p; });
    var chk = (~sum) & 0xff;
    var out = [0xff, 0xff, id, len, instr].concat(params, [chk]);
    return new Uint8Array(out);
  }

  function ticks(deg) {
    var t = Math.round(2048 + deg / 0.087890625);
    return Math.max(0, Math.min(4095, t));
  }

  function log(msg, kind) {
    var line = document.createElement("div");
    line.className = "logline " + (kind || "");
    line.textContent = new Date().toLocaleTimeString() + "  " + msg;
    $("log").prepend(line);
    while ($("log").children.length > 40) $("log").lastChild.remove();
  }

  async function send(bytes, label) {
    if (!writer) { log("未连接", "err"); return; }
    try {
      await writer.write(bytes);
      log(label + "  →  " + Array.from(bytes).map(function (b) {
        return b.toString(16).padStart(2, "0");
      }).join(" "));
    } catch (e) {
      log("写失败：" + e.message, "err");
    }
  }

  async function connect() {
    if (!("serial" in navigator)) {
      log("这个浏览器不支持 Web Serial（用 Chrome/Edge，且需 https 或 localhost）", "err");
      return;
    }
    try {
      port = await navigator.serial.requestPort();
      await port.open({ baudRate: 1000000 });
      writer = port.writable.getWriter();
      $("serial-state").textContent = "已连接 1Mbps";
      $("serial-state").className = "pill ok";
      log("串口已连接，1Mbps 8N1", "ok");
      readLoop();
    } catch (e) {
      log("连接失败：" + e.message, "err");
    }
  }

  async function readLoop() {
    if (!port || !port.readable) return;
    reading = true;
    reader = port.readable.getReader();
    var buf = [];
    try {
      while (reading) {
        var r = await reader.read();
        if (r.done) break;
        for (var i = 0; i < r.value.length; i++) buf.push(r.value[i]);
        // 找完整帧：FF FF id len ...
        while (buf.length >= 6) {
          if (buf[0] !== 0xff || buf[1] !== 0xff) { buf.shift(); continue; }
          var total = buf[3] + 4;
          if (buf.length < total) break;
          var f = buf.splice(0, total);
          var params = f.slice(5, total - 1);
          if (f[4] === 0x00 && params.length >= 8) {
            var pos = params[0] | (params[1] << 8);
            log("ID " + f[2] + " 位置 " + pos + " (" + (pos * 0.087890625).toFixed(1) + "°)");
          }
        }
      }
    } catch (e) {
      log("读失败：" + e.message, "err");
    } finally {
      if (reader) { try { reader.releaseLock(); } catch (e) {} }
    }
  }

  $("serial-connect").addEventListener("click", connect);

  $("serial-estop").addEventListener("click", function () {
    if (!writer) { log("未连接：急停请直接关主电源", "err"); return; }
    S.ids && Object.keys(S.ids).forEach(function (k) {
      send(frame(S.ids[k], 0x03, [0x28, 0x00]), "卸力 ID " + S.ids[k]);
    });
  });

  $("serial-send").addEventListener("click", function () {
    if (!writer) { log("未连接", "err"); return; }
    var pairs = [
      [S.ids.yaw, state.yaw],
      [S.ids.shoulder, state.shoulder],
      [S.ids.elbow, state.elbow]
    ];
    pairs.forEach(function (p) {
      var t = ticks(p[1]);
      // 写 0x2A 起 6 字节：位置(2) + 时间(2) + 速度(2)
      send(frame(p[0], 0x03, [0x2A, t & 0xff, t >> 8, 0, 0, 0xE8, 0x03]), "ID " + p[0] + " → " + t);
    });
    // 夹爪：0° 全开 → 180° 全闭（按实际机械行程改）
    var g = ticks(180 - 60 * (1 - state.jaw));
    send(frame(S.ids.gripper, 0x03, [0x2A, g & 0xff, g >> 8, 0, 0, 0xE8, 0x03]), "夹爪 → " + g);
  });

  // ------------------------------------------------------------------ 渲染循环
  function resize() {
    var w = canvas.clientWidth, h = canvas.clientHeight;
    if (w === 0 || h === 0) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  window.addEventListener("resize", resize);

  var last = performance.now();
  function loop(now) {
    // 注意 dt 可能为负：headless/虚拟时间里第一帧 now 会小于模块加载时的 last
    var dt = Math.min(0.05, Math.max(0, (now - last) / 1000));
    last = now;
    try { tickAnim(dt); } catch (e) { setStatus("动画异常：" + e.message, "err"); state.playing = false; }
    controls.update();
    renderer.render(scene, camera);
    requestAnimationFrame(loop);
  }

  // 给脚本/截图用：?autoplay 播放；?t=3.5 直接跳到某一时刻（不播放）
  var mT = location.search.match(/[?&]t=([\d.]+)/);
  if (mT) {
    state.playing = false;
    state.t = parseFloat(mT[1]);
    poseAt(state.t);
    $("play").textContent = "▶ 播放抓取动画";
  } else if (/autoplay/.test(location.search)) {
    state.playing = true;
    $("play").textContent = "⏸ 暂停";
  }

  applyState();
  resize();
  setStatus("就绪：拖动滑杆改关节角，或点「播放抓取动画」", "ok");
  requestAnimationFrame(loop);
})();