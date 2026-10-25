# modkit M1 · 可拆装模块化机器人

[![CI](https://github.com/gh503/robot-modkit/actions/workflows/ci.yml/badge.svg)](https://github.com/gh503/robot-modkit/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/gh503/robot-modkit)](https://github.com/gh503/robot-modkit/releases)
[![Live](https://img.shields.io/badge/live-3D%20viewer-4c78a8)](https://gh503.github.io/robot-modkit/)
[![Studio](https://img.shields.io/badge/live-Studio-2f80c9)](https://gh503.github.io/robot-modkit/design.html)

> 一台"接口先定、形态后长"的机器人：**差速底盘 + 4 自由度臂 + 夹爪**，
> 目标不是演示视频，而是**能独立完成物理任务**（导航到指定位置 → 识别目标 → 抓取 → 放到另一处）。
>
> v1.5 起，底盘/关节/连杆/夹爪/传感器是**有端口和数据的组件**：换构型不改代码，
> 用 JSON 拼装后生成 BOM、功率、重心和 `safety.json`。见
> [docs/65-组件库与自由组装.md](docs/65-组件库与自由组装.md)。
>
> v1.6 新增 [网页设计器](https://gh503.github.io/robot-modkit/design.html)：
> 在浏览器里加件/换件/删件、拖关节、播放运动学、导出 JSON/BOM/STL/SVG/STEP。
> v1.7 加了**预算模式**和 ¥968 的 `m1_budget` 两关节定点抓放方案。
> 见 [docs/67-网页设计器.md](docs/67-网页设计器.md)。
>
> 面向新手：从零基础到能自己改图纸、改固件、加传感器，手册在 [docs/07-小白操作手册.md](docs/07-小白操作手册.md)。

![关节模块装配预览](docs/images/assembly.png)

**在线看：<https://gh503.github.io/robot-modkit/>**；**自由设计：<https://gh503.github.io/robot-modkit/design.html>**。
查看器里拖动滑杆改关节角、播放抓取动画，
也可以直接连总线舵机（Chrome/Edge 的 Web Serial）。v1.4 在界面上加了**运动预检与
fail-closed 联锁**：温度/电压/故障/限位/单步/几何包络任一不过，拒绝下发；标定文件可覆盖
零位/方向/限位。物理闸门仍是 0/5，界面通过不等于实物通过。

[![实时查看器](docs/images/viewer.png)](https://gh503.github.io/robot-modkit/)

![整机](docs/images/hero.png)

## 它现在到了哪一步

| 层 | 状态 | 证据 |
|---|---|---|
| 机械：关节模块（M0） | ✅ 可用 | 5 个零件、33 项几何自检（干涉/间隙/壁厚/水密） |
| 机械：底盘 + 夹爪 + 相机架（M1） | ✅ 出图 | 新增 7 个零件，几何自检 **85 项全 PASS**（含校准件/工装） |
| 生产：可制造性 + 工程图 + 成本 | ✅ 可用 | 13 页 A4 图纸；方向/悬垂/壁厚/时长；三档成本 ¥1392/¥1808 |
| 生产：设计校核（力矩/刚度/强度/公差/驱动） | ✅ 可用 | 肩余量 2.8×、连杆 100g 挠度 0.60mm、最弱强度 9.2× |
| 生产：工装 + 质检 + 批次 | ✅ 可用 | 三件套夹具；Q1/Q2/Q3 判据；`modkit qc` 序列号与良率 |
| 生产：工序卡 + 打印参数 + 线束 | ✅ 可用 | 17 道工序/7.0h（与 BOM 对账）；逐件壁数/填充；14 根线束裁线表 |
| 生产：公差与精度 | ✅ 有量化 | 装配良率 99.98%；开环末端 p95 6.24mm → 回差补偿目标 3.5mm |
| 生产：检验/追溯/包装 | ✅ 可用 | 27 件逐件检验表；20 条需求追溯（16 已验证）；箱规与跌落判据 |
| 固件：总线协议 + 驱动 + 底盘闭环 + 低压保护 | ✅ 可用 | **77 项** C++ 单测 + **5 个在环场景**（119 断言） |
| 固件：ESP32 平台层 | 🟡 编译通过 | esp32s3 交叉编译 OK；⚠️ 未上真实硬件 |
| 上位机：协议/运动学/仿真/CLI | ✅ 可用 | **268 项** pytest（IK/标定/自检/里程计/回差/导航/视觉/日志/仿真/质检/台架/安全预检/组件装配/网页设计器）；无硬件可跑全流程 |
| 仿真：三维视图 + **数字孪生** | ✅ 可用 | 16 个硬件场景全过 + 浏览器工作台（`modkit simui`） |
| 打印校准件 + 四张拼盘 + 工装 | ✅ 可用 | `print_gauge`、`plate_01..04.stl`（27 件）、jigs 三件套 |
| 自主任务（导航+视觉+抓取） | 🟡 软件链通 | `mission` 仿真 16.4s；真机未跑 |
| 整机实测 | ⬜ 硬件阻塞 | 0/5 个物理闸门；顺序见 [docs/42](docs/42-完成度审计.md) |
| 数字孪生验收 | ✅ 采购前目标达成 | 17 条逐项对照见 [docs/45](docs/45-数字孪生验收.md) |
| **v1.0 ready-to-build** | ✅ 软件/设计侧完成 | 声明与边界见 [docs/52](docs/52-v1.0完成声明.md) |
| **v1.1 五项增强** | ✅ 已验收 | 畸变/手眼、接触动态、3D、排板、编辑器；见 [docs/58](docs/58-v1.1验收.md) |
| **v1.2 交付硬化** | ✅ 已验收 | bring-up 证据、协议异常流、发布校验和；见 [docs/60](docs/60-v1.2验收.md) |
| **v1.3 产品级 UI** | ✅ 已验收 | 工作台/查看器重做、键盘与安全确认、移动端；见 [docs/61](docs/61-v1.3-UI优化.md) |
| **v1.4 预硬件安全** | ✅ 离线验收 | 软限位/单步/温度/电压/故障联锁、几何+路径包络、`preflight`、到货执行单；物理仍 0/5；见 [docs/64](docs/64-v1.4-预硬件验收.md) |
| **v1.5 组件库** | ✅ 离线验收 | 36 个组件 + 6 个装配示例；BOM/功率/重心/静载/安全配置；`components`/`assemble`；物理仍 0/5；见 [docs/66](docs/66-v1.5验收.md) |
| **v1.6 网页设计器** | ✅ 离线验收 | 浏览器加/换/删件、关节滑杆/运动学播放、参数编辑、JSON/BOM/STL/SVG/STEP 导出；物理仍 0/5；见 [docs/67](docs/67-网页设计器.md) |
| **v1.7 预算模式** | ✅ 离线验收 | 设计预算字段/余量提示；`m1_budget` 15 组件/¥968/两关节定点抓放；物理仍 0/5；见 [docs/67](docs/67-网页设计器.md) |

> 这张表是**唯一可信的状态声明**。任何"应该能行"都不写进来。

## 可视化 / 仿真

| 想做什么 | 怎么做 |
|---|---|
| 网页里实时转、实时摆姿态 | 打开 <https://gh503.github.io/robot-modkit/>（或本地 `cd web && python3 -m http.server`） |
| **网页里自由装配/换件/仿真** | 打开 <https://gh503.github.io/robot-modkit/design.html>；见 [docs/67](docs/67-网页设计器.md) |
| 生成高质量四视图 / 爆炸图 | `make -C sim shots`（需本机有 Chrome） |
| 抓取动画 GIF | `make -C sim grasp` 或 `make -C sim shots` |
| 底盘闭环仿真 | `make -C sim drive` |
| **硬件仿真**（舵机/电池/丢帧） | `modkit simrun --all sim/scenarios` |
| **交互式仿真工作台** | `modkit simui --open`，浏览器里拖滑杆/注故障 |
| **抓取摩擦锥** | `modkit simrun --scenario sim/scenarios/slippery_cube.json` |
| **蒙特卡洛 / 参数辨识** | `modkit simsweep ...` / `modkit identify --log telemetry.csv` |
| **车载相机手眼** | `modkit simrun --scenario sim/scenarios/mission_onboard.json` |
| **工作台验收** | 逐条证据见 [docs/50](docs/50-仿真工作台验收.md) |
| **相机畸变/手眼标定** | `modkit simrun --scenario sim/scenarios/mission_distortion.json`；见 [docs/53](docs/53-相机畸变与手眼标定.md) |
| **接触滑动/六维力** | `modkit simrun --scenario sim/scenarios/fast_transport.json`；见 [docs/54](docs/54-接触动力学与六维力.md) |
| **3D 实时 / 场景编辑** | `modkit simui`，四宫格 3D + JSON 编辑器；见 [docs/56](docs/56-工作台3D实时视图.md)、[57](docs/57-场景编辑器与回归基线.md) |
| **回归基线** | `modkit simdiff --baseline ... --current ...` |
| **硬件 bring-up** | `modkit --port ... bringup --action check`（只读）；11 步证据见 [docs/59](docs/59-硬件bringup记录.md) |
| **运动预检/联锁** | `modkit --sim preflight` 或 `modkit --port ... preflight --write-limits`；见 [docs/63](docs/63-硬件到货执行单.md) |
| **离线姿态包络** | `modkit envelope --x 100 --y 0 --z 120`；桌面/底座/折叠越界返回 2 |
| **物理约束台账** | 逐项覆盖与缺口见 [docs/62](docs/62-物理约束台账.md) |
| **自由拼机器人（网页）** | 打开 [Studio](https://gh503.github.io/robot-modkit/design.html)；左侧点组件、右侧改参数、导出 JSON/STL/STEP；见 [docs/67](docs/67-网页设计器.md) |
| **自由拼机器人（CLI）** | `modkit components` 看库；`modkit assemble plan assemblies/m1.json --out out/`；见 [docs/65](docs/65-组件库与自由组装.md) |
| **组件 CAD 批导出** | `make components-cad` → `cad/out/components/`（36 个 STEP/STL + manifest） |
| 仿真调试图 | `modkit simplot --scenario sim/scenarios/nav_square.json --out sq.png` |
| 相机仿真 | `modkit camsim --out cube.png --cube 200,0,40 --detect` |
| 打印前先验证打印机精度 | 打 `cad/out/print_gauge.stl`（`build.py` 顺带导出），流程见 [docs/13](docs/13-业界实践对照.md) |
| 拼打印板 | `cd cad && python plate.py --copies 1` → `plate_01..04.stl`；批量见 [docs/55](docs/55-按数量排板.md) |

## 三分钟上手（不需要任何硬件）

```bash
git clone https://github.com/gh503/robot-modkit.git && cd robot-modkit
python3 -m venv .venv && ./.venv/bin/pip install -e software
make doctor                                          # 环境自检
make check-fast                                      # 268 项测试 + 16 场景 + 7 个装配示例
./.venv/bin/python -m modkit.cli --sim scan          # 扫描仿真舵机
./.venv/bin/python -m modkit.cli --sim pose --x 150 --y 0 --z 150   # 逆解到点
./.venv/bin/python -m modkit.cli --sim demo          # 逐关节摆动
```

看整机长什么样、动作顺不顺（不需要硬件）：

```bash
make -C sim views    # 四视图 + 尺寸图 + 工作空间
make -C sim grasp    # 抓取动画 GIF
make -C sim drive    # 底盘闭环仿真（打印判据）
```

看图纸、跑自检：

```bash
cd cad && ../.venv/bin/python build.py     # 生成 STEP/STL + 33 项几何断言
../.venv/bin/python render.py              # 出三视图预览
```

跑测试（ROS 环境下的 pytest 插件会互相打架，见下方"已知坑"）：

```bash
cd software && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ../.venv/bin/python -m pytest
cd firmware && make test
```

## 目录

```
docs/     00 计划 · 01 系统设计 · 02 接口 · 03 配电 · 04 BOM · 11 零件清单 · 12 仿真
          05 装配 · 06 调试测试 · 07 小白手册 · 08 学习路径 · 09 故障排查 · 10 决策
cad/      params.py（唯一尺寸源）· parts.py（M0）· parts_m1.py（整机）· build.py · render.py
sim/      model.py（可动模型）· draw.py（多视图）· anim_grasp.py（动画）· drive.py（闭环仿真）
firmware/ src/（协议+驱动，可脱离硬件测试）· esp32/（平台层）· test/（假总线）
software/ modkit/（协议/运动学/仿真/CLI）· tests/
```

## 设计主张（为什么长这样）

1. **接口先于形态**：全机一个 20mm M3 网格、一种螺钉、一条三线总线。换构型改的是"用哪几块板"。
2. **免测量优先**：舵机靠浅槽+压盖固定，不依赖官方未公布的安装孔坐标。
3. **间隙是设计值**：旋转件与固定件 0.6mm、舵机与盖板 0.4mm，由脚本断言而非试装。
4. **每层可独立验证**：CAD 有几何断言、协议有字节断言、运动学有数值断言、平台层可仿真。硬件坏了，软件照样能测。

## 已知坑（踩过，记下来）

- ROS 2 Humble 的 `launch_testing` 会被 pytest 自动加载并因缺 `pyyaml` 报错 → 用 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`。
- 本机 `~/Documents/infra-dev` 是另一个项目（Jarvis），故本项目独立在 `~/Documents/robot-modkit`，独立 git 仓库。
- 机械臂逆解的肩角符号写反过一次，被 `test_forward_ik_roundtrip` 抓住 —— 所以那条测试必须保留。

## 参与

- 想改东西：先看 [CONTRIBUTING.md](CONTRIBUTING.md)（五条必跑命令 + 六条硬规则）
- 想提问题：用 [issue 模板](.github/ISSUE_TEMPLATE/)
- **要有尺寸的图纸**：[13 页工程图](docs/drawings/modkit-m1-drawings.pdf)（A4 可直接打印）
- **要真的造出来**：[docs/15-生产链路总览](docs/15-生产链路总览.md)（八个环节 + 每环门禁）
- **要评估风险/改版**：[FMEA](docs/22-FMEA与风险.md) · [版本与兼容矩阵](docs/23-版本与兼容.md)
- **要开工前自查**：[28-生产就绪检查](docs/28-生产就绪检查.md)（G0–G8 放行清单）
- **要小批量做**：[docs/21-批量生产](docs/21-批量生产.md)（序列号/烧录/抽检/包装）
- **要算成本/排产**：[docs/17-成本模型](docs/17-成本模型.md)（五档 × 1/5/20 台）
- **要下单**：[docs/51-下单清单](docs/51-下单清单.md)（含预算差额/货期/链接）
- **要打件**：[docs/16-可制造性报告](docs/16-可制造性报告.md)（方向/悬垂/壁厚/时长）
- 文档怎么找：[docs/README.md](docs/README.md)（按角色 + 按类型两张表）
- 想了解"为什么这么做"：[docs/13-业界实践对照](docs/13-业界实践对照.md) 把 SO-ARM100、OSHWA、
  Diátaxis、REP-103 逐项对照过，并列出还欠什么

## 版本

当前 **v1.7.0**：在网页设计器上增加**预算模式**——可编辑 `budget_cny`、实时显示
预算余量/超支，并新增 **¥968** 的 `m1_budget` 两关节定点抓放方案（240 底盘、
偏航+肩、固定上臂、40mm 夹爪）。完整 M1 仍是 ¥1127，超出 ¥1000；预算版是
有意识的裁剪，不是三关节通用臂。实物未采购/未装配，物理闸门 **0/5**。边界见
[docs/52](docs/52-v1.0完成声明.md)、[58](docs/58-v1.1验收.md)、[60](docs/60-v1.2验收.md)、
[61](docs/61-v1.3-UI优化.md)、[64](docs/64-v1.4-预硬件验收.md)、
[66](docs/66-v1.5验收.md)、[67](docs/67-网页设计器.md)，逐项约束见 [docs/62](docs/62-物理约束台账.md)，
完整变更见 [CHANGELOG.md](CHANGELOG.md)。

## 许可

MIT（代码、CAD、文档统一）。为什么暂不改 CERN-OHL：见 [D17](docs/10-决策记录.md)。


MIT，见 [LICENSE](LICENSE)。硬件图纸同样 MIT，商用注明出处即可。