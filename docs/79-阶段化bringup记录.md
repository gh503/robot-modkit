# 79 · 阶段化 bring-up 记录

> 状态：**v1.27.0 已实现**。整机 `bringup` 是 M1 的 11 步（六轴/视觉/任务）；
> 阶段 0/1/2 没有六轴，不能拿整机清单硬套。本工具按装配能力生成步骤，
> 记录证据和 sha256。**物理闸门仍 0/5**，simulated 永远不算。

## 79.1 和整机 bring-up 的区别

| | `modkit bringup` | `modkit stage` |
|---|---|---|
| 对象 | 整机 M1（6 轴 + 视觉 + 任务） | 当前装配（1–5 轴） |
| 步骤 | 固定 11 步 | 按能力生成 6–13 步 |
| 闸门 | M1–M5 | 阶段完成 x/y；不宣称整机 |
| 记录 | `records/bringup.json` | `records/stage-bringup.json` |
| 证据 | 必须文件 + sha256 | 同左 |

阶段 0 先用 `stage`，整机再转 `bringup`；两边都不把仿真当实测。

## 79.2 一条命令

```bash
cd software
# 生成阶段 0 的 6 步记录
../.venv/bin/python -m modkit.cli stage --action init \
  --assembly ../assemblies/bench_joint.json --serial J-001 --operator 老王

# 记录一步（pass 必须带真实证据）
../.venv/bin/python -m modkit.cli stage --action record \
  --step 2 --result pass --evidence ../records/scan.txt --note "ID 1 应答"

# 状态 / JSON
../.venv/bin/python -m modkit.cli stage --action status
../.venv/bin/python -m modkit.cli stage --action status --json
```

默认文件 `records/stage-bringup.json`；已有记录时 `init` 需要 `--force`。

## 79.3 阶段步骤数

| 阶段 | 例子 | 步骤 | 关键步骤 |
|---|---|---:|---|
| `joint` | `bench_joint` | 6 | 上电前、扫描、回中、标定、急停、烤机 |
| `arm` | `bench_arm` | 9 | + 工作空间 |
| `drive` | `rover_base` | 8 | + 轮向、直线、转向 |
| `mobile-draw` | `m1_pen` | 12 | + 240° 圆弧 |
| `mobile-pick` | `m1_budget` / `m1` | 13 | + 抓放 |

步骤由 `pack.bringup_steps()` 生成，和 [77](77-硬件准备包.md) 的 `bringup.md`
同源；改一处两边同步，避免文档和工具各写一套。

## 79.4 计划冻结

`init` 会把当时的步骤（标题/命令/通过标准）写进记录，之后即使装配 JSON 改了，
旧记录也不重新生成步骤，避免证据错位。记录同时保存装配文件 sha256；
`status`/`validate` 会提示“装配文件在记录后被修改”。

要按新装配重做，另起一个 `--file` 重新 init，不要覆盖旧证据。

## 79.5 证据规则

- `pass` 必须 `--evidence` 指向存在且非空文件；记录 sha256；
- 文件被改，`status`/`validate` 报“sha256 不符”；
- `simulated` 可记录，但 `validate` 明确提示不计入物理；
- `fail` 可记录现象/备注，方便复盘；
- 不自动发运动命令、不自动改安全配置。

## 79.6 推荐顺序

1. `assemble pack` 生成清单；
2. 按 `bringup.md` 做，`stage record` 记证据；
3. 阶段全过后，再按 [63](63-硬件到货执行单.md) 转整机 `bringup`；
4. 整机 11 步全过、且证据复核后，才谈物理闸门（当前 0/5）。

## 79.7 边界

- 阶段完成 ≠ 整机验收；不改变 0/5；
- 证据真实性靠人；工具只做存在性/sha256，不能证明视频内容；
- 记录文件是本机 JSON，不是签名/审计系统；
- 串口/ID/限位仍以实物为准。

## 79.8 测试

- `software/tests/test_stage.py`：
  - 4 个阶段步骤数（6/9/8/12）；
  - pass 无证据/缺文件拒绝；
  - simulated 不计物理；
  - 证据被改触发 sha256；
  - init 后计划冻结；装配改动被检测；
  - CLI init/record/status。
- 总计 **309 项** pytest；Web smoke 14 组。

## 79.9 版本

- **v1.27.0**：`stage` 模块/CLI；阶段记录 + 证据/sha256；
  Web 增加“复制硬件包命令”；测试 302 → 307。
- **v1.28.0**：阶段计划冻结 + 装配 sha256 变更检测；测试 307 → **309**。
