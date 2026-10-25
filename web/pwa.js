/* 注册离线壳；失败时不影响页面本身。 */
(function () {
  "use strict";
  if (!("serviceWorker" in navigator)) return;
  window.addEventListener("load", function () {
    navigator.serviceWorker.register("sw.js").catch(function () { /* file:// 或隐私模式 */ });
  });
})();
