# 59 · 硬件 bring-up 记录

> 没有实测证据的"调好了"不算数。`modkit bringup` 把 [42](42-完成度审计.md) §3
> 的 11 步变成可核验记录：`pass` 必须带**存在的证据文件**，仿真只能标 `simulated`。

## 1. 为什么不是一张勾选表

- 勾选表可以随手全打勾；这里 `pass` 要提供扫描日志、视频、CSV 或照片，记录文件 sha256；
- 证据被改过，`verify` 会报 `sha256 不符`；
- `simulated` 永远不计入物理闸门，避免"仿真通过"被说成"实物通过"；
- 记录是 JSON，能进 `records/` 存档、随质检记录一起交付。

## 2. 命令

```bash
# 看 11 步与对应闸门
modkit bringup --action list

# 只读检查：scan + 读反馈；不发运动/扭矩指令
modkit --port /dev/ttyUSB0 bringup --action check
# 无硬件时只读仿真
modkit bringup --action check --sim

# 建记录（序列号建议与质检记录一致）
modkit bringup --action init --serial M1-2026-0001 --operator 老王

# 每做完一步，登记证据
modkit bringup --action record --step 2 --result pass \
  --evidence logs/scan-M1-2026-0001.txt --note "6 轴全在，12.1V"

# 状态 / 下一步
modkit bringup --action status

# 校验证据没被改
modkit bringup --action verify

# 只演示状态机：全部 simulated，不计入物理
modkit bringup --action simulate --file /tmp/demo-bringup.json
```

默认记录 `records/bringup.json`；`--file` 可指定按序列号分开存。

## 3. 11 步与闸门

| # | 步骤 | 闸门 | 关键判据 |
|---|---|---|---|
| 1 | 上电前检查 | G4 | 12V 不短路、急停串正极、保险 3A |
| 2 | 扫描六轴 | G5 | 6 个 ID、电压/温度/故障位 |
| 3 | 方向与零位 | G6 | 方向正确、零位存盘 |
| 4 | 速度寄存器标定 | G6 | 直行 1m 偏差 <20mm |
| 5 | 急停时序 | G4 | 全速拍停 <0.3s，3 次 |
| 6 | 直线 2m | G7 | 3 次偏差 <5cm |
| 7 | 原地转 90° | G7 | 3 次误差 <3° |
| 8 | 夹爪抓放 | G7 | 100g 方块 10 次 ≥8 |
| 9 | 视觉标定 | G6 | 内参/四点/手眼，10 次识别 ≥9 |
| 10 | T1 任务闭环 | M4 | 5 次 ≥4，单次 ≤3min |
| 11 | 30min 烤机 | G7 | 壳温 <55℃、无停机 |

里程碑聚合：

- **M1**：1、2、3、8（能装、能扫、能夹）
- **M2**：4、5、6、7（能直线/转向/急停）
- **M3**：8、9（能看、能抓）
- **M4**：10（任务闭环）
- **M5**：11（长期运行）

只有某里程碑的全部步骤都 `pass`，才计 1 个物理闸门；当前 **0/5**。

## 4. 与旧记录的关系

- `modkit qc` 管**零件/装配/功能**质检（Q1–Q3）；
- `modkit bringup` 管**上电调试**的证据；
- 两者都过，才建议把 `qc` 结论改成"合格"；
- bring-up 记录不替代 [18](18-质检与验收.md) 的判据，也不替代 [28](28-生产就绪检查.md) 的 G0–G8。

## 5. 安全边界

- 工具**不自动发运动指令**，只打印应执行的命令并记录你提供的证据；
- 第 3–11 步都涉及运动，必须有人在场、急停可用；
- 真机 `mission` 仍要求先完成 1–9，且急停监控在场；
- 证据可以是日志/视频/照片/CSV，但必须能复核；不要用"我记得做了"当证据。

## 6. 测试

`software/tests/test_bringup.py` 6 项：步骤唯一、pass 必须有非空证据、sha256 篡改可抓、
simulated 不计入物理、里程碑必须全步通过、只读检查不动关节。
