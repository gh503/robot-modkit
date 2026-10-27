# AquaTwin · 泳池清洗机器人数字孪生

> **独立应用项目**（`ventures/aquatwin`），不是 modkit 的一个命令。
> 目标客户：泳池服务运营商、泳池机器人 OEM、商业/酒店/社区泳池资产方。
> 当前版本 **0.2.0**：可运行 MVP + 实测导入/校准/批量/报价闭环；**没有现场实测**，
> 合成示例只用于验证软件管线，不能当 field-validated。

## 一句话

把“这个池子用这台机器人洗一次要多久、多少电、多少成本、几个月回本”从**上门试**
变成**先算清楚**，并输出客户能看懂的一页报告。

## 为什么是现在

- 泳池清洗是高频、标准化、可外包的服务；人工成本上涨、旺季招工难；
- 泳池机器人从“随机碰撞”转向“路径覆盖 + 过滤管理”，需要**按池型选型**；
- 服务商投标/报价缺一个可解释的工时、能耗、过滤负荷模型；
- 现有 CFD 太重、太贵，服务商需要**分钟级、可解释、可批量**的降阶模型。

## 谁付钱

| 客户 | 痛点 | AquaTwin 给什么 |
|---|---|---|
| 泳池服务商（10–500 池） | 报价靠经验、上门试错、旺季排班 | 每池工时/成本/覆盖报告；路线与机器人选型 |
| 泳池机器人 OEM | 客户问“能不能洗我的池” | 售前数字孪生；参数敏感性；投标材料 |
| 酒店/社区/物业 | 外包质量不可见 | 覆盖率、能耗、过滤负荷的可解释凭证 |
| 保险/合规/审计 | 清洁记录不结构化 | 可复现的 `metrics.json` + 报告（未来接台账） |

## 快速开始

```bash
cd ventures/aquatwin
python3 -m venv .venv && . .venv/bin/activate
pip install -e .

aquatwin list
aquatwin validate --scenario scenarios/residential_8x4.json
aquatwin study --scenario scenarios/residential_8x4.json --out out/residential

# 有实测数据后：导入/校验 → 校准 → 用校准模型出报告
aquatwin measurements --file data/measurements-example.csv
aquatwin calibrate --scenario scenarios/residential_8x4.json \
  --measurements data/measurements-example.csv --out out/calibration
aquatwin study --scenario scenarios/residential_8x4.json \
  --calibration out/calibration/calibration.json --out out/calibrated

# 多池组合 / 客户报价页
aquatwin batch --dir scenarios --out out/portfolio
aquatwin quote --scenario scenarios/residential_8x4.json \
  --customer "示例客户" --out out/quote
```

打开：

- `out/residential/report.md`：给工程/客户看的完整报告；
- `out/residential/dashboard.html`：给销售/客户看的一页（离线、无 CDN）；
- `out/residential/coverage.svg`：俯视覆盖路径；
- `out/residential/metrics.json`：机器可读，接 BI/CRM；
- `out/residential/study.json`：输入快照，保证可复现；
- `out/residential/quote.html`：可打印客户报价页（不是合同/性能保证）；
- `out/calibration/calibration.json` + `validation.md`：校准因子与逐条残差；
- `out/portfolio/portfolio.{json,md,html}`：多池组合。

四个内置场景：住宅 8×4m、商业 25×10m、小型 6×3m、L 形 8×4m（polygon）。

## 输出长什么样

```
单次 6.2 min（补电 0.0）；覆盖 100.0%；能耗 10.7 Wh
运行成本 ¥24.28；含折旧 ¥31.97；单次节省 ¥85.72
回收期（节省）3.2 个月；1 年 ROI 1161.5%
```

> 这是**示例假设**，不是市场报价/实测。报告里逐条列出假设与边界。

## 实测导入与校准（0.2）

没有实测数据时，模型只能做方案比较；有数据后走这条链：

```text
measurements.csv/json
  → measurements（校验/字段/单位/缺失值）
  → calibrate（time_scale / setup_min / energy_scale / pressure_scale）
  → study --calibration（把因子应用到报告/报价）
  → validation.md（逐条残差 + 边界）
```

CSV 最小列：

```csv
study,source,run_id,time_min,energy_wh,coverage_pct,pressure_kpa,speed_m_s,debris_g_m3
住宅泳池 8×4m,field,r1,6.4,10.8,98.0,4.2,0.25,5
```

- `source`：`field` / `lab` / `vendor` / `synthetic`；只有 `field` 才能写现场验证；
- 条件列可覆盖 `speed_m_s/swath_m/overlap/debris_g_m3/water_temp_c/...`，
  用于让多条数据可区分参数；
- `calibrate` 输出 4 个透明因子，不改变模型结构；`time_scale`/`setup_min` 约束在
  合理范围，超出会截断并在 `caveats` 里说明；
- **校准 ≠ 认证**：数据不足、非现场、外推到新池型都必须降级表述。

完整协议/字段/判据见 [`docs/calibration.md`](docs/calibration.md)。

## 场景 JSON

```json
{
  "schema": "aquatwin.study/1",
  "name": "住宅泳池 8×4m",
  "pool": {"length_m": 8, "width_m": 4, "depth_m": 1.5,
           "water_temp_c": 26, "salinity_ppt": 2, "debris_g_m3": 5},
  "robot": {"swath_m": 0.45, "overlap": 0.10, "speed_m_s": 0.25,
            "battery_wh": 90, "pump_flow_m3_s": 0.0008, "pump_head_m": 3},
  "filter": {"capture_efficiency": 0.90, "capacity_g": 500,
             "backwash_cost_cny": 30},
  "economics": {"electricity_cny_kwh": 0.8, "labor_cny_h": 60,
                "service_price_cny": 300, "robot_capex_cny": 6000,
                "cleanings_per_week": 5}
}
```

字段完整定义见 [`aquatwin/scenario.py`](aquatwin/scenario.py)；缺省值就是代码里的默认值，
报告会标为假设。`aquatwin new --out scenarios/my.json` 生成模板。

## 模型（可手算）

1. **体积/水质**：`V=L×W×D`；`ρ≈998.2+0.8S−0.25(T−20)`；水质量 `ρV`。
2. **覆盖**：有效宽度 `w=swath×(1−overlap)`；矩形 lane 数 `⌈W/w⌉`，
   路径 `L×lanes+(lanes−1)w`；多边形用扫描线交区间 + travel，覆盖率按
   `区间长×w/多边形面积` 截断到 100%。
3. **阻力**：`F=½ρCdAv²`；驱动功率 `Fv/η` + 刷/电子。
4. **泵**：水力 `ρgQH`；轴功率 `/η_pump`。
5. **时间**：`路径/v + 转向×turn_time`；电池不足按 80% 可用容量加补电。
6. **过滤**：捕集 `V×debris×capture`；循环 `捕集/容量`；压升/反冲洗水。
7. **成本**：电+反冲洗+监管+维护+折旧；对比人工 `工时×工资+化学品`。
8. **回收期**：设备价 / 月节省；同时给“服务利润”口径，避免混淆。

所有公式在 `aquatwin/model.py`，报告里重复一遍；没有黑盒 ML。
校准只加 4 个乘子：`time_scale`、`setup_min`、`energy_scale`、`pressure_scale`；
`model_version` 与因子一起写进 `metrics.json`/`calibration.json`，可追溯。

## 商业场景与方向

###  beachhead：住宅泳池服务商

- 按池型/机器人参数出报告，减少“到了现场才发现洗不干净”；
- 用覆盖率/工时/成本做报价，而不是拍脑袋；
- 旺季按“机器人+人”排班，报告作为服务凭证。

### 扩展 1：OEM 售前数字孪生

- OEM 把 AquaTwin 嵌进官网/销售工具：客户输入池子尺寸，出“适配/时间/成本”；
- 按年 license 或按报告收费；数据回流用于产品定义。

### 扩展 2：商业/酒店/社区泳池

- 多池资产组合：按池型、污染负荷、电价做清洁计划；
- 过滤反冲洗/水耗/能耗纳入 ESG 报告；
- 与工单/BMS/水质传感器对接。

### 扩展 3：相邻水域（同一套引擎）

- 水产养殖网箱/水池巡检（路径+阻力+能耗）；
- 自来水厂/蓄水池/管道检查（封闭空间覆盖）；
- 灌溉/喷淋/冷却液巡检（流体+泵+过滤）；
- 船体清洗/HVAC 风管（不同末端，同一经济性框架）。

> 这些是**方向**，不是已经交付的产品；每个方向都需要独立的场景 schema 与现场验证。

## 商业模式（示例，不是承诺）

| 模式 | 价格假设 | 交付 | 备注 |
|---|---|---|---|
| 单次研究 | ¥299/池 | PDF/HTML 报告 | 获客入口 |
| 服务商订阅 | ¥999/月/路线 | 批量报告+API | 10–100 池 |
| OEM license | ¥5–20 万/年 | 嵌入/白标 | 按出货/席位 |
| 数据/标定服务 | ¥2–5 万/项目 | 实测标定+模型 | 需要现场 |

单位经济模型：一个服务商 100 池、每周 5 次、单次节省 ¥80 → 年节省约 ¥208 万
（示例算术，不是市场预测）；AquaTwin 收费应显著低于节省。详细测算见
[`docs/business.md`](docs/business.md)。

## 研究/验证（必须做，不能跳过）

MVP 只证明“模型能跑、账能算清”，不证明“预测准”。下一步：

1. **标定**：3 种池型 × 3 种机器人 × 3 种污染负荷；测实际时间、能耗、覆盖率、
   过滤压升；记录水温/盐度/流量。
2. **误差目标**：时间/能耗 ±20%，覆盖率 ±5 个百分点；达不到就不对外承诺。
3. **覆盖真值**：染料/水下相机/标记点，不只信路径长度。
4. **过滤**：实测压升-捕集曲线，替换固定 `pressure_rise_kpa_per_100g`。
5. **经济**：用客户真实工资/电价/服务价，不用本文示例价。
6. **安全/合规**：电气、溺水、化学品、隐私（相机）单独评估。

详见 [`docs/research.md`](docs/research.md)。

## 目录

```
aquatwin/
  scenario.py    # schema/校验
  coverage.py    # 矩形 boustrophedon + SVG/CSV
  model.py       # 物理/时间/能耗/过滤/经济
  measurements.py # 实测 schema/CSV/JSON/校验
  calibrate.py    # 4 因子拟合 + validation.md
  batch.py        # 多池组合/portfolio
  report.py       # report/dashboard/quote/validation
  cli.py          # list/validate/study/roi/new/measurements/calibrate/batch/quote
scenarios/       # 3 个内置场景
data/            # synthetic 示例测量（不是现场数据）
tests/           # 16 项 pytest
docs/            # calibration/business/research/pricing/roadmap
```

## 边界（必须读）

- 不是 CFD：阻力系数、泵曲线、过滤曲线都是假设，需实测标定；
- 覆盖只支持矩形 + 无自交多边形；不含障碍/台阶/斜池/水流，路径是扫描线近似；
- 不含水质化学、藻类、消毒副产物、溺水/电气安全；
- 经济模型是**方案比较**，不是报价、收益承诺或投资建议；
- 没有现场数据/物理闸门；对外必须标“modeled, not measured”；
- 校准因子只在导入数据覆盖的池型/机器人/工况内有效；外推必须重新验证；
- 与 modkit 的关系：可独立运行；modkit 提供机器人/世界/流体底座，
  AquaTwin 只带自己的商业逻辑（当前零运行时依赖）。

## 独立/拆分

本目录自带 `pyproject.toml`、测试、场景、文档，可整体复制为独立仓库：

```bash
cp -r ventures/aquatwin ~/aquatwin && cd ~/aquatwin && git init && pip install -e .
```

拆分后不需要 modkit；若要接 modkit 的世界/流体，再加可选依赖即可。

## License

与 robot-modkit 相同（见仓库根 `LICENSE`）；商业授权/白标另议。
