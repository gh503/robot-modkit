# 84 · 独立应用孵化：AquaTwin

> 状态：**0.2.0 实测校准闭环，软件可运行；无现场数据/客户/收入**。
> 项目位置：[`ventures/aquatwin`](../ventures/aquatwin/README.md)。这是独立应用，
> 不进入 modkit 的 Python 包，也不改变物理闸门 **0/5**。

## 84.1 为什么从 modkit 孵化

modkit 已经有三块可复用的底座：

1. **机器人装配/运动学**：谁去洗、怎么动；
2. **三维世界/流体**：池子多大、水多重、阻力/泵/过滤；
3. **实验/报告**：同一输入出同一指标。

但“泳池清洗”要卖给客户，缺的不是又一个仿真命令，而是**商业闭环**：

- 按池型报价；
- 按机器人选型；
- 按单次时间/能耗/成本算回收期；
- 给服务商/OEM 一份客户能看懂的报告。

AquaTwin 就是把这个闭环做成独立产品。

## 84.2 它做什么

输入一份场景 JSON：

- 泳池：长/宽/深、水温、盐度、污染负荷；
- 机器人：清洁宽度/重叠/速度/电池/泵/刷/阻力面积；
- 过滤：捕获率/容量/反冲洗成本/压升；
- 经济：电价/工资/服务价/设备价/频次。

输出：

- `report.md`：结论、输入、覆盖、动力、过滤、成本、敏感性、边界；
- `dashboard.html`：离线单页，给销售/客户；
- `coverage.svg` / `coverage.csv`：俯视路径；
- `metrics.json`：机器可读，接 BI/CRM；
- `study.json`：输入快照，保证复现；
- `quote.html`：可打印报价页（0.2）；
- `quote.pdf` / `dashboard.pdf`：`aquatwin pdf`（0.2.1，WeasyPrint/wkhtmltopdf）；
- `aquatwin schema`：`aquatwin.measurements/1` JSON Schema；
- `calibration.json` / `validation.md` / `measurements.json`：校准因子、逐条残差、数据快照（0.2）；
- `portfolio.{json,md,html}`：多池组合（0.2）。

### 0.2 校准闭环

```bash
aquatwin measurements --file data/measurements-example.csv
aquatwin calibrate --scenario scenarios/residential_8x4.json \
  --measurements data/measurements-example.csv --out out/calibration
aquatwin study --scenario scenarios/residential_8x4.json \
  --calibration out/calibration/calibration.json --out out/calibrated
aquatwin batch --dir scenarios --out out/portfolio
aquatwin quote --scenario scenarios/residential_8x4.json --customer "客户" --out out/quote
```

只拟合 4 个透明因子（时间/部署/能耗/压升），带 90% bootstrap 区间；
**synthetic 示例不是现场数据**，报告会降级标注。协议见
[`ventures/aquatwin/docs/calibration.md`](../ventures/aquatwin/docs/calibration.md)。

## 84.3 示例结果（假设，不是实测）

`scenarios/residential_8x4.json`：

| 指标 | 值 |
|---|---:|
| 单次时间 | 6.2 min |
| 覆盖率 | 100% |
| 能耗 | 10.7 Wh |
| 运行成本 | ¥24.28/次 |
| 含折旧 | ¥31.97/次 |
| 相对人工节省 | ¥85.72/次 |
| 回收期（节省） | 3.2 月 |
| 1 年 ROI（扣折旧） | 1161.5% |

这些数来自 `model.py` 的公式 + 场景假设；**没有现场标定**，不能当报价/保证。
商业解读必须同时给基线、样本、时间窗。

## 84.4 商业场景与方向

| 场景 | 客户 | 价值 |
|---|---|---|
| 住宅泳池服务 | 10–500 池服务商 | 报价/排班/覆盖凭证 |
| 商业/酒店/社区 | 物业/资产方 | 多池计划、ESG、合规 |
| 机器人 OEM | 硬件厂 | 售前数字孪生/白标 |
| 水产养殖 | 网箱/水池运营 | 巡检路径/阻力/能耗（需新验证） |
| 自来水/蓄水池 | 水司 | 封闭空间覆盖/泵（需新验证） |
| 灌溉/冷却液 | 农业/工厂 | 泵/过滤/泄漏（需新验证） |
| 船体/HVAC | 航运/楼宇 | 覆盖/过滤（需新验证） |

定价/单位经济/竞争/风险见 [`docs/business.md`](../ventures/aquatwin/docs/business.md)；
研究/标定/判据见 [`docs/research.md`](../ventures/aquatwin/docs/research.md)；
路线图见 [`docs/roadmap.md`](../ventures/aquatwin/docs/roadmap.md)。

## 84.5 与 modkit 的边界

- AquaTwin **零运行时依赖**，可整体复制为独立仓库；
- 它复用 modkit 的领域知识，不 import `modkit`；
- 世界/流体/浅水仍在 modkit；AquaTwin 只做覆盖/时间/能耗/过滤/经济；
- 未来可把 AquaTwin 场景导出为 `modkit.world/1`，用 `world run` 做局部流场，
  再把结果回填经济模型；这是二期，不是现在；
- 物理闸门 0/5；AquaTwin 不改变“无实物证据”的事实。

## 84.6 怎么跑

```bash
cd ventures/aquatwin
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
aquatwin study --scenario scenarios/residential_8x4.json --out out/residential
```

测试：`make aquatwin-check`（25 项），CI 有独立 job。

## 84.7 下一步

软件侧的导入/校准/批量/报价管线已经就绪；唯一重要的事变成
**拿 10–20 个真实池子跑这条管线**，把时间/能耗误差压到 ±20%、覆盖率 ±5pp。
达不到就不对外承诺精度；下一步功能（白标/API/多边形池）排在现场验证之后。
