/* 注册离线壳、安装提示、离线状态；失败不影响页面本身。 */
(function () {
  "use strict";
  var deferred = null;
  var btn = null;

  function isStandalone() {
    return (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) ||
      window.navigator.standalone === true;
  }
  function t(key, fallback) {
    var i = window.MODKIT_I18N;
    return i && i.lang === "en" && i.dict && i.dict[key] ? i.dict[key] : fallback;
  }
  function label() {
    if (!btn) return;
    if (isStandalone()) { btn.hidden = true; return; }
    var ios = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
    if (deferred) {
      btn.hidden = false;
      btn.textContent = t("install", "安装应用");
      btn.removeAttribute("aria-disabled");
    } else if (ios) {
      btn.hidden = false;
      btn.textContent = t("install.ios", "添加到主屏");
    } else {
      btn.hidden = true;
    }
  }
  function online() {
    var el = document.getElementById("net-status");
    if (!el) return;
    el.hidden = navigator.onLine !== false;
    el.textContent = t("net.offline", "离线");
  }
  function init() {
    btn = document.getElementById("pwa-install");
    if (btn) {
      btn.addEventListener("click", function () {
        if (deferred) {
          deferred.prompt();
          deferred.userChoice.then(function () { deferred = null; label(); });
        } else if (/iPad|iPhone|iPod/.test(navigator.userAgent)) {
          btn.title = "Safari 分享菜单 → 添加到主屏幕";
          btn.textContent = "分享 → 添加到主屏";
        }
      });
    }
    window.addEventListener("beforeinstallprompt", function (e) {
      e.preventDefault();
      deferred = e;
      label();
    });
    window.addEventListener("appinstalled", function () {
      deferred = null;
      label();
      var el = document.getElementById("net-status");
      if (el) { el.hidden = false; el.textContent = "已安装"; setTimeout(online, 2500); }
    });
    window.addEventListener("online", online);
    window.addEventListener("offline", online);
    window.addEventListener("modkit:lang", function () { label(); online(); });
    label();
    online();
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("sw.js").catch(function () { /* file:// 或隐私模式 */ });
    }
  }
  window.MODKIT_PWA = { installable: function () { return !!deferred; }, isStandalone: isStandalone };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
