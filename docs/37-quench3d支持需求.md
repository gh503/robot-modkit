# 37 · 让 quench3d 完整支持本项目的仿真（给另一个 agent 的任务书）

> 用途：把下面「提示词」整段发给执行 quench3d 的 agent。
> 背景：本项目的在线预览用 three.js（运动学）；需要 quench3d 补上**动力学 + 运行时控制 + 每连杆网格**，
> 才能做抓取接触、堵转力矩、跌落这类离线校核。

## 1. 现状与证据

| 试验（quench3d 0.1.0） | 结果 |
|---|---|
| 场景校验（5 刚体 / 3 铰链） | 0 error / 0 warning |
| 单铰链位置伺服 30° | 29.9°，稳定 |
| 双铰链 30° / -60° | 29.9° / -60.2°，稳定 |
| 三自由度（0 / 35 / -55） | 12s 内肩 8.4°–60°、肘 -17°–-63° 漂移 |
| `fixed` 焊两根连杆 | 约 24° 转动漂移 |
| 断裂力矩 0.05 / 0.5 N·m | 断开 / 保持（符合预期） |

复现场景：<https://raw.githubusercontent.com/gh503/robot-modkit/main/sim/out/modkit_arm.scene.json>

## 2. 提示词（直接复制）

````text
你是 quench3d（https://github.com/gh503/quench3d）的工程师。目标：让 quench3d 完整支持一台
4 自由度桌面机械臂的动力学仿真、离线批处理与浏览器在线预览。

一、背景与现有资产
- quench3d 是纯 Rust 3D 引擎 + 自研刚体物理（wgpu，桌面/Web/CLI/MCP，Apache-2.0）。
- 被仿真的机器人：robot-modkit M1，约 360g，大臂 120mm、小臂 110mm，3 个关节用 30kg·cm
  总线舵机（额定 2.94 N·m），关节径向间隙 0.2mm，夹爪 40mm。
- 已有一个可校验的场景（3 铰链位置伺服 + 断裂力矩）：
  https://raw.githubusercontent.com/gh503/robot-modkit/main/sim/out/modkit_arm.scene.json
  生成器（mm/Z-up → m/Y-up 的换算、锚点、质量）：
  https://github.com/gh503/robot-modkit/blob/main/sim/quench_scene.py
  说明文档：https://github.com/gh503/robot-modkit/blob/main/docs/12-仿真与可视化.md §0.3
- 我已实测的问题（0.1.0，默认伺服增益 stiffness 8 / damping 1）：
  · 单/双铰链位置伺服能稳（29.9°/30°）；
  · 三自由度串链 12s 内肩在 8.4°–60°、肘在 -17°–-63° 漂移，不收敛；
  · 用 fixed 关节焊两根连杆，2s 内约 24° 转动漂移；
  · simulate 报告只有刚体位姿，没有关节角度/力矩；
  · 场景是静态的，没有"运行中改关节目标"的入口；
  · 每个连杆的 STL 不能挂到刚体上（models[] 是独立视觉对象）。

二、任务（按优先级）

P0-1 串链位置伺服稳定
- 目标：对 2–4 个串联铰链、每节 0.05–0.5kg、负载力矩 ≤3 N·m，在 dt=1/500–1/60 下，
  5 秒内到达目标 ±1°，无持续振荡，不越限位。
- 允许的做法：子步（physics.substeps）、约束迭代次数、伺服增益按 SI 单位并给推荐值、
  速度前馈/重力前馈、或明确的 PD+限幅模型。不要引入第三方物理库。
- 必须暴露可调参数并写进场景 schema（例如 physics.substeps / solver_iterations）。
- 验收：用上面的 modkit_arm 场景，yaw=0、shoulder=35、elbow=-55，5s 后
  |肩-35|≤1.0°、|肘+55|≤1.0°，偏航块倾角 ≤0.5°；连续 3 个增益档都能过。

P0-2 关节遥测
- simulate --json 增加 joints[]：name/angle_deg/target_deg/error_deg/torque_nm/
  limit_state(ok|low|high)/broken；--trace 支持关节角度序列。
- 验收：报告里的肩力矩与解析静力矩（约 0.19 N·m）误差 ≤15%；断开的关节有明确标记。

P0-3 运行时关节控制（做抓取序列的前提）
- 任选其一，但必须能用脚本驱动：
  a) actions 增加 "joint_target"（at_time/at_step、joint 名、target_deg、可选速度）；
  b) 新命令 quench3d drive <scene> --script <json> 逐步改目标并输出轨迹；
  c) Rust SDK/MCP 暴露 set_joint_target(joint, deg) 并保证 step() 后可读。
- 验收：给一个 3 关节 + 平行夹爪、桌上 40mm 方块的场景，脚本完成
  "到上方 → 下降 → 闭合 → 抬起 10cm → 保持 1s"，报告方块升高 ≥10cm 且不滑落。

P1-1 刚体挂网格（视觉与碰撞分离）
- objects[] 增加 visual：{path, position, rotation_deg, scale}，支持 STL/GLB/OBJ；
  网格跟随刚体位姿；碰撞仍用 shape/shapes 代理。
- 验收：用 modkit 的 STL（https://github.com/gh503/robot-modkit 的 cad/out/*.stl）
  渲染一台整机，转动关节时网格跟手不漂移；`simulate` 不因挂网格改变物理结果。

P1-2 运动学回放模式
- 允许 body: "kinematic" 或 drive 模式：按关节目标播放轨迹，不参与重力/接触求解，
  用于"没有物理也要看动作"。确定性、可逐帧截图。
- 验收：同一脚本跑两遍，逐帧位姿逐位相同。

P1-3 Web/wasm 运行时接口
- 导出 setJointTarget/step/getJointStates/getBodyTransform；示例页面能拖动滑杆让模型动；
  文档写清 wasm 体积与 60fps 的规模上限。
- 注意：Web Serial 由页面 JS 负责，引擎只提供接口，不要内置串口。

P2（可后置）
- MCP 工具：joint_target / simulate_steps / query_contact；
- 接触力查询（抓取是否夹住）；
- 性能：4 自由度 60fps、1000 步批量 <2s。

三、约束
- 不破坏现有场景格式：新字段必须可选，旧场景逐位不变；必要时升 version 并给迁移说明。
- 保持确定性、#![forbid(unsafe_code)]、无第三方物理库、三平台 + wasm CI 全绿。
- 单位：米、秒、N、N·m；角度字段名带 _deg 的用度，limits 用弧度（保持现状，但文档写死）。
- 不要静默忽略非法字段：校验器要报错或警告。

四、交付
- 代码 + 测试（上面每条验收都要有对应的 Rust/CLI 测试，CI 能跑）。
- 场景 fixture：把 modkit_arm.scene.json 收进 tests/fixtures，并按需要补一份带夹爪/方块的。
- 文档：units、伺服增益推荐值、substeps、joint_target/drive 用法、visual 挂载、wasm API。
- 一份结果表：每条验收的命令、数值、PASS/FAIL；没做到的写清原因，不要模糊。
````

## 3. 验收口径（给评审用）

- P0 全过才叫「能支持整机动力学」；
- P1 全过才叫「能替代 three.js 做在线预览」；
- P2 是加分项，不影响结论。
