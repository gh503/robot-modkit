#!/usr/bin/env node
/* 浏览器冒烟：通过 Chrome DevTools Protocol 跑真实 Web 页面。
 *
 * 前置：本地静态服务器 + 带 --remote-debugging-port 的 Chrome。
 * CI 由 .github/workflows/ci.yml 的 web-smoke job 启动；本地：
 *   python3 -m http.server 8777 --directory web &
 *   google-chrome --headless=new --no-sandbox --remote-debugging-port=9222 \
 *     --use-angle=swiftshader --enable-unsafe-swiftshader about:blank &
 *   node tools/web-smoke.mjs
 */
import fs from "node:fs";

const PORT = process.env.MODKIT_CDP_PORT || "9222";
const BASE = (process.env.MODKIT_WEB_BASE || "http://127.0.0.1:8777").replace(/\/$/, "");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

class CDP {
  constructor(url) {
    this.url = url;
    this.id = 0;
    this.pending = new Map();
    this.errors = [];
    this.ws = null;
  }
  async open() {
    this.ws = new WebSocket(this.url);
    await new Promise((resolve, reject) => {
      this.ws.addEventListener("open", resolve, { once: true });
      this.ws.addEventListener("error", () => reject(new Error("CDP WebSocket 连接失败")), { once: true });
    });
    this.ws.addEventListener("message", (ev) => {
      let msg;
      try { msg = JSON.parse(String(ev.data)); } catch { return; }
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        msg.error ? reject(new Error(msg.error.message || JSON.stringify(msg.error))) : resolve(msg.result);
      } else if (msg.method === "Runtime.exceptionThrown") {
        const d = msg.params.exceptionDetails || {};
        this.errors.push((d.exception && d.exception.description) || d.text || "unknown page exception");
      } else if (msg.method === "Runtime.consoleAPICalled" && msg.params.type === "error") {
        this.errors.push(msg.params.args.map((a) => a.value || a.description || "").join(" "));
      }
    });
  }
  send(method, params = {}) {
    if (!this.ws || this.ws.readyState !== 1) throw new Error("CDP 未连接");
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
      setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id);
          reject(new Error("CDP 超时：" + method));
        }
      }, 15000);
    });
  }
  async eval(expression) {
    const r = await this.send("Runtime.evaluate", {
      expression, returnByValue: true, awaitPromise: true, userGesture: true
    });
    if (r.exceptionDetails) {
      const d = r.exceptionDetails;
      throw new Error("页面脚本异常：" + ((d.exception && d.exception.description) || d.text));
    }
    return r.result.value;
  }
  async navigate(url) {
    await this.send("Page.navigate", { url });
    await waitFor(async () => (await this.eval("document.readyState")) === "complete", 12000, "页面加载 " + url);
    await sleep(450);
  }
  close() { try { this.ws.close(); } catch { /* ignore */ } }
}

async function target() {
  for (let i = 0; i < 40; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const page = list.find((t) => t.type === "page");
      if (page && page.webSocketDebuggerUrl) return page;
    } catch { /* Chrome 还没起来 */ }
    await sleep(250);
  }
  throw new Error(`连不上 Chrome CDP 127.0.0.1:${PORT}`);
}

async function waitFor(fn, timeout, label) {
  const start = Date.now();
  let last;
  while (Date.now() - start < timeout) {
    try {
      const v = await fn();
      if (v) return v;
      last = v;
    } catch (e) { last = e.message; }
    await sleep(100);
  }
  throw new Error(`等待超时：${label}（最后值 ${JSON.stringify(last)}）`);
}
function check(cond, msg) { if (!cond) throw new Error(msg); }

let cdp;
let failures = 0;
async function run(name, fn) {
  process.stdout.write(`- ${name} ... `);
  try {
    await fn();
    process.stdout.write("ok\n");
  } catch (e) {
    failures++;
    process.stdout.write("FAIL\n  " + (e.stack || e.message) + "\n");
  }
}

async function main() {
  const t = await target();
  cdp = new CDP(t.webSocketDebuggerUrl);
  await cdp.open();
  await cdp.send("Page.enable");
  await cdp.send("Runtime.enable");
  await cdp.send("Network.enable");
  await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });

  await run("Studio 打开且 7 个预设", async () => {
    await cdp.navigate(`${BASE}/design.html?smoke=1`);
    await waitFor(() => cdp.eval("!!window.MODKIT_STUDIO && !!window.MODKIT_ASSEMBLIES"), 8000, "Studio 初始化");
    const presets = await cdp.eval("Object.keys(window.MODKIT_ASSEMBLIES).sort()");
    check(presets.length === 7, `预设数 ${presets.length} != 7`);
    const options = await cdp.eval('document.querySelectorAll("#preset option").length');
    check(options >= 7, `预设下拉只有 ${options} 项`);
  });

  await run("逐个预设求解", async () => {
    const presets = await cdp.eval("Object.keys(window.MODKIT_ASSEMBLIES)");
    for (const name of presets) {
      await cdp.eval(`MODKIT_STUDIO.loadPreset(${JSON.stringify(name)})`);
      await sleep(140);
      const r = await cdp.eval(`(() => {
        const s = MODKIT_STUDIO.state.report;
        return { name: MODKIT_STUDIO.state.assembly.name, n: s.instances.length, cost: s.totalCost,
                 mass: s.totalMass, off: s.instances.filter(i => i.offboard).length,
                 errors: s.issues.filter(i => i.level === "error").length };
      })()`);
      check(r.n > 0, `${name}: 0 个实例`);
      check(r.cost > 0, `${name}: BOM 成本为 0`);
      check(r.errors === 0, `${name}: ${r.errors} 个错误`);
      if (name === "sensor_tower") check(r.off > 0, "sensor_tower 应有 offboard 电源");
    }
  });

  await run("3D 选中/复制粘贴/拖拽导入", async () => {
    await cdp.eval('MODKIT_STUDIO.loadPreset("m1")');
    await sleep(200);
    await cdp.eval('MODKIT_STUDIO.select("buck");');
    await sleep(120);
    const hi = await cdp.eval('({ sel: !!MODKIT_STUDIO.view.selectedHelper, groups: Object.keys(MODKIT_STUDIO.view.instanceGroups).length })');
    check(hi.sel, "选中后没有 3D 包围盒");
    check(hi.groups === 18, `3D 组 ${hi.groups} != 18`);
    await cdp.eval('MODKIT_STUDIO.state.assembly.payload_g = 1000; MODKIT_STUDIO.revalidate();');
    await waitFor(async () => (await cdp.eval("MODKIT_STUDIO.view.issueHelpers.length")) > 0, 3000, "问题实例高亮");
    check(await cdp.eval("MODKIT_STUDIO.state.report.issues.some(i => i.level === 'error' && i.instance === 'gripper')"), "没有 gripper 载荷错误");
    await cdp.eval('MODKIT_STUDIO.state.assembly.payload_g = 0; MODKIT_STUDIO.revalidate();');
    await cdp.eval('MODKIT_STUDIO.copySelected()');
    check(await cdp.eval('MODKIT_STUDIO.state.clipboard.rootId') === "buck", "复制根不是 buck");
    await cdp.eval('MODKIT_STUDIO.select("chassis"); MODKIT_STUDIO.pasteClipboard();');
    await waitFor(async () => (await cdp.eval("MODKIT_STUDIO.state.report.instances.length")) === 19, 3000, "粘贴后 19 个实例");
    check((await cdp.eval("MODKIT_STUDIO.state.report.issues.filter(i => i.level === 'error').length")) === 0, "粘贴后出现错误");
    await cdp.eval("MODKIT_STUDIO.undo()");
    await waitFor(async () => (await cdp.eval("MODKIT_STUDIO.state.report.instances.length")) === 18, 3000, "撤销回 18 个实例");

    const raw = await cdp.eval("JSON.stringify(MODKIT_ASSEMBLIES.m1)");
    const lit = JSON.stringify(raw);
    await cdp.eval(`(() => {
      const dt = new DataTransfer();
      dt.items.add(new File([${lit}], "m1.json", { type: "application/json" }));
      window.dispatchEvent(new DragEvent("drop", { dataTransfer: dt, bubbles: true, cancelable: true }));
    })()`);
    await waitFor(async () => (await cdp.eval('document.querySelector("#toast").textContent')).includes("已导入装配"), 3000, "拖拽导入提示");
    check((await cdp.eval("MODKIT_STUDIO.state.report.instances.length")) === 18, "拖拽导入后不是 18 个实例");
  });

  await run("导出 GLB/3MF/打印页", async () => {
    const r = await cdp.eval(`(() => {
      const glb = MODKIT_STUDIO.buildGLB();
      const gu = new Uint8Array(glb);
      const mf = MODKIT_STUDIO.build3MF();
      const html = MODKIT_STUDIO.buildPrintHTML();
      return {
        glbLen: glb.byteLength, glbMagic: String.fromCharCode(...gu.slice(0, 4)),
        glbVer: new DataView(glb).getUint32(4, true),
        mfLen: mf.length, mfMagic: Array.from(mf.slice(0, 4)),
        htmlLen: html.length, hasBom: html.includes("BOM"), hasTotal: html.includes("TOTAL")
      };
    })()`);
    check(r.glbMagic === "glTF" && r.glbVer === 2, "GLB 头不对");
    check(r.glbLen > 50000, `GLB 太小 ${r.glbLen}`);
    check(r.mfMagic.join(",") === "80,75,3,4", "3MF 不是 ZIP");
    check(r.mfLen > 50000, `3MF 太小 ${r.mfLen}`);
    check(r.htmlLen > 1000 && r.hasBom && r.hasTotal, "打印页缺 BOM/TOTAL");
  });

  await run("项目/版本/schema 迁移", async () => {
    const r = await cdp.eval(`(() => {
      MODKIT_STUDIO.saveProject();
      const p = MODKIT_STUDIO.workspace().projects.find(x => x.id === MODKIT_STUDIO.state.projectId);
      const before = MODKIT_STUDIO.state.assembly.name;
      window.prompt = () => "smoke-v1";
      MODKIT_STUDIO.snapshotVersion();
      MODKIT_STUDIO.state.assembly.name = "smoke-change";
      MODKIT_STUDIO.revalidate();
      document.querySelector("#version-select").value = "0";
      MODKIT_STUDIO.restoreVersion();
      const old = MODKIT_STUDIO.migrateAssembly({
        budget: 900, payload: 55,
        components: [{ id: "root", type: "frame.chassis_160" }]
      });
      return {
        projects: MODKIT_STUDIO.workspace().projects.length,
        versions: p.versions.length,
        restored: MODKIT_STUDIO.state.assembly.name,
        before, oldSchema: old.schema_version, oldBudget: old.budget_cny,
        oldPayload: old.payload_g, oldAt: old.components[0].at, oldSpin: old.components[0].spin
      };
    })()`);
    check(r.projects >= 1, "项目没有保存");
    check(r.versions >= 1, "版本没有保存");
    check(r.restored === r.before, `版本恢复 ${r.restored} != ${r.before}`);
    check(r.oldSchema === 2 && r.oldBudget === 900 && r.oldPayload === 55, "schema 迁移字段不对");
    check(Array.isArray(r.oldAt) && r.oldSpin === 0, "schema 迁移组件默认值不对");
  });

  await run("Pareto/约束规划", async () => {
    const r = await cdp.eval(`(() => {
      const B = window.MODKIT_BUDGET, m = window.MODKIT_ASSEMBLIES.m1;
      const cs = B.suggest(m, { includeMass: true });
      const drop = cs.find(c => c.id === "drop-elbow");
      const frame = cs.find(c => c.id === "swap-frame.chassis_240-frame.chassis_160");
      const p = B.plan(m, 1000, 6, { constraints: { minJoints: 4 } });
      const bad = B.plan(m, 1000, 6, { constraints: { maxMass: 1500 } });
      document.querySelector("#c-min-joints").value = "4";
      document.querySelector("#optimize").click();
      const cards = document.querySelectorAll("#optimizer .opt-card").length;
      document.querySelector("#plan-budget").click();
      return {
        dropPareto: drop.pareto, framePareto: frame.pareto,
        frameDominated: frame.dominatedBy.includes("drop-elbow"),
        plan: { feasible: p.feasible, reached: p.reached, cost: p.cost,
                steps: p.steps.map(x => x.id), violations: p.violations },
        bad: { feasible: bad.feasible, base: bad.baseViolations },
        cards, planShown: !!document.querySelector("#plan .plan-card")
      };
    })()`);
    check(r.dropPareto === true && r.framePareto === false, "Pareto 标记不对");
    check(r.frameDominated, "支配关系缺失");
    check(r.plan.feasible === true && r.plan.reached === false, "约束规划状态不对");
    check(!r.plan.steps.includes("drop-elbow"), "minJoints=4 仍去掉了肘关节");
    check(r.plan.cost > 1100, `约束规划成本不对 ${r.plan.cost}`);
    check(r.bad.feasible === false && r.bad.base.length > 0, "不可行约束没有报违反");
    check(r.cards >= 1 && r.planShown, "约束 UI 没有渲染");
  });

  await run("网格碰撞/关节力矩", async () => {
    const r = await cdp.eval(`(() => {
      const A = window.MODKIT_ASSEMBLY, m = window.MODKIT_ASSEMBLIES.m1;
      const rep = A.validate(m);
      const box = [0, 0, 0, 10, 10, 10];
      return {
        hit: A.meshHit(A.identity(), box, A.identity(), [5, 5, 5, 15, 15, 15]),
        miss: A.meshHit(A.identity(), box, A.identity(), [11, 0, 0, 21, 10, 10]),
        contained: A.meshHit(A.identity(), box, A.identity(), [2, 2, 2, 8, 8, 8]),
        loads: rep.jointLoads.map(j => ({ name: j.name, load: j.load, gravity: j.gravity,
          dynamic: j.dynamic, ratio: j.ratio, ok: j.ok })),
        stats: rep.collisionStats, mesh: rep.collisionMesh,
        rows: document.querySelectorAll("#torque tbody tr").length
      };
    })()`);
    check(r.hit === true && r.miss === false && r.contained === true, "三角面网格相交不对");
    check(r.loads.length === 3 && r.loads.every(j => j.load > 0 && j.ok), "关节力矩缺失/超限");
    check(r.loads.every(j => Math.abs(j.load - j.gravity - j.dynamic) < 1e-6), "力矩分项对不上");
    check(r.rows === 3, `力矩表行数 ${r.rows}`);
    check(r.stats && typeof r.stats.meshTests === "number", "碰撞统计缺失");
  });

  await run("Studio 生成查看器链接", async () => {
    await cdp.eval('MODKIT_STUDIO.loadPreset("m1")');
    await sleep(200);
    const info = await cdp.eval(`(() => {
      const u = MODKIT_STUDIO.viewerURL();
      return { len: u.length, hash: u.includes("#d="), http: u.startsWith("http") };
    })()`);
    check(info.http && info.hash, "viewerURL 不是 http#d=");
    check(info.len < 60000, "viewerURL 超过 60000 字符");
  });

  const viewerUrl = await cdp.eval("MODKIT_STUDIO.viewerURL()");
  await run("查看器渲染 + 关节/爆炸", async () => {
    await cdp.navigate(viewerUrl);
    await waitFor(() => cdp.eval("!!window.MODKIT_VIEW && !!MODKIT_VIEW.state.renderer"), 8000, "查看器初始化");
    const r = await cdp.eval(`(() => ({
      title: document.querySelector("#view-title").textContent,
      status: document.querySelector("#view-status").textContent,
      groups: Object.keys(MODKIT_VIEW.state.groups).length,
      tris: MODKIT_VIEW.state.renderer.info.render.triangles,
      sliders: document.querySelectorAll("#view-joints input").length,
      wheels: MODKIT_VIEW.state.wheelVisuals.length,
      grip: MODKIT_VIEW.state.gripperVisuals.length
    }))()`);
    check(r.groups === 18, `查看器 ${r.groups} 个组 != 18`);
    check(r.tris > 500, `三角形 ${r.tris} 太少`);
    check(r.sliders === 4, `关节滑杆 ${r.sliders} != 4`);
    check(r.wheels === 2, `驱动轮 ${r.wheels} != 2`);
    check(r.grip === 1, "夹爪几何缺失");
    await cdp.eval('document.querySelector("#view-explode").click()');
    await sleep(180);
    check(await cdp.eval("MODKIT_VIEW.state.exploded"), "爆炸视图未开启");
    await cdp.eval('document.querySelector("#view-explode").click()');
    await cdp.eval('document.querySelector("#view-play").click()');
    await sleep(500);
    check(await cdp.eval("MODKIT_VIEW.state.playing"), "播放未启动");
    const spun = await cdp.eval("MODKIT_VIEW.state.wheelVisuals.some(w => Math.abs(w.wheel.rotation.y) > 0.05)");
    check(spun, "驱动轮没有转");
    await cdp.eval('document.querySelector("#view-play").click()');
    await cdp.eval('document.querySelector("#view-reset").click()');
    check(!(await cdp.eval("MODKIT_VIEW.state.playing")), "复位后仍在播放");
  });

  await run("index.html#d= 重定向", async () => {
    const old = viewerUrl.replace("/view.html", "/index.html");
    await cdp.navigate(old);
    await sleep(600);
    check((await cdp.eval("location.pathname")).endsWith("/view.html"), "没有跳到 view.html");
    check((await cdp.eval("!!window.MODKIT_VIEW")), "重定向后查看器未初始化");
  });

  await run("无效分享链接有明确错误", async () => {
    await cdp.navigate(`${BASE}/view.html?smoke=bad#d=bad`);
    const s = await cdp.eval('document.querySelector("#view-status").textContent');
    check(s.includes("无法显示"), `状态是 ${s}`);
  });

  await run("移动/无障碍/i18n", async () => {
    await cdp.navigate(`${BASE}/design.html?lang=zh&smoke=i18n`);
    const r = await cdp.eval(`(() => {
      const btn = document.getElementById("lang-toggle");
      const before = document.documentElement.lang;
      btn.click();
      const en = {
        lang: document.documentElement.lang, nav: document.querySelector('[data-i18n="nav.design"]').textContent,
        play: document.getElementById("play").textContent,
        ph: document.getElementById("search").placeholder,
        title: document.title, skip: !!document.querySelector(".skip")
      };
      btn.click();
      return {
        before: before, en: en, zh: document.documentElement.lang,
        navZh: document.querySelector('[data-i18n="nav.design"]').textContent,
        tagged: document.querySelectorAll("[data-i18n],[data-i18n-ph]").length,
        pwa: !!window.MODKIT_PWA, install: !!document.getElementById("pwa-install"),
        reduce: matchMedia("(prefers-reduced-motion: reduce)").matches
      };
    })()`);
    check(r.before === "zh-CN" && r.en.lang === "en", "语言切换失败");
    check(r.en.nav === "Design" && r.en.play === "▶ Play motion", "英文控件未翻译");
    check(r.en.ph.indexOf("Search") === 0, "搜索占位未翻译");
    check(r.zh === "zh-CN" && r.navZh === "自由设计", "切回中文失败");
    check(r.tagged >= 20, `i18n 标注仅 ${r.tagged} 个`);
    check(r.pwa && r.install, "PWA 安装接口/按钮缺失");
    check(typeof r.reduce === "boolean", "减少动态媒体查询不可用");
  });

  await run("PWA 壳已注册", async () => {
    await cdp.navigate(`${BASE}/design.html?smoke=pwa`);
    const info = await cdp.eval(`(async () => {
      const r = await navigator.serviceWorker.ready;
      await r.update();
      let hit = null;
      for (let i = 0; i < 50; i++) {
        hit = await caches.match("models/frame_chassis_160.step");
        if (hit) break;
        await new Promise((x) => setTimeout(x, 200));
      }
      for (let i = 0; i < 50; i++) {
        if (r.active && r.active.state === "activated") break;
        await new Promise((x) => setTimeout(x, 200));
      }
      return { state: r.active && r.active.state, keys: await caches.keys(), step: !!hit };
    })()`);
    const manifest = await cdp.eval(`fetch("manifest.webmanifest").then((r) => r.json())`);
    check(info.state === "activated", `SW 状态 ${info.state}`);
    check(info.keys.some((k) => k.startsWith("modkit-shell-")), "没有 modkit-shell 缓存");
    check(info.step, "STEP 未预缓存，离线导出会失败");
    check(manifest.icons.length >= 3 && manifest.icons.some((i) => i.sizes === "192x192"), "PWA 图标不完整");
    check((await cdp.eval("!!window.MODKIT_PWA && typeof MODKIT_PWA.isStandalone() === 'boolean'")), "PWA 安装状态接口缺失");
  });

  await run("全页面无脚本异常", async () => {
    check(cdp.errors.length === 0, "页面异常：\n" + cdp.errors.join("\n"));
  });

  try {
    await cdp.send("Page.captureScreenshot", { format: "png" });
  } catch { /* ignore */ }

  cdp.close();
  if (failures) {
    console.error(`\nweb smoke: ${failures} 项失败`);
    process.exit(1);
  }
  console.log("\nweb smoke: PASS（13 项）");
}

main().catch((e) => {
  console.error("web smoke 崩溃：", e.stack || e.message);
  if (cdp) cdp.close();
  process.exit(1);
});
