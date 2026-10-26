/* MODKIT Studio 离线壳。
 *
 * 策略：
 * - 导航/脚本/样式 network-first，离线回退到缓存；
 * - 图片/模型等静态资源 stale-while-revalidate，离线直接用缓存；
 * - 只缓存同源 GET；不缓存 POST/跨域。
 * 脚本必须 network-first：否则发布后第一次刷新会先拿旧 JS，功能像“没生效”。
 * 版本号只用于激活时清理旧壳；更新后第一次在线访问会刷新。
 */
"use strict";
var CACHE = "modkit-shell-v1.33.0";
var SHELL = [
  "./", "./index.html", "./design.html", "./design.css", "./designer.js",
  "./assembly-core.js", "./assembly-view.js", "./budget-core.js", "./i18n.js", "./pwa.js", "./manifest.webmanifest",
  "./view.html", "./world.html", "./world.css", "./world.js",
  "./favicon.svg", "./icons/icon-192.png", "./icons/icon-512.png",
  "./icons/icon-maskable-512.png", "./scene.js", "./viewer.js",
  "./data/components.js", "./data/assemblies.js", "./data/fluids.json",
  "./data/world-pool.json", "./data/world-lab.json", "./data/world-kitchen.json",
  "./data/world-greenhouse.json", "./data/world-pipeline.json", "./data/world-factory.json",
  "./data/world-outdoor.json", "./data/world-aquarium.json",
  "./data/world-room.json", "./data/room-demo.obj",
  "./vendor/three.min.js", "./vendor/OrbitControls.js"
];
// 36 个单件 STEP 共约 2.7MB：预缓存后离线也能导出全部零件。
var MODELS = [
  "./models/adapter_disc_grid.step",
  "./models/adapter_grid_disc.step",
  "./models/compute_pi4.step",
  "./models/drive_caster.step",
  "./models/drive_wheel_65.step",
  "./models/drive_wheel_80.step",
  "./models/electronics_buck_5v.step",
  "./models/electronics_esp32.step",
  "./models/electronics_power_dist.step",
  "./models/frame_chassis_160.step",
  "./models/frame_chassis_240.step",
  "./models/frame_deck_120x80.step",
  "./models/frame_deck_160x100.step",
  "./models/frame_mast_100.step",
  "./models/frame_mast_200.step",
  "./models/frame_power_bay.step",
  "./models/joint_continuous.step",
  "./models/joint_elbow.step",
  "./models/joint_generic.step",
  "./models/joint_pitch.step",
  "./models/joint_yaw.step",
  "./models/link_beam_100.step",
  "./models/link_beam_140.step",
  "./models/link_beam_200.step",
  "./models/link_beam_60.step",
  "./models/power_adapter_12v5a.step",
  "./models/power_battery_3s.step",
  "./models/power_estop.step",
  "./models/sensor_camera_usb.step",
  "./models/sensor_imu.step",
  "./models/sensor_line_array.step",
  "./models/sensor_tof.step",
  "./models/tool_gripper_40.step",
  "./models/tool_gripper_70.step",
  "./models/tool_pen.step",
  "./models/tool_vacuum_20.step"
];

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(CACHE).then(function (cache) {
      return cache.addAll(SHELL.concat(MODELS));
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (k) { return k !== CACHE; })
        .map(function (k) { return caches.delete(k); }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function (event) {
  var req = event.request;
  if (req.method !== "GET") return;
  var url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req, { cache: "no-cache" }).then(function (res) {
        var copy = res.clone();
        caches.open(CACHE).then(function (c) { c.put(req, copy); });
        return res;
      }).catch(function () {
        return caches.match(req).then(function (hit) {
          return hit || caches.match("./design.html") || caches.match("./index.html");
        });
      })
    );
    return;
  }

  var code = req.destination === "script" || req.destination === "style" || req.destination === "worker";
  if (code) {
    event.respondWith(
      fetch(req, { cache: "no-cache" }).then(function (res) {
        if (res.ok) {
          var copy = res.clone();
          caches.open(CACHE).then(function (c) { c.put(req, copy); });
        }
        return res;
      }).catch(function () { return caches.match(req); })
    );
    return;
  }

  event.respondWith(
    caches.match(req).then(function (hit) {
      var network = fetch(req).then(function (res) {
        if (res.ok) {
          var copy = res.clone();
          caches.open(CACHE).then(function (c) { c.put(req, copy); });
        }
        return res;
      }).catch(function () { return hit; });
      return hit || network;
    })
  );
});
