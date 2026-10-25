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
    var top = $("top-state"), topText = $("top-state-text");
    if (top) {
      top.className = "status-pill " + (kind || "");
      if (topText) topText.textContent = kind === "err" ? "3D 异常" : "3D 就绪";
    }
  }
  window.addEventListener("error", function (e) {
    setStatus("JS 错误：" + e.message, "err");
  });

  // ------------------------------------------------------------------ 场景
  var canvas = $("view");
  if (!window.THREE) {
    $("webgl-fallback").classList.add("show");
    setStatus("three.js 未加载：请检查 web/vendor/，参数面板仍可用", "err");
    return;
  }
  var renderer = null;
  try {
    renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    if (THREE.SRGBColorSpace) renderer.outputColorSpace = THREE.SRGBColorSpace;
    if (THREE.ACESFilmicToneMapping) {
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.0;
    }
  } catch (e) {
    $("webgl-fallback").classList.add("show");
    setStatus("3D 不可用：" + e.message + "（参数与真机调试仍可用）", "err");
  }

  var scene = new THREE.Scene();
  scene.background = new THREE.Color(0xeaeff6);

  var camera = new THREE.PerspectiveCamera(40, 1, 1, 5000);
  camera.up.set(0, 0, 1);
  camera.position.set(360, -420, 300);

  var controls;
  if (THREE.OrbitControls) {
    controls = new THREE.OrbitControls(camera, canvas);
    controls.target.set(60, 0, 110);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.minDistance = 150;
    controls.maxDistance = 1200;
    controls.maxPolarAngle = Math.PI * 0.5;
  } else {
    controls = { target: { set: function () {} }, update: function () {} };
    setStatus("OrbitControls 未加载：视角固定", "err");
  }

  scene.add(new THREE.HemisphereLight(0xffffff, 0x9aa4b2, 0.95));
  var dir = new THREE.DirectionalLight(0xfff6ec, 1.0);
  dir.position.set(300, -420, 520);
  dir.castShadow = true;
  dir.shadow.mapSize.set(2048, 2048);
  dir.shadow.camera.near = 50;
  dir.shadow.camera.far = 2200;
  dir.shadow.camera.left = -420;
  dir.shadow.camera.right = 420;
  dir.shadow.camera.top = 420;
  dir.shadow.camera.bottom = -420;
  dir.shadow.bias = -0.0009;
  dir.shadow.radius = 3;
  scene.add(dir);
  var dir2 = new THREE.DirectionalLight(0xffffff, 0.35);
  dir2.position.set(-300, 250, 200);
  scene.add(dir2);

  // 地面 + 网格（three 的 GridHelper 在 XZ 平面，转到 XY）
  var ground = new THREE.Mesh(
    new THREE.PlaneGeometry(1400, 1400),
    new THREE.MeshStandardMaterial({ roughness: 0.72, metalness: 0.04, color: 0xf7f9fc })
  );
  ground.position.z = -55.1;
  ground.receiveShadow = true;
  scene.add(ground);

  var grid = new THREE.GridHelper(800, 16, 0xc8d2e0, 0xdfe6ef);
  grid.rotation.x = Math.PI / 2;
  grid.position.z = -54.9;
  scene.add(grid);

  var MAT = {
    chassis: new THREE.MeshStandardMaterial({ roughness: 0.72, metalness: 0.04, color: 0xd8dee9 }),
    steel: new THREE.MeshStandardMaterial({ roughness: 0.72, metalness: 0.04, color: 0x4c78a8 }),
    joint: new THREE.MeshStandardMaterial({ roughness: 0.72, metalness: 0.04, color: 0x2f3b45 }),
    wheel: new THREE.MeshStandardMaterial({ roughness: 0.72, metalness: 0.04, color: 0x33383f }),
    bracket: new THREE.MeshStandardMaterial({ roughness: 0.72, metalness: 0.04, color: 0xe45756 }),
    gripper: new THREE.MeshStandardMaterial({ roughness: 0.72, metalness: 0.04, color: 0x54a24b }),
    wrist: new THREE.MeshStandardMaterial({ roughness: 0.72, metalness: 0.04, color: 0xf58518 }),
    servo: new THREE.MeshStandardMaterial({ roughness: 0.72, metalness: 0.04, color: 0x8c8c8c }),
    cam: new THREE.MeshStandardMaterial({ roughness: 0.72, metalness: 0.04, color: 0xb279a2 }),
    block: new THREE.MeshStandardMaterial({ roughness: 0.72, metalness: 0.04, color: 0xe45756 })
  };

  function box(w, d, h, mat) {
    var m = new THREE.Mesh(new THREE.BoxGeometry(w, d, h), mat);
    m.castShadow = true;
    m.receiveShadow = true;
    return m;
  }
  function cyl(r, h, mat) {
    // three 的圆柱轴默认沿 Y，正好是轮轴方向
    var m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, 24), mat);
    m.castShadow = true;
    m.receiveShadow = true;
    return m;
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
    playing: false, t: 0, held: false, follow: false
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
      stopAnim("手动");
      animProgress(0);
      applyState();
    });
  });

  $("reset").addEventListener("click", function () {
    state.yaw = 0; state.shoulder = 35; state.elbow = -55; state.jaw = 1;
    state.playing = false; state.held = false;
    blockMesh.position.set(200, 0, 20);
    $("s-yaw").value = state.yaw; $("s-shoulder").value = state.shoulder;
    $("s-elbow").value = state.elbow; $("s-jaw").value = state.jaw;
    stopAnim("待机");
    animProgress(0);
    applyState();
    toast("已复位", "ok");
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
    $("phase").textContent = state.playing ? "开始" : "已暂停";
    if (!state.playing) animProgress(state.t);
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
    animProgress(t);
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
  function setView(k) {
    var v = VIEWS[k];
    if (!v) return;
    camera.position.set(v[0][0], v[0][1], v[0][2]);
    controls.target.set(v[1][0], v[1][1], v[1][2]);
    controls.update();
    Object.keys(VIEWS).forEach(function (name) {
      var b = $("view-" + name);
      if (!b) return;
      var on = name === k;
      b.classList.toggle("active", on);
      b.setAttribute("aria-pressed", String(on));
    });
  }
  Object.keys(VIEWS).forEach(function (k) {
    $("view-" + k).addEventListener("click", function () { setView(k); });
  });

  // ------------------------------------------------------------------ Web Serial
  // 寄存器：0x28 扭矩使能、0x2A 目标位置(2)+时间(2)+速度(2)、0x38 反馈 8 字节
  // 0x41 状态位（故障）。读 0x38 拿不到故障位，必须单独读。
  var REG_TORQUE = 0x28, REG_GOAL = 0x2A, REG_FB = 0x38, REG_STATUS = 0x41;
  var JOINTS = [
    ["yaw", "偏航"], ["shoulder", "肩"], ["elbow", "肘"], ["gripper", "夹爪"]
  ];
  var port = null, writer = null, reader = null, reading = false, pollTimer = null;
  var torqueOn = false, demo = false, demoTimer = null;
  var csv = [], recording = false;
  var fb = {};                    // name -> {pos, speed, load, volts, temp, status, seen}

  JOINTS.forEach(function (j) {
    fb[j[0]] = { pos: null, speed: 0, load: 0, volts: null, temp: null, status: 0, seen: false };
  });

  function toast(msg, kind) {
    var t = $("toast");
    t.textContent = msg;
    t.className = "toast show" + (kind ? " " + kind : "");
    clearTimeout(toast._timer);
    toast._timer = setTimeout(function () { t.className = "toast"; }, kind === "err" ? 5200 : 3200);
  }

  function setSerialState(connected, text) {
    var el = $("serial-state");
    if (el) {
      el.textContent = text || (connected ? "已连接" : "未连接");
      el.className = "pill " + (connected ? "ok" : "");
    }
    ["serial-disconnect", "serial-torque", "serial-send", "serial-follow", "serial-record"]
      .forEach(function (id) { if ($(id)) $(id).disabled = !connected; });
    var es = $("serial-estop");
    if (es) { es.disabled = !connected; es.classList.toggle("show", !!connected); }
  }
  setSerialState(false);

  var safetyOK = false, pendingSafety = null;
  function guardSafety(fn) {
    if (safetyOK || demo) { fn(); return; }
    pendingSafety = fn;
    $("safety-check").checked = false;
    $("safety-ok").disabled = true;
    $("safety-dialog").showModal();
  }
  function closeSafety() {
    pendingSafety = null;
    $("safety-dialog").close();
  }
  $("safety-check").addEventListener("change", function () {
    $("safety-ok").disabled = !this.checked;
  });
  $("safety-ok").addEventListener("click", function () {
    if (!$("safety-check").checked) return;
    safetyOK = true;
    var fn = pendingSafety;
    $("safety-dialog").close(); pendingSafety = null;
    if (fn) fn();
    toast("已确认安全：本次会话不再重复弹窗", "ok");
  });
  $("safety-cancel").addEventListener("click", closeSafety);
  $("safety-cancel-x").addEventListener("click", closeSafety);

  function animProgress(t) {
    var total = (S.keyframes.length - 1) * SEG - 0.6;
    var pct = Math.max(0, Math.min(100, total > 0 ? t / total * 100 : 0));
    var bar = $("anim-progress"), wrap = bar && bar.parentElement;
    if (bar) bar.style.width = pct.toFixed(1) + "%";
    if (wrap) wrap.setAttribute("aria-valuenow", String(Math.round(pct)));
  }
  function stopAnim(label) {
    state.playing = false;
    $("play").textContent = "▶ 播放抓取动画";
    $("phase").textContent = label || "待机";
  }

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
    while ($("log").children.length > 30) $("log").lastChild.remove();
  }

  // 串口写入必须串行，否则多帧会交错
  var queue = Promise.resolve();
  function send(bytes, label, silent) {
    if (!writer) { if (!silent) log("未连接", "err"); return Promise.resolve(); }
    queue = queue.then(function () {
      return writer.write(bytes).then(function () {
        if (!silent) {
          log(label + "  →  " + Array.from(bytes).map(function (b) {
            return b.toString(16).padStart(2, "0");
          }).join(" "));
        }
      });
    }).catch(function (e) { log("写失败：" + e.message, "err"); });
    return queue;
  }

  function setTorque(on) {
    if (!writer) { log("先连接串口", "err"); return; }
    JOINTS.forEach(function (j) {
      send(frame(S.ids[j[0]], 0x03, [REG_TORQUE, on ? 1 : 0]), null, true);
    });
    torqueOn = on;
    $("serial-torque").textContent = on ? "卸力" : "使能扭矩";
    $("serial-torque").className = on ? "action danger" : "action";
    log(on ? "已使能扭矩（保持当前位置）" : "已卸力", on ? "ok" : "");
  }

  async function connect() {
    if (!("serial" in navigator)) {
      log("这个浏览器不支持 Web Serial（用 Chrome/Edge，且需 https 或 localhost）", "err");
      setStatus("当前浏览器不支持 Web Serial", "err");
      return;
    }
    if (port) { toast("串口已连接，先断开再重选", "warn"); return; }
    if (demo) {
      toggleDemo();
      $("serial-demo").textContent = "演示数据（无硬件）";
      $("serial-demo").className = "action";
    }
    var btn = $("serial-connect");
    btn.disabled = true; btn.textContent = "选择串口中…";
    try {
      port = await navigator.serial.requestPort();
      await port.open({ baudRate: 1000000 });
      writer = port.writable.getWriter();
      setSerialState(true, "已连接 1Mbps");
      log("串口已连接，1Mbps 8N1；先「使能扭矩」再下发", "ok");
      toast("串口已连接", "ok");
      readLoop();
    } catch (e) {
      if (port) { try { await port.close(); } catch (err) {} }
      port = null; writer = null;
      setSerialState(false, "未连接");
      log("连接失败：" + e.message, "err");
      toast("连接失败：" + e.message, "err");
    } finally {
      btn.disabled = false;
      btn.textContent = port ? "重新选择串口" : "连接串口";
    }
  }

  async function disconnect() {
    reading = false;
    stopPolling();
    if (reader) { try { await reader.cancel(); } catch (e) {} }
    if (writer) { try { writer.releaseLock(); } catch (e) {} writer = null; }
    if (port) { try { await port.close(); } catch (e) { log("关闭串口：" + e.message, "warn"); } }
    port = null; reader = null;
    torqueOn = false;
    state.follow = false;
    $("serial-follow").textContent = "跟随反馈";
    $("serial-follow").className = "action";
    $("serial-torque").textContent = "使能扭矩";
    $("serial-torque").className = "action";
    setSerialState(false, "未连接");
    $("serial-connect").textContent = "连接串口";
    log("串口已断开", "ok");
    toast("串口已断开", "ok");
  }

  function onFrame(f) {
    var id = f[2], instr = f[4], params = f.slice(5, f.length - 1);
    var name = null;
    JOINTS.forEach(function (j) { if (S.ids[j[0]] === id) name = j[0]; });
    if (!name) return;

    if (instr === 0x00 && params.length >= 8) {
      var o = fb[name];
      o.pos = params[0] | (params[1] << 8);
      o.speed = (params[2] | (params[3] << 8));
      if (o.speed > 32767) o.speed -= 65536;
      o.load = (params[4] | (params[5] << 8));
      if (o.load > 32767) o.load -= 65536;
      o.volts = params[6] / 10;
      o.temp = params[7];
      o.seen = true;
      renderRow(name);
      if (recording) pushCsv(name);
      if (state.follow) {
        var deg = (o.pos - 2048) * 0.087890625;
        if (name === "yaw") { state.yaw = deg; state.playing = false; applyState(); }
        else if (name === "shoulder") { state.shoulder = deg; state.playing = false; applyState(); }
        else if (name === "elbow") { state.elbow = deg; state.playing = false; applyState(); }
      }
    } else if (instr === 0x00 && params.length >= 1) {
      // 0x41 状态位（读 1 字节时返回）
      var st = params[0];
      if (st !== fb[name].status) {
        fb[name].status = st;
        if (st) log("ID " + id + "（" + name + "）故障位 0x" + st.toString(16), "err");
        renderRow(name);
      }
    }
  }

  async function readLoop() {
    if (!port || !port.readable) return;
    reading = true;
    var rd = port.readable.getReader();
    reader = rd;
    var buf = [];
    try {
      while (reading) {
        var r = await rd.read();
        if (r.done) break;
        for (var i = 0; i < r.value.length; i++) buf.push(r.value[i]);
        while (buf.length >= 6) {
          if (buf[0] !== 0xff || buf[1] !== 0xff) { buf.shift(); continue; }
          var total = buf[3] + 4;
          if (buf.length < total) break;
          onFrame(buf.splice(0, total));
        }
      }
    } catch (e) {
      if (reading) log("读失败：" + e.message, "err");
    } finally {
      try { rd.releaseLock(); } catch (e) {}
      if (reader === rd) reader = null;
    }
  }

  function targetOf(name) {
    if (name === "gripper") return 180 - 60 * (1 - state.jaw);
    return state[name];
  }

  function renderRow(name) {
    var o = fb[name];
    if (!o.seen) return;
    var deg = (o.pos - 2048) * 0.087890625;
    var target = targetOf(name);
    var err = deg - target;
    $("t-" + name).textContent = target.toFixed(1) + "°";
    $("a-" + name).textContent = deg.toFixed(1) + "°";
    var e = $("e-" + name);
    e.textContent = err.toFixed(1) + "°";
    e.className = Math.abs(err) > 5 ? "bad" : (Math.abs(err) > 1.5 ? "warn" : "");
    var c = $("c-" + name);
    c.textContent = o.temp + "℃";
    c.className = o.temp >= 55 ? "bad" : (o.temp >= 45 ? "warn" : "");
    $("u-" + name).textContent = o.volts.toFixed(1) + "V";
    $("u-" + name).className = o.volts < 10.8 ? "warn" : "";
  }

  function poll() {
    JOINTS.forEach(function (j) {
      send(frame(S.ids[j[0]], 0x02, [REG_FB, 8]), null, true);
      send(frame(S.ids[j[0]], 0x02, [REG_STATUS, 1]), null, true);
    });
  }

  function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(poll, 250);
  }

  function stopPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
  }

  $("serial-connect").addEventListener("click", connect);
  $("serial-disconnect").addEventListener("click", disconnect);
  $("serial-torque").addEventListener("click", function () {
    guardSafety(function () { setTorque(!torqueOn); });
  });

  $("serial-estop").addEventListener("click", function () {
    if (!writer) { log("未连接：急停请直接关主电源", "err"); return; }
    JOINTS.forEach(function (j) {
      send(frame(S.ids[j[0]], 0x03, [REG_TORQUE, 0]), "卸力 ID " + S.ids[j[0]]);
    });
    torqueOn = false;
    state.follow = false;
    $("serial-follow").textContent = "跟随反馈";
    $("serial-follow").className = "action";
    $("serial-torque").textContent = "使能扭矩";
    $("serial-torque").className = "action";
    log("已全部卸力", "ok");
  });

  $("serial-follow").addEventListener("click", function () {
    if (!writer) { log("先连接串口", "err"); return; }
    state.follow = !state.follow;
    $("serial-follow").textContent = state.follow ? "停止跟随" : "跟随反馈";
    $("serial-follow").className = state.follow ? "action primary" : "action";
    if (state.follow) { startPolling(); log("跟随：每 250ms 读 0x38 + 0x41（只读）", "ok"); }
    else { stopPolling(); log("停止跟随"); }
  });

  $("serial-send").addEventListener("click", function () {
    if (!writer) { log("未连接", "err"); return; }
    guardSafety(function () {
      if (!torqueOn) {
        setTorque(true);
        log("下发前自动使能扭矩；若姿态差很多请先手动摆近", "ok");
      }
      JOINTS.forEach(function (j) {
        var name = j[0], t = ticks(targetOf(name));
        // 0x2A 起 6 字节：位置(2) + 时间(2) + 速度(2)。时间 0 = 用速度控制
        send(frame(S.ids[name], 0x03, [REG_GOAL, t & 0xff, t >> 8, 0, 0, 0xE8, 0x03]),
             null, true);
      });
      log("已下发 4 轴目标（速度 1000）", "ok");
      toast("已下发姿态", "ok");
      startPolling();
    });
  });

  function pushCsv(name) {
    var o = fb[name], deg = (o.pos - 2048) * 0.087890625;
    csv.push([Date.now(), name, S.ids[name], targetOf(name).toFixed(2), deg.toFixed(2),
              (deg - targetOf(name)).toFixed(2), o.temp, o.volts.toFixed(1),
              o.load, o.status].join(","));
  }

  $("serial-record").addEventListener("click", function () {
    if (!recording) {
      csv = ["time_ms,joint,id,target_deg,actual_deg,err_deg,temp_c,volts_v,load,status"];
      recording = true;
      $("serial-record").textContent = "停止并下载 CSV";
      $("serial-record").className = "action primary";
      log("开始记录（跟随/轮询时写入）", "ok");
      startPolling();
    } else {
      recording = false;
      $("serial-record").textContent = "开始记录 CSV";
      $("serial-record").className = "action";
      var blob = new Blob([csv.join("\n")], { type: "text/csv" });
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "modkit-debug-" + new Date().toISOString().replace(/[:.]/g, "-") + ".csv";
      a.click();
      log("已下载 " + (csv.length - 1) + " 行", "ok");
    }
  });

  // 无硬件也能验面板：合成反馈走同一条 onFrame 渲染路径
  function toggleDemo() {
    demo = !demo;
    if (demo) {
      $("serial-state").textContent = "演示数据";
      $("serial-state").className = "pill warn";
      demoTimer = setInterval(function () {
        JOINTS.forEach(function (j) {
          var name = j[0], t = targetOf(name);
          var o = fb[name];
          o.pos = ticks(t + Math.sin(Date.now() / 700 + S.ids[name]) * 0.6);
          o.volts = 11.9; o.temp = 38 + (S.ids[name] % 3);
          o.load = 30; o.status = 0; o.seen = true;
          renderRow(name);
        });
      }, 250);
      log("演示模式：数据是合成的，不要当成真机", "warn");
    } else {
      if (demoTimer) clearInterval(demoTimer);
      demoTimer = null;
      $("serial-state").textContent = "未连接";
      $("serial-state").className = "pill";
      log("退出演示模式");
    }
  }
  $("serial-demo").addEventListener("click", function () {
    if (port) { toast("先断开串口再进入演示数据", "warn"); return; }
    toggleDemo();
    $("serial-demo").textContent = demo ? "退出演示数据" : "演示数据（无硬件）";
    $("serial-demo").className = demo ? "action primary" : "action";
  });
  // 通过 ?demo 自动进入，方便截图与自测
  if (/[?&]demo/.test(location.search)) {
    toggleDemo();
    $("serial-demo").textContent = "退出演示数据";
    $("serial-demo").className = "action primary";
    switchPanel("hardware");
  }

  // ------------------------------------------------------------------ 面板 / 帮助 / 快捷键
  function switchPanel(name) {
    if (name !== "hardware") name = "model";
    var model = name === "model";
    $("tabbtn-model").setAttribute("aria-selected", String(model));
    $("tabbtn-hardware").setAttribute("aria-selected", String(!model));
    $("tabbtn-model").tabIndex = model ? 0 : -1;
    $("tabbtn-hardware").tabIndex = model ? -1 : 0;
    $("panel-model").hidden = !model;
    $("panel-hardware").hidden = model;
    try { history.replaceState(null, "", location.pathname + location.search + "#" + name); } catch (e) {}
  }
  $("tabbtn-model").addEventListener("click", function () { switchPanel("model"); });
  $("tabbtn-hardware").addEventListener("click", function () { switchPanel("hardware"); });
  [$("tabbtn-model"), $("tabbtn-hardware")].forEach(function (b) {
    b.addEventListener("keydown", function (e) {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      e.preventDefault();
      var next = this.id === "tabbtn-model" ? "hardware" : "model";
      switchPanel(next);
      $(next === "model" ? "tabbtn-model" : "tabbtn-hardware").focus();
    });
  });
  if (location.hash === "#hardware") switchPanel("hardware");
  window.addEventListener("hashchange", function () {
    switchPanel(location.hash === "#hardware" ? "hardware" : "model");
  });

  function openHelp() { $("help-dialog").showModal(); }
  function closeHelp() { $("help-dialog").close(); }
  $("help").addEventListener("click", openHelp);
  $("close-help").addEventListener("click", closeHelp);
  $("help-ok").addEventListener("click", closeHelp);

  var tip = $("tip");
  try {
    if (localStorage.getItem("modkit.tip.dismissed") === "1") tip.hidden = true;
  } catch (e) {}
  $("dismiss-tip").addEventListener("click", function () {
    tip.hidden = true;
    try { localStorage.setItem("modkit.tip.dismissed", "1"); } catch (e) {}
  });

  $("clear-log").addEventListener("click", function () { $("log").textContent = ""; });

  document.addEventListener("keydown", function (e) {
    if (document.querySelector("dialog[open]")) return;
    var tag = (e.target && e.target.tagName) || "";
    if (/^(INPUT|TEXTAREA|SELECT|BUTTON|A)$/.test(tag) || (e.target && e.target.isContentEditable)) return;
    if (e.code === "Space") {
      e.preventDefault();
      if (!e.repeat) $("play").click();
    } else if (e.code === "KeyR") {
      e.preventDefault(); $("reset").click();
    } else if (e.key === "?" || (e.key === "/" && e.shiftKey)) {
      e.preventDefault(); openHelp();
    } else if (/^Digit[1-4]$/.test(e.code)) {
      e.preventDefault();
      setView(["iso", "front", "side", "top"][Number(e.code.slice(-1)) - 1]);
    }
  });

  $("safety-dialog").addEventListener("cancel", function () {
    pendingSafety = null;
  });

  // ------------------------------------------------------------------ 渲染循环
  function resize() {
    var w = canvas.clientWidth, h = canvas.clientHeight;
    if (w === 0 || h === 0) return;
    if (renderer) renderer.setSize(w, h, false);
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
    if (renderer) renderer.render(scene, camera);
    requestAnimationFrame(loop);
  }

  // 给脚本/截图用：?autoplay 播放；?t=3.5 直接跳到某一时刻（不播放）
  var mT = location.search.match(/[?&]t=([\d.]+)/);
  if (mT) {
    state.playing = false;
    state.t = parseFloat(mT[1]);
    poseAt(state.t);
    $("play").textContent = "▶ 播放抓取动画";
    $("phase").textContent = "预览";
  } else if (/autoplay/.test(location.search)) {
    state.playing = true;
    $("play").textContent = "⏸ 暂停";
  }

  applyState();
  resize();
  if (renderer) setStatus("就绪：拖动滑杆改关节角，或点「播放抓取动画」", "ok");
  else setStatus("3D 不可用：参数面板仍可用；换浏览器或开启硬件加速", "err");
  requestAnimationFrame(loop);
})();
