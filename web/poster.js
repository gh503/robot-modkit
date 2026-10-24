/* 静态高质量渲染（给文档/README 出图），与 index.html 共用 scene.js 的尺寸。
 *
 * 参数：
 *   view=iso|front|side|top|hero   相机
 *   w=1600&h=1200                  输出尺寸
 *   t=3.6                          动画时刻（秒）
 *   explode=0..1                   爆炸图
 *   grid=0|1                       地面网格
 *   bg=studio|white|dark           背景
 *
 * 为什么单独写一个：查看器要交互、要滑杆、要串口面板，不适合出图；
 * 这里只做"给定姿态 → 一张干净的图"，好截图、好复现。
 */
(function () {
  "use strict";

  var S = window.MODKIT_SCENE;
  var P = S.params;
  var q = new URLSearchParams(location.search);
  var num = function (k, d) { var v = parseFloat(q.get(k)); return isNaN(v) ? d : v; };

  var W = num("w", 1600), H = num("h", 1200);
  var VIEW = q.get("view") || "iso";
  var T = q.get("t") === null ? 0 : num("t", 0);
  var EXPLODE = num("explode", 0);
  var SHOW_GRID = q.get("grid") !== "0";
  var BG = q.get("bg") || "studio";

  var canvas = document.getElementById("c");
  var renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(1);
  renderer.setSize(W, H, true);   // 同时设置 CSS 尺寸，避免截图时被缩放
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  // 不用 ACES / sRGB 输出：r128 没有颜色管理，套上会把中间调整体冲白
  renderer.toneMapping = THREE.NoToneMapping;

  var scene = new THREE.Scene();
  var camera = new THREE.PerspectiveCamera(34, W / H, 1, 8000);
  camera.up.set(0, 0, 1);

  // ---------------------------------------------------------------- 灯光
  scene.add(new THREE.HemisphereLight(0xe8f0fa, 0xa8b3c1, 0.55));

  var key = new THREE.DirectionalLight(0xfff6ec, 1.05);
  key.position.set(320, -520, 620);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  key.shadow.camera.near = 50;
  key.shadow.camera.far = 2200;
  key.shadow.camera.left = -420;
  key.shadow.camera.right = 420;
  key.shadow.camera.top = 420;
  key.shadow.camera.bottom = -420;
  key.shadow.bias = -0.0008;
  key.shadow.radius = 3;
  scene.add(key);

  var fill = new THREE.DirectionalLight(0xdce8f7, 0.3);
  fill.position.set(-420, -180, 260);
  scene.add(fill);

  var rim = new THREE.DirectionalLight(0xffffff, 0.38);
  rim.position.set(-180, 520, 380);
  scene.add(rim);

  // ---------------------------------------------------------------- 材质
  function mat(color, rough, metal) {
    return new THREE.MeshStandardMaterial({
      color: color,
      roughness: rough === undefined ? 0.75 : rough,
      metalness: metal === undefined ? 0.0 : metal
    });
  }
  var M = {
    print: mat(0xdfe5ee, 0.82),        // 打印件
    printAccent: mat(0xe8ebf1, 0.8),
    link: mat(0x3f6f9f, 0.52, 0.12),   // 铝合金连杆
    joint: mat(0x2b333b, 0.45, 0.35),
    wheel: mat(0x24282d, 0.95),
    hub: mat(0xb9c2cc, 0.35, 0.55),
    bracket: mat(0xc4483f, 0.62, 0.08),
    gripper: mat(0x3f8f4f, 0.7),
    wrist: mat(0xd97a1a, 0.55, 0.1),
    servo: mat(0x9aa3ad, 0.4, 0.5),
    cam: mat(0x7a5b8f, 0.6),
    block: mat(0xd9534f, 0.8),
    metal: mat(0xc9d1da, 0.3, 0.7)
  };

  function add(geo, material, parent, opts) {
    var m = new THREE.Mesh(geo, material);
    m.castShadow = true;
    m.receiveShadow = true;
    if (opts && opts.pos) m.position.set(opts.pos[0], opts.pos[1], opts.pos[2]);
    if (opts && opts.rot) m.rotation.set(opts.rot[0], opts.rot[1], opts.rot[2]);
    if (opts && opts.explode) m.userData.explode = opts.explode;
    // 细描边：让浅色打印件在浅背景上也能看清轮廓（技术插画的感觉）
    if (!opts || opts.edges !== false) {
      var eg = new THREE.EdgesGeometry(m.geometry, 26);
      var line = new THREE.LineSegments(eg, new THREE.LineBasicMaterial({
        color: 0x2b3742, transparent: true, opacity: 0.15
      }));
      m.add(line);
    }
    parent.add(m);
    return m;
  }
  function box(w, d, h) { return new THREE.BoxGeometry(w, d, h); }
  function cyl(r, h, seg) { return new THREE.CylinderGeometry(r, r, h, seg || 36); }

  var robot = new THREE.Group();
  scene.add(robot);
  var parts = [];

  // 底盘（左右两块 + 接缝）
  var chassisL = add(box(P.chassisX / 2 - 1, P.chassisY, P.chassisT), M.print, robot,
    { pos: [-P.chassisX / 4 - 0.5, 0, -P.chassisT / 2], explode: [-40, 0, 0] });
  var chassisR = add(box(P.chassisX / 2 - 1, P.chassisY, P.chassisT), M.print, robot,
    { pos: [P.chassisX / 4 + 0.5, 0, -P.chassisT / 2], explode: [40, 0, 0] });
  parts.push(chassisL, chassisR);

  var joiner = add(box(58, P.chassisY * 0.55, P.chassisT), M.printAccent, robot,
    { pos: [0, 0, -P.chassisT / 2 - 0.2], explode: [0, 0, -70] });
  parts.push(joiner);

  // 轮组
  [-1, 1].forEach(function (s) {
    var wheel = add(cyl(P.wheelR, P.wheelW, 40), M.wheel, robot,
      { pos: [0, s * P.wheelY, P.servoZ], rot: [0, 0, Math.PI / 2], explode: [0, s * 90, 0] });
    var hub = add(cyl(P.wheelR * 0.36, P.wheelW + 2, 32), M.hub, robot,
      { pos: [0, s * P.wheelY, P.servoZ], rot: [0, 0, Math.PI / 2], explode: [0, s * 130, 0] });
    var tyreRing = add(new THREE.TorusGeometry(P.wheelR - 4, 4.5, 12, 48), M.joint, robot,
      { pos: [0, s * P.wheelY, P.servoZ], rot: [0, Math.PI / 2, 0], explode: [0, s * 70, 0] });
    var servo = add(box(46, 25, 36), M.servo, robot,
      { pos: [0, s * P.driveY, P.servoZ], explode: [0, s * 55, 0] });
    var bracket = add(box(60, 44, 5), M.bracket, robot,
      { pos: [0, s * P.driveY, -2.5], explode: [0, s * 40, -20] });
    parts.push(wheel, hub, tyreRing, servo, bracket);
  });

  // 相机
  var camBody = add(box(30, 30, 22), M.cam, robot, { pos: [P.camX, P.camY, 12], explode: [-70, 40, 20] });
  var lens = add(cyl(7, 8, 28), M.joint, robot,
    { pos: [P.camX + 12, P.camY, 12], rot: [0, 0, Math.PI / 2], explode: [-90, 40, 20] });
  parts.push(camBody, lens);

  // 底座立柱
  var yawGroup = new THREE.Group();
  yawGroup.position.set(P.armX, 0, 0);
  robot.add(yawGroup);

  var column = add(cyl(P.columnR, P.baseH, 40), M.link, yawGroup,
    { pos: [0, 0, P.baseH / 2], rot: [Math.PI / 2, 0, 0], explode: [0, 0, 0] });
  var baseDisc = add(cyl(30, 6, 48), M.metal, yawGroup,
    { pos: [0, 0, 3], rot: [Math.PI / 2, 0, 0], explode: [0, 0, -30] });
  parts.push(column, baseDisc);

  // 肩
  var shoulderGroup = new THREE.Group();
  shoulderGroup.position.z = P.baseH;
  yawGroup.add(shoulderGroup);

  var shoulderBlock = add(box(46, 34, 34), M.print, shoulderGroup,
    { pos: [0, 0, 0], explode: [0, 0, 0] });
  var shoulderJoint = add(cyl(15, 32, 36), M.joint, shoulderGroup,
    { pos: [0, 0, 0], rot: [Math.PI / 2, 0, 0], explode: [0, 0, 0] });
  var upperArm = add(box(P.l1 - 12, P.linkW, P.linkT), M.link, shoulderGroup,
    { pos: [(P.l1 - 12) / 2 + 6, 0, 0], explode: [30, 0, 0] });
  var upperRib = add(box(P.l1 - 40, P.linkW * 0.45, 4), M.printAccent, shoulderGroup,
    { pos: [(P.l1 - 40) / 2 + 20, 0, -P.linkT / 2 - 2], explode: [30, 0, -25] });
  parts.push(shoulderBlock, shoulderJoint, upperArm, upperRib);

  // 肘
  var elbowGroup = new THREE.Group();
  elbowGroup.position.x = P.l1;
  shoulderGroup.add(elbowGroup);
  var elbowBlock = add(box(38, 30, 30), M.print, elbowGroup, {});
  var elbowJoint = add(cyl(14, 28, 32), M.joint, elbowGroup,
    { pos: [0, 0, 0], rot: [Math.PI / 2, 0, 0] });
  var forearm = add(box(P.l2 - 10, P.linkW - 4, P.linkT - 2), M.link, elbowGroup,
    { pos: [(P.l2 - 10) / 2 + 5, 0, 0], explode: [40, 0, 0] });
  parts.push(elbowBlock, elbowJoint, forearm);

  // 腕 + 夹爪
  var wristGroup = new THREE.Group();
  wristGroup.position.x = P.l2;
  elbowGroup.add(wristGroup);
  var wristBase = add(box(34, 44, 14), M.wrist, wristGroup, {});
  var jawA = add(box(P.gripperLen, P.jawT, 46), M.gripper, wristGroup,
    { pos: [P.gripperLen / 2, 0, 0], explode: [0, 30, 0] });
  var jawB = add(box(P.gripperLen, P.jawT, 46), M.gripper, wristGroup,
    { pos: [P.gripperLen / 2, 0, 0], explode: [0, -30, 0] });
  parts.push(wristBase, jawA, jawB);

  // 地面（接影）
  var ground = new THREE.Mesh(
    new THREE.CircleGeometry(620, 64),
    new THREE.ShadowMaterial({ color: 0x1b2733, opacity: 0.16 })
  );
  ground.receiveShadow = true;
  ground.position.z = -P.wheelR + P.wheelR;   // 轮底 = 0
  ground.position.z = P.servoZ - P.wheelR;
  scene.add(ground);

  var grid = null;
  if (SHOW_GRID) {
    grid = new THREE.GridHelper(1200, 24, 0xcfd8e3, 0xe3e9f1);
    grid.rotation.x = Math.PI / 2;
    grid.position.z = P.servoZ - P.wheelR + 0.15;
    grid.material.transparent = true;
    grid.material.opacity = 0.5;
    scene.add(grid);
  }

  // 方块（抓取目标），抬起后跟手
  var blockMesh = add(box(40, 40, 40), M.block, scene, { pos: [200, 0, 20] });
  blockMesh.castShadow = true;

  // ---------------------------------------------------------------- 姿态
  var KF = S.keyframes;
  var SEG = 1.25;
  function poseAt(t) {
    var f = t / SEG;
    var i = Math.max(0, Math.min(KF.length - 2, Math.floor(f)));
    var u = Math.min(1, Math.max(0, f - i));
    u = u * u * (3 - 2 * u);
    var a = KF[i], b = KF[i + 1];
    return {
      yaw: a.yaw + (b.yaw - a.yaw) * u,
      shoulder: a.shoulder + (b.shoulder - a.shoulder) * u,
      elbow: a.elbow + (b.elbow - a.elbow) * u,
      jaw: a.jaw + (b.jaw - a.jaw) * u
    };
  }

  function apply(st) {
    yawGroup.rotation.z = THREE.MathUtils.degToRad(st.yaw);
    shoulderGroup.rotation.y = -THREE.MathUtils.degToRad(st.shoulder);
    elbowGroup.rotation.y = -THREE.MathUtils.degToRad(st.elbow);
    var gap = P.jawOpen * st.jaw + P.jawClosed * (1 - st.jaw);
    jawA.position.y = gap / 2 + P.jawT / 2;
    jawB.position.y = -(gap / 2 + P.jawT / 2);
  }

  function applyExplode(k) {
    parts.forEach(function (m) {
      var e = m.userData.explode || [0, 0, 0];
      if (!m.userData.home) m.userData.home = m.position.clone();
      m.position.set(m.userData.home.x + e[0] * k,
                     m.userData.home.y + e[1] * k,
                     m.userData.home.z + e[2] * k);
    });
  }

  // 夹住的方块跟随指尖
  function carry(st) {
    var held = T > SEG * 3.2 && T < SEG * 6.9;
    if (!held) { blockMesh.position.set(200, 0, 20); return; }
    var tip = new THREE.Vector3(P.gripperLen, 0, 0);
    wristGroup.localToWorld(tip);
    blockMesh.position.copy(tip);
  }

  apply(poseAt(T));
  applyExplode(EXPLODE);
  robot.updateMatrixWorld(true);
  carry(poseAt(T));

  // ---------------------------------------------------------------- 相机
  // 自动取景：按整机包围盒算距离，避免"图里一个角、大片留白"
  var box = new THREE.Box3().setFromObject(robot);
  var center = box.getCenter(new THREE.Vector3());
  var size = box.getSize(new THREE.Vector3());
  var radius = 0.5 * size.length();

  var DIRS = {
    iso: new THREE.Vector3(0.62, -0.86, 0.52),
    hero: new THREE.Vector3(0.5, -0.78, 0.4),
    front: new THREE.Vector3(1, 0, 0.16),
    side: new THREE.Vector3(0, -1, 0.14),
    top: new THREE.Vector3(0.06, 0, 1),
    explode: new THREE.Vector3(0.66, -0.9, 0.55)
  };
  var dir = (DIRS[VIEW] || DIRS.iso).clone().normalize();
  var margin = VIEW === "explode" ? 1.34 : 1.18;
  // 迭代取景：按"真实顶点投影"收敛，而不是包围盒的 8 个角
  //（机械臂是 L 形，包围盒的角离实体很远，用角会把画面撑空）
  var verts = [];
  robot.updateMatrixWorld(true);
  robot.traverse(function (o) {
    if (!o.isMesh) return;
    var pos = o.geometry.attributes.position;
    var step = Math.max(1, Math.floor(pos.count / 60));
    for (var i = 0; i < pos.count; i += step) {
      verts.push(new THREE.Vector3().fromBufferAttribute(pos, i).applyMatrix4(o.matrixWorld));
    }
  });

  function silhouette() {
    var x0 = 9, x1 = -9, y0 = 9, y1 = -9;
    for (var i = 0; i < verts.length; ++i) {
      var p = verts[i].clone().project(camera);
      if (p.x < x0) x0 = p.x;
      if (p.x > x1) x1 = p.x;
      if (p.y < y0) y0 = p.y;
      if (p.y > y1) y1 = p.y;
    }
    return { x0: x0, x1: x1, y0: y0, y1: y1 };
  }

  var fill = 0.84;
  var dist = radius / Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * margin;
  for (var it = 0; it < 6; ++it) {
    camera.position.copy(center).addScaledVector(dir, dist);
    camera.lookAt(center);
    camera.updateMatrixWorld(true);
    var bb = silhouette();
    var frac = Math.max(Math.abs(bb.x0), Math.abs(bb.x1), Math.abs(bb.y0), Math.abs(bb.y1));
    dist *= frac / fill;
  }
  // 水平/垂直居中：按投影中心偏移量挪 target，避免"人偏在右边"
  for (var c2 = 0; c2 < 2; ++c2) {
    var bb2 = silhouette();
    var visH = 2 * dist * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
    var right = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0);
    var up = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 1);
    center.addScaledVector(right, (bb2.x0 + bb2.x1) / 2 * visH * camera.aspect / 2);
    center.addScaledVector(up, (bb2.y0 + bb2.y1) / 2 * visH / 2);
    camera.position.copy(center).addScaledVector(dir, dist);
    camera.lookAt(center);
    camera.updateMatrixWorld(true);
    var bb3 = silhouette();
    var f3 = Math.max(Math.abs(bb3.x0), Math.abs(bb3.x1), Math.abs(bb3.y0), Math.abs(bb3.y1));
    dist *= f3 / fill;
  }
  camera.position.copy(center).addScaledVector(dir, dist);
  camera.lookAt(center);
  camera.near = Math.max(1, dist - radius * 3);
  camera.far = dist + radius * 6;
  camera.updateProjectionMatrix();

  // 背景：用 CSS 画，渲染器透明，阴影仍在地面
  document.body.className = "bg-" + BG;

  renderer.render(scene, camera);

  // 截图脚本靠这个标记判断"画完了"
  document.getElementById("ready").textContent = "1";
})();
