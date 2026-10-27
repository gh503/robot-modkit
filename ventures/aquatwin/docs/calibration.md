# AquaTwin 校准协议（v0.2）

> 目标：把“模型假设”变成“在明确数据范围内可检查的预测”。
> 不是：用少量数据训练黑盒、承诺精度、替代现场验收。

## 1. 数据分层

| `source` | 含义 | 能写什么 |
|---|---|---|
| `field` | 真实泳池、真实机器人、真实仪表 | 可作为现场校准证据 |
| `lab` | 实验池/台架，条件可控 | 可做参数辨识，不直接外推现场 |
| `vendor` | OEM/供应商提供 | 可做先验/对比，需注明来源 |
| `synthetic` | 由模型生成，仅测软件管线 | **绝不能**当实测 |

报告会原样带出 `source`；`synthetic/lab/vendor` 会追加 caveat。代码不提供“把合成数据伪装成 field”的开关。

## 2. 测量数据格式

### 2.1 JSON

```json
{
  "schema": "aquatwin.measurements/1",
  "study": "住宅泳池 8×4m",
  "source": "field",
  "collected_at": "2026-10-01T09:00:00+08:00",
  "instrumentation": "钳形功率计 + 秒表 + 过滤压差表",
  "notes": "同一机器人、同一过滤芯",
  "runs": [
    {
      "run_id": "r1",
      "time_min": 6.4,
      "energy_wh": 10.8,
      "coverage_pct": 98.0,
      "pressure_kpa": 4.2,
      "debris_g": 38.0,
      "conditions": {"speed_m_s": 0.25, "debris_g_m3": 5.0},
      "notes": "池边有台阶，路径被截断"
    }
  ]
}
```

必填：`run_id`、`time_min`、`energy_wh`。可选：`coverage_pct`（0–100）、
`pressure_kpa`、`debris_g`、`conditions`、`notes`。

### 2.2 CSV

最小列：

```csv
study,source,run_id,time_min,energy_wh
住宅泳池 8×4m,field,r1,6.4,10.8
```

可选列：`coverage_pct,pressure_kpa,debris_g,notes`，以及条件列
`speed_m_s,swath_m,overlap,turn_time_s,battery_wh,pump_flow_m3_s,pump_head_m,
pump_efficiency,drag_cd,body_area_m2,debris_g_m3,water_temp_c,salinity_ppt,
length_m,width_m,depth_m`。

`study/source` 可以在每行重复；CSV 里没有时用 CLI 参数补：

```bash
aquatwin measurements --file data/measurements.csv --study "住宅泳池 8×4m" --source field
```

### 2.3 条件（conditions）的作用

如果 4 条数据都在同一速度/同一污染负荷下，模型只能拟合一个总乘子，无法区分
“路径慢”还是“泵效率低”。**条件列是多条数据能校准的前提**：

- 至少覆盖 2 个速度或 2 个清洁宽度；
- 至少覆盖 2 个污染负荷（有压力数据时）；
- 每组条件记录仪表、池型、机器人固件/电池状态。

## 3. 校准模型

模型结构不变，只拟合 4 个因子：

| 因子 | 作用 | 约束 | 拟合方式 |
|---|---|---|---|
| `time_scale` | 作业时间乘子（路径/转向/实际降速） | 0.30–3.00 | `time ≈ a × active_time + b`，二维网格 + 局部细化 |
| `setup_min` | 每次部署固定时间（下水/收线/检查） | 0–30 min | 同上 |
| `energy_scale` | 能耗乘子（泵/驱动/电池综合偏差） | 0.20–5.00 | 过原点加权最小二乘 |
| `pressure_scale` | 过滤压升乘子 | 0.10–5.00 | 过原点加权最小二乘 |

应用顺序：

```text
active_h  ← active_h × time_scale + setup_min/60
energy_wh ← energy_wh × energy_scale
pressure  ← pressure × pressure_scale
然后重新计算补电次数、总时间、电费、单次成本、回收期
```

输出 `calibration.json` 同时带：

- `model_version` / `study_sha256` / `measurements_sha256`；
- `n_runs` / `source` / `bounds`；
- 时间/能耗/压力 MAPE、覆盖率 MAE；
- 4 个因子的 90% bootstrap 区间（确定性重采样；不是新池型预测区间）；
- 逐条残差（实测/预测/误差）；
- `caveats`（数据不足、非现场、无压力数据等）。

## 4. 判据（建议，不是自动认证）

| 指标 | 试点门槛 | 说明 |
|---|---|---|
| 时间 MAPE | ≤ 20% | 至少 3 个池型、每型 ≥3 条 |
| 能耗 MAPE | ≤ 20% | 同一功率计口径 |
| 压力 MAPE | ≤ 25% | 有压差表时 |
| 覆盖率 MAE | ≤ 5 pp | 染料/相机真值，不只看路径 |
| 区间 | 报告必须给 90% bootstrap 区间 | 区间宽 = 数据不足，不能只报点估计 |
| 外推 | 新池型/新机器人必须重做 | 因子不是普适常数 |

达不到门槛时：报告保留“未校准/低置信”，不隐藏残差，不用单点最优冒充验证。

## 5. 现场采集清单（最小可用）

1. 池型：长/宽/深、台阶/斜坡/障碍、水面到池边距离；
2. 机器人：型号、固件、清洁宽度、速度设置、电池健康；
3. 过滤：滤芯型号/新旧、起始压差、结束压差、反冲洗前后；
4. 仪表：功率计（或电池库仑计）、秒表、压差表、水温/盐度；
5. 每条 run 记录：日期、开始/结束、实际路径是否被中断、补电次数；
6. 覆盖真值：染料/水下相机/池底标记，至少抽 2 个池做；
7. 失败样本也要保留：卡住、漏扫、二次下水——这些比成功样本更有价值。

**不能删失败样本。** 只留成功样本会把 MAPE 做漂亮，却让报价失真。

## 6. 命令

```bash
# 校验（JSON 或 CSV）
aquatwin measurements --file data/measurements-example.csv --json

# 拟合并输出 calibration.json + validation.md
aquatwin calibrate --scenario scenarios/residential_8x4.json \
  --measurements data/measurements-example.csv --out out/calibration

# 用校准后的模型出报告/报价
aquatwin study --scenario scenarios/residential_8x4.json \
  --calibration out/calibration/calibration.json --out out/calibrated

# 或者一步：study --measurements（内部先校准）
aquatwin study --scenario scenarios/residential_8x4.json \
  --measurements data/measurements.csv --out out/calibrated

# 模型审计（软件/数据管线 vs 现场验证）
aquatwin audit --scenario scenarios/residential_8x4.json \
  --measurements data/measurements-example.csv --out out/audit

# 多池组合
aquatwin batch --dir scenarios --out out/portfolio \
  --calibration out/calibration/calibration.json
```

## 7. 版本与复现

- `model_version` 固定在 `aquatwin/model.py`；改公式必须升版本；
- 报告带输入快照 `study.json`、`calibration.json`、`measurements.json`；
- 同一输入重复运行应得到同一 JSON（无随机数；网格搜索确定性）；
- 旧校准文件在新模型上不自动兼容：版本不一致时报告必须显式提示。

## 8. 模型审计

`audit.json` 是固定 schema `aquatwin.audit/1`，由 `aquatwin audit` 生成。它至少检查：

- `model_version` 与代码一致；校准因子在 `FACTOR_BOUNDS` 内；
- 90% bootstrap 区间合法；校准的 `study` 与当前场景匹配；
- 数据来源（field/lab/vendor/synthetic）、样本数、时间/能耗 MAPE；
- `physical_gate` 硬编码为 `"0/5"`，`field_validated` 硬编码为 `false`。

`software_ready:true` 只代表代码/数据管线可复现；**审计通过不是现场通过**。
JSON Schema 也用 `const false` / `const "0/5"` 锁死，不能靠手改字段冒充验证。

## 9. 明确不做

- 不做逐池“记忆”/在线学习；每条数据先进入可审计文件；
- 不用合成数据补足样本量；
- 不把 MAPE 当性能保证；
- 不用校准掩盖覆盖/安全/电气问题；
- 不在没有现场数据时写“已验证/已认证”。
