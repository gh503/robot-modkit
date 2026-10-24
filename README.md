# modkit M1 · 可拆装模块化机器人

[![CI](https://github.com/gh503/robot-modkit/actions/workflows/ci.yml/badge.svg)](https://github.com/gh503/robot-modkit/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> 一台"接口先定、形态后长"的机器人：**差速底盘 + 4 自由度臂 + 夹爪**，
> 目标不是演示视频，而是**能独立完成物理任务**（导航到指定位置 → 识别目标 → 抓取 → 放到另一处）。
>
> 面向新手：从零基础到能自己改图纸、改固件、加传感器，手册在 [docs/07-小白操作手册.md](docs/07-小白操作手册.md)。

![关节模块装配预览](docs/images/assembly.png)

## 它现在到了哪一步

| 层 | 状态 | 证据 |
|---|---|---|
| 机械：关节模块（M0） | ✅ 可用 | 5 个零件、33 项几何自检（干涉/间隙/壁厚/水密） |
| 机械：底盘 + 夹爪 + 相机架（M1） | ✅ 出图 | 新增 7 个零件，几何自检 **76 项全 PASS** |
| 固件：总线协议 + 驱动 + 底盘闭环 | ✅ 可用 | **65 项** C++ 测试（协议 41 + 底盘 24） |
| 固件：ESP32 平台层 | 🟡 编译通过 | esp32s3 交叉编译 OK；⚠️ 未上真实硬件 |
| 上位机：协议/运动学/仿真/CLI | ✅ 可用 | 23 项 pytest；无硬件可跑全流程 |
| 自主任务（导航+视觉+抓取） | ⬜ 未开始 | 路线图 M3–M5 |
| 整机实测 | ⬜ 未开始 | 等你的打印机和舵机 |

> 这张表是**唯一可信的状态声明**。任何"应该能行"都不写进来。

## 三分钟上手（不需要任何硬件）

```bash
git clone https://github.com/gh503/robot-modkit.git && cd robot-modkit
python3 -m venv .venv && ./.venv/bin/pip install -e software
./.venv/bin/python -m modkit.cli --sim scan          # 扫描仿真舵机
./.venv/bin/python -m modkit.cli --sim pose --x 150 --y 0 --z 150   # 逆解到点
./.venv/bin/python -m modkit.cli --sim demo          # 逐关节摆动
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
docs/     00 计划 · 01 系统设计 · 02 接口 · 03 配电 · 04 BOM · 11 零件清单
          05 装配 · 06 调试测试 · 07 小白手册 · 08 学习路径 · 09 故障排查 · 10 决策
cad/      params.py（唯一尺寸源）· parts.py（M0）· parts_m1.py（整机）· build.py · render.py
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

## 许可

MIT，见 [LICENSE](LICENSE)。硬件图纸同样 MIT，商用注明出处即可。