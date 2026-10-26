# 75 · 移动端、无障碍、i18n 与 PWA 安装

> 状态：**v1.24.0 已实现**。目标不是“像原生 App”，而是让手机可用、
> 键盘/读屏可用、可安装、离线可开。

## 75.1 移动端

- 断点：`≤980px` Studio 从三栏变纵向；`≤560px` 工具栏换行、状态胶囊隐藏、
  触控目标 `≥36px`（`pointer:coarse`）。
- 查看器 `≤860px` 从左右分栏变上下：3D 在上、摘要在下。
- 3D 画布 `touch-action:none`，触摸拖动交给 OrbitControls，不劫持页面滚动。
- 390×844（iPhone 12/13 逻辑尺寸）实测：`scrollWidth 375 < innerWidth 390`，
  无横向溢出；Studio `flex-direction:column`；查看器单列。
- 手机仍不建议做重装配：组件库/树/表单会纵向很长；查看、校验、分享链接是主场景。

## 75.2 无障碍

- **跳转链接**：Studio 和查看器都有 `.skip`，键盘第一个 Tab 可见。
- **焦点**：全局 `:focus-visible` 2px 蓝色轮廓；禁用态按钮不参与点击。
- **标签页**：`role=tablist` + 左右方向键/Home/End，`aria-selected` 与 `tabindex` 同步。
- **状态播报**：`#top-state`、`#view-status`、`#toast`、`#net-status` 有
  `role=status` / `aria-live=polite`。
- **减少动态**：`prefers-reduced-motion: reduce` 时 CSS 动画/过渡近乎关闭；
  播放按钮会拒绝启动并提示改用滑杆逐帧。这是主动禁用，不是“假装支持”。
- 画布有 `role=img` + `aria-label`；3D 内容本身仍无法被读屏完整理解，
  右侧组件数/BOM/校验摘要是文本替代。

## 75.3 i18n（核心控件）

- `web/i18n.js`：`data-i18n`（文本）、`data-i18n-ph`（placeholder）、
  `data-i18n-doc`（标题）；`?lang=en` 或右上角 `EN/中` 切换，存
  `localStorage.modkit.lang`。
- 已翻译：导航、组件库、预设/新建/导入/分享/3D 查看/校验、播放/复位/速度/适配、
  四个标签页、查看器的适配/复制/编辑/播放/复位/爆炸/摘要/来源。
- 动态消息（校验错误、toast、BOM 细节、项目名）仍是中文；这是**部分 i18n**，
  不宣称全站英文可用。
- 语言切换会派发 `modkit:lang`，PWA 安装按钮和播放按钮据此更新标签。

## 75.4 PWA 安装

- `manifest.webmanifest`：`standalone`、`scope ./`、`start_url design.html`，
  192/512 PNG + maskable 512。
- `pwa.js` 捕获 `beforeinstallprompt`，显示“安装应用”；点击调用
  `prompt()`；`appinstalled` 后隐藏。iOS Safari 没有该事件，显示
  “添加到主屏”并提示分享菜单路径。
- `display-mode: standalone` 时隐藏安装按钮，避免重复提示。
- 离线：`online/offline` 事件显示/隐藏“离线”胶囊；Service Worker 仍缓存
  壳 + 36 个 STEP。
- 安装提示是否出现由浏览器决定（需要 HTTPS/localhost、SW 控制、参与度）；
  页面只提供入口，不伪造“已安装”。

## 75.5 测试

- 静态：`i18n.js`/`pwa.js` 存在，关键 `data-i18n` 标注，图标文件存在，
  manifest 含 192/512，CSS 含 `prefers-reduced-motion` / `pointer:coarse`，
  查看器有 skip/main。
- 浏览器“移动/无障碍/i18n”组：切 EN 后导航/播放/placeholder/标题变化，
  切回中文；标注 ≥20；`MODKIT_PWA` 与安装按钮存在。
- PWA 组：SW activated、壳缓存、STEP 预缓存、manifest 图标 ≥3。
- 总计 **302 项** pytest；`make web-smoke` **14 组**。

## 75.6 边界

- 没有做完整英文翻译、RTL、读屏逐页人工走查、真实手机 Safari/Firefox 回归。
- 没有做 PWA 安装成功率统计；headless Chrome 不弹安装提示。
- 没有原生推送/后台同步；离线只保证壳和 STEP，不保证所有动态资源。
- 物理闸门仍 **0/5**；UI 可用不等于硬件可用。

## 75.7 版本

- **v1.23.0**：移动断点/触控目标、skip/focus/reduced-motion、核心 i18n、
  PWA 安装提示/图标/离线状态；测试 302；smoke 14 组。
