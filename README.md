# modkit M1 · 可拆装模块化机器人 + 流体/3D 世界仿真

[![CI](https://github.com/gh503/robot-modkit/actions/workflows/ci.yml/badge.svg)](https://github.com/gh503/robot-modkit/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/gh503/robot-modkit)](https://github.com/gh503/robot-modkit/releases)
[![Live](https://img.shields.io/badge/live-3D%20viewer-4c78a8)](https://gh503.github.io/robot-modkit/)
[![Studio](https://img.shields.io/badge/live-Studio-2f80c9)](https://gh503.github.io/robot-modkit/design.html)

> **一台接口先定、形态后长的机器人**：差速底盘 + 4 自由度臂 + 夹爪，目标不是演示视频，
> 而是能完成真实物理任务。组件有端口和数据，换构型只改 JSON；软件侧可在没有硬件时
> 跑通装配、运动学、安全、绘图、硬件准备包和阶段 bring-up。
>
> 当前正在扩展**流体材料 + 三维虚拟世界 + 可复现实验环境**，面向泳池/管道/灌溉/
> 水下服务机器人等商业场景。物理闸门仍是 **0/5**：没有采购、打印、装配、上电和标定。

**在线看**：<https://gh503.github.io/robot-modkit/> · **自由设计**：<https://gh503.github.io/robot-modkit/design.html>  
**状态与完整版本历史**：[docs/80](docs/80-项目状态与版本历史.md)（唯一可信状态表）

![整机](docs/images/hero.png)

## 现在能做什么

| 能力 | 入口 | 状态 |
|---|---|---|
| 装配/换件/预算/导出 | [Studio](https://gh503.github.io/robot-modkit/design.html) 或 `modkit assemble` | ✅ 离线可用 |
| 运动学/安全/绘图 | `modkit pose`、`draw`、`preflight` | ✅ 离线可用 |
| 阶段硬件包 | `modkit assemble pack` | ✅ 生成 bring-up/接线/装配/打印/采购/验收/固件配置 |
| 阶段 bring-up 记录 | `modkit stage` | ✅ 证据 + sha256；不伪造实测 |
| 流体材料/工程计算 | `modkit fluid` | ✅ 15 种材料 + 工程公式；见 [81](docs/81-流体材料与工程计算.md) |
| 3D 世界/环境 | `modkit world` + [world.html](https://gh503.github.io/robot-modkit/world.html) | ✅ 9 预设 + 多边形/heightfield + 编辑；见 [82](docs/82-三维世界与环境.md) |
| 稳态管网 | `modkit network solve` | ✅ 节点/管/泵/需求；见 [85](docs/85-稳态管网.md) |
| 本地 API | `modkit serve` + `/docs` | ✅ 世界异步 job/管网/流体；见 [86](docs/86-本地API与部署.md) |
| glTF 导出 | `modkit world export` | ✅ glTF/GLB：盒/柱/球/平面/heightfield/水面 |
| AquaTwin | [ventures/aquatwin](ventures/aquatwin/README.md) | ✅ 0.2.2：实测导入/校准/批量/报价/PDF/模型审计；现场仍 0/5 |
| 整机实测 | 按 [docs/63](docs/63-硬件到货执行单.md) 执行 | ⬜ 0/5，硬件阻塞 |

完整能力地图（仿真、生产、采购、验收）见 [docs/80 §80.2](docs/80-项目状态与版本历史.md)。

## 三分钟上手

```bash
git clone https://github.com/gh503/robot-modkit.git && cd robot-modkit
python3 -m venv .venv && ./.venv/bin/pip install -e software
make doctor
make check-fast          # 364 项测试 + 16 组网页冒烟 + 11 装配示例 + AquaTwin 32 项
make bench               # 世界/管网轻量基准（时间/体积误差）
make web-smoke           # 需本机 Chrome
```

不接硬件跑一遍：

```bash
./.venv/bin/python -m modkit.cli --sim scan
./.venv/bin/python -m modkit.cli --sim pose --x 150 --y 0 --z 150
./.venv/bin/python -m modkit.cli draw --shape square --z 150 --play --sim
./.venv/bin/python -m modkit.cli world export --preset pool --format glb --out out/pool.glb
```

生成某一阶段的完整硬件包：

```bash
cd software
../.venv/bin/python -m modkit.cli assemble pack ../assemblies/bench_joint.json \
  --out ../out/pack-bench-joint
```

## 独立应用：AquaTwin

从本项目孵化、但**独立运行**的商业 MVP：[`ventures/aquatwin`](ventures/aquatwin/README.md)
把泳池清洗的“覆盖/工时/能耗/过滤/成本/回收期”算成一份可解释报告，
面向泳池服务商、机器人 OEM、商业/酒店泳池。

```bash
cd ventures/aquatwin && python3 -m venv .venv && . .venv/bin/activate
pip install -e .
aquatwin study --scenario scenarios/residential_8x4.json --out out/residential
# 有实测：measurements → calibrate → study --calibration
aquatwin calibrate --scenario scenarios/residential_8x4.json \
  --measurements data/measurements-example.csv --out out/calibration
aquatwin pdf --scenario scenarios/residential_8x4.json --out out/quote --what quote
```

它不是 modkit 的包依赖；商业场景/定价/研究/验证见
[docs/84](docs/84-应用孵化AquaTwin.md)。没有现场数据，报告只作方案比较。

## 边界（先看这一段）

- **物理闸门 0/5**：设计/仿真通过 ≠ 实物通过；没有实测证据不写“已验证”。
- 价格是 2026-10 估算，不是供应商报价；线束是逻辑检查表，不是按长度下料图。
- `m1_pen` 是 2DOF 固定上臂，只能画圆弧；3DOF `bench_arm` 才能画方框。
- 流体/世界模型是**工程级降阶模型**，不是认证 CFD；用于方案比较、控制/任务调试和
  数字孪生交互，不替代水池试验、安规和第三方认证。
- 所有“物理结论”必须回到 [docs/62 物理约束台账](docs/62-物理约束台账.md) 和实测记录。

## 目录

```
docs/       设计与验收文档；80 是状态/版本/使用地图
cad/        params.py（唯一尺寸源）· 零件/整机/出图
sim/        可动模型、多视图、抓取/底盘仿真
firmware/   总线协议/驱动 + ESP32 平台层
software/   modkit Python 包（装配/运动/安全/绘图/硬件包/流体/世界）
web/        Studio、3D 查看器、PWA
assemblies/ 11 个可复现装配
```

## 设计主张

1. **接口先于形态**：20mm M3 网格、一种螺钉、一条三线总线。
2. **每层可独立验证**：CAD 几何断言、协议字节断言、运动学数值断言、流体守恒断言。
3. **先离线后硬件**：能在仿真里证伪的，不带到实物上；不能仿真的，明确标“待实测”。
4. **商业场景从约束出发**：泳池/管道/灌溉的流体与空间约束先建模，再谈机器人形态。

## 参与 / 许可

- 改东西前看 [CONTRIBUTING.md](CONTRIBUTING.md)；问题用 [issue 模板](.github/ISSUE_TEMPLATE/)。
- 文档入口：[docs/README.md](docs/README.md)。
- MIT；硬件图纸同样 MIT，商用注明出处即可。
