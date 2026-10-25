/* MODKIT Studio 离线壳。
 *
 * 策略：
 * - 导航请求 network-first，离线回退到缓存的 design.html / index.html；
 * - 静态资源 stale-while-revalidate，离线直接用缓存；
 * - 只缓存同源 GET；不缓存 POST/跨域。
 * 版本号只用于激活时清理旧壳；更新后第一次在线访问会刷新。
 */
"use strict";
var CACHE = "modkit-shell-v1.13.0";
var SHELL = [
  "./", "./index.html", "./design.html", "./design.css", "./designer.js",
  "./assembly-core.js", "./budget-core.js", "./pwa.js", "./manifest.webmanifest",
  "./favicon.svg", "./scene.js", "./viewer.js",
  "./data/components.js", "./data/assemblies.js",
  "./vendor/three.min.js", "./vendor/OrbitControls.js"
];

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(CACHE).then(function (cache) {
      return cache.addAll(SHELL);
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
      fetch(req).then(function (res) {
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
