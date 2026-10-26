/* 轻量 UI i18n：只翻译标注了 data-i18n 的静态控件。
 * 动态状态/错误消息仍由业务代码输出中文；不假装全站已完成本地化。 */
(function () {
  "use strict";
  var EN = {
    "doc.title": "modkit Studio · Free design & simulation",
    "doc.viewer": "modkit Viewer · Read-only 3D structure",
    "brand.sub": "Free assembly · simulation · export",
    "nav.viewer": "3D viewer",
    "nav.design": "Design",
    "nav.docs": "Components",
    "nav.github": "GitHub",
    "palette.title": "Components",
    "palette.desc": "36 ported parts · select a parent, then add",
    "palette.search": "Search ID / name / category",
    "btn.new": "New",
    "btn.import": "Import",
    "btn.restore": "Restore",
    "btn.share": "Share",
    "btn.view3d": "3D view",
    "btn.validate": "Validate",
    "btn.procure": "Download purchase CSV",
    "motion.play": "▶ Play motion",
    "motion.reset": "Reset joints",
    "motion.speed": "Speed",
    "motion.fit": "Fit view",
    "tab.build": "Build",
    "tab.check": "Check",
    "tab.bom": "BOM",
    "tab.export": "Export",
    "preset": "Preset",
    "install": "Install app",
    "install.ios": "Add to Home Screen",
    "net.offline": "Offline",
    "lang.toggle": "Switch to Chinese",
    "viewer.title": "Structure viewer",
    "viewer.fit": "Fit view",
    "viewer.copy": "Copy link",
    "viewer.edit": "Edit in Studio",
    "viewer.play": "▶ Play",
    "viewer.reset": "Reset",
    "viewer.explode": "Explode",
    "viewer.joints": "Joints / motion",
    "viewer.summary": "Checks",
    "viewer.source": "Source",
    "viewer.studio": "Open Studio",
    "viewer.demo": "M1 3D demo",
    "viewer.skip": "Skip to viewer"
  };
  var ZH = {};
  var lang = "zh";
  var KEY = "modkit.lang";

  function store() {
    try { return window.localStorage; } catch (e) { return null; }
  }
  function apply(l) {
    lang = l === "en" ? "en" : "zh";
    document.documentElement.lang = lang === "en" ? "en" : "zh-CN";
    var nodes = document.querySelectorAll("[data-i18n],[data-i18n-ph],[data-i18n-title],[data-i18n-aria]");
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i], key = el.getAttribute("data-i18n") || el.getAttribute("data-i18n-ph") ||
        el.getAttribute("data-i18n-title") || el.getAttribute("data-i18n-aria");
      if (!key) continue;
      if (!(key in ZH)) {
        ZH[key] = el.getAttribute("data-i18n-ph") ? el.getAttribute("placeholder") :
          el.getAttribute("data-i18n-title") ? el.getAttribute("title") :
            el.getAttribute("data-i18n-aria") ? el.getAttribute("aria-label") : el.textContent;
      }
      var text = lang === "en" ? (EN[key] != null ? EN[key] : ZH[key]) : ZH[key];
      if (el.hasAttribute("data-i18n-ph")) el.setAttribute("placeholder", text);
      else if (el.hasAttribute("data-i18n-title")) el.setAttribute("title", text);
      else if (el.hasAttribute("data-i18n-aria")) el.setAttribute("aria-label", text);
      else el.textContent = text;
    }
    var title = document.querySelector("[data-i18n-doc]");
    if (title) {
      var tk = title.getAttribute("data-i18n-doc");
      if (!(tk in ZH)) ZH[tk] = document.title;
      document.title = lang === "en" ? (EN[tk] || ZH[tk]) : ZH[tk];
    }
    var btn = document.getElementById("lang-toggle");
    if (btn) {
      btn.textContent = lang === "en" ? "中" : "EN";
      btn.setAttribute("aria-label", lang === "en" ? "切换到中文" : "Switch to English");
      btn.setAttribute("title", lang === "en" ? "切换到中文" : "Switch to English");
    }
    var s = store();
    if (s) { try { s.setItem(KEY, lang); } catch (e) { /* 隐私模式 */ } }
    window.dispatchEvent(new CustomEvent("modkit:lang", { detail: { lang: lang } }));
  }
  function init() {
    var s = store(), stored = null;
    try { stored = s && s.getItem(KEY); } catch (e) { stored = null; }
    var q = "";
    try { q = new URLSearchParams(location.search).get("lang") || ""; } catch (e) { q = ""; }
    lang = (q || stored || "zh").toLowerCase().indexOf("en") === 0 ? "en" : "zh";
    apply(lang);
    var btn = document.getElementById("lang-toggle");
    if (btn) btn.addEventListener("click", function () { apply(lang === "en" ? "zh" : "en"); });
  }
  window.MODKIT_I18N = { apply: apply, init: init, get lang() { return lang; }, dict: EN };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
