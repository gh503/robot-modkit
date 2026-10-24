"""线束：加工表 + 走线示意图。

为什么值得单独做：
  · 线的长度错了，装到最后才发现短 20mm，整批返工；
  · 没有编号，故障时"哪根是 W8"要拆开看。

产物：
  docs/images/harness.png        俯视走线示意（非比例）
  docs/26-线束加工.md            裁线表 + 压接/标签/通断测试

用法：cd cad && ../.venv/bin/python harness.py
"""

from __future__ import annotations

import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import params as P
from matplotlib import font_manager as fm

# 与 drawings.py 一致：注册 Noto CJK，否则中文全变方框
for _f in ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
           "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
           "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"):
    if pathlib.Path(_f).exists():
        fm.fontManager.addfont(_f)
plt.rcParams["font.sans-serif"] = ["Noto Sans CJK JP", "Noto Sans CJK SC",
                                   "WenQuanYi Zen Hei", "DejaVu Sans"]
plt.rcParams["font.family"] = "sans-serif"

ROOT = pathlib.Path(__file__).parent.parent
DOCS = ROOT / "docs"
DATA = ROOT / "hardware" / "harness.json"

# 俯视示意坐标（mm，底盘中心为原点；只是示意，不是装配定位）
NODES = {
    "battery": (-80, 0), "fuse": (-100, 40), "estop": (-112, -35),
    "term": (-20, 0), "dcdc": (10, -45), "esp32": (55, -45), "pi": (90, -45),
    "arm": (P.ARM_ORIGIN_X, 0),
    "servo1": (P.ARM_ORIGIN_X, 0), "servo2": (P.ARM_ORIGIN_X + 10, 60),
    "servo3": (P.ARM_ORIGIN_X + 30, 110), "servo4": (P.ARM_ORIGIN_X + 45, 140),
    "servo5": (-P.DRIVE_Y, -P.DRIVE_Y - 20), "servo6": (-P.DRIVE_Y, P.DRIVE_Y + 20),
    "gpio5": (55, -45), "estop_aux": (-112, -35),
}

# 把 from/to 文本映射到示意节点
def node_of(text: str) -> str | None:
    t = text
    table = [
        ("电池 XT60", "battery"), ("保险丝座", "fuse"), ("急停按钮", "estop"),
        ("12V 分线端子", "term"), ("DC-DC 5V 输入", "dcdc"), ("DC-DC 5V 输出", "dcdc"),
        ("ESP32 5V", "esp32"), ("树莓派 5V", "pi"),
        ("ESP32 TX/RX", "esp32"), ("半双工收发器", "dcdc"),
        ("收发器 DATA", "dcdc"), ("舵机 1 DATA", "servo1"), ("舵机 2 DATA", "servo2"),
        ("舵机 3 DATA", "servo3"), ("舵机 4 DATA", "servo4"),
        ("驱动舵机 5/6 电源", "servo5"), ("电池分压", "battery"),
        ("ESP32 GPIO5", "gpio5"), ("急停辅助触点", "estop_aux"),
        ("ESP32 GPIO（可选）", "esp32"),
    ]
    for k, v in table:
        if k in t:
            return v
    return None


def route(a: tuple[float, float], b: tuple[float, float], k: int):
    """正交走线，按 k 错开，避免全部叠在一条直线上。"""
    off = (k % 5 - 2) * 6.0
    midx = (a[0] + b[0]) / 2 + off
    return [a, (midx, a[1]), (midx, b[1]), b]


def draw(cables: list[dict]) -> pathlib.Path:
    fig, ax = plt.subplots(figsize=(9, 7.6), dpi=160)
    # 底盘轮廓
    ax.add_patch(plt.Rectangle((-P.CHASSIS_X / 2, -P.CHASSIS_Y / 2), P.CHASSIS_X, P.CHASSIS_Y,
                               fill=False, lw=2, ec="#333"))
    ax.add_patch(plt.Rectangle((-P.CHASSIS_X / 2 + 6, -P.CHASSIS_Y / 2 + 6),
                               P.CHASSIS_X - 12, P.CHASSIS_Y - 12,
                               fill=False, lw=0.8, ls="--", ec="#999"))
    # 轮子/万向轮
    for sy in (-1, 1):
        ax.add_patch(plt.Rectangle((-P.DRIVE_Y - 12, sy * 75 - 10), 24, 20, color="#555"))
    for sx in (-1, 1):
        ax.add_patch(plt.Circle((sx * P.CASTER_X, 0), 9, fill=False, ec="#555", lw=2))
    # 臂底座
    ax.add_patch(plt.Circle((P.ARM_ORIGIN_X, 0), 26, fill=False, ec="#4c78a8", lw=2))
    ax.text(P.ARM_ORIGIN_X, 0, "臂底座", ha="center", va="center", fontsize=8)

    colors = plt.cm.tab20.colors
    for i, c in enumerate(cables):
        a = NODES.get(node_of(c["from"]) or "", None)
        b = NODES.get(node_of(c["to"]) or "", None)
        if a is None or b is None:
            continue
        pts = route(a, b, i)
        xs, ys = zip(*pts)
        ax.plot(xs, ys, color=colors[i % len(colors)], lw=1.6, alpha=0.9,
                solid_capstyle="round")
        mx, my = pts[1]
        ax.annotate(c["id"], (mx, my), fontsize=7, color=colors[i % len(colors)],
                    xytext=(2, 2), textcoords="offset points")

    for name, (x, y) in NODES.items():
        ax.plot([x], [y], "o", ms=3, color="#222")
    ax.set_aspect("equal")
    ax.set_xlim(-P.CHASSIS_X / 2 - 20, P.CHASSIS_X / 2 + 40)
    ax.set_ylim(-P.CHASSIS_Y / 2 - 20, P.CHASSIS_Y / 2 + 60)
    ax.set_xlabel("x / mm")
    ax.set_ylabel("y / mm")
    ax.set_title("M1 线束走向（俯视示意，非装配定位）")
    ax.grid(alpha=0.2)
    out = DOCS / "images" / "harness.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return out


def main() -> int:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    cables = data["cables"]

    fails = []
    for c in cables:
        if not (40 <= c["length_mm"] <= 400):
            fails.append(f"{c['id']} 长度 {c['length_mm']} 不合理")
        if c["awg"] not in (18, 20, 22, 24, 26, 28):
            fails.append(f"{c['id']} 线号 {c['awg']}AWG 不在清单内")
        if node_of(c["from"]) is None or node_of(c["to"]) is None:
            fails.append(f"{c['id']} 端点没画到图上：{c['from']} → {c['to']}")

    img = draw(cables)
    total = sum(c["length_mm"] for c in cables)
    by_awg: dict[int, int] = {}
    for c in cables:
        by_awg[c["awg"]] = by_awg.get(c["awg"], 0) + c["length_mm"]

    lines = [
        "# 26 · 线束加工（自动生成）",
        "",
        f"> 数据源 `hardware/harness.json`；共 **{len(cables)} 根**，总长 **{total} mm**。",
        "> 长度是**成品长度**（含两端余量），不是两点直线距离。",
        "",
        "## 1. 裁线表",
        "",
        "| 编号 | 从 | 到 | 长度 | 线号 | 连接器 | 备注 |",
        "|---|---|---|---:|---|---|---|",
    ]
    for c in cables:
        lines.append(f"| {c['id']} | {c['from']} | {c['to']} | {c['length_mm']} mm | "
                     f"{c['awg']}AWG | {c['connector']} | {c['note']} |")
    lines += [
        "",
        "## 2. 备料汇总",
        "",
        "| 线号 | 总长 | 建议多买 20% |",
        "|---:|---:|---:|",
    ]
    for awg in sorted(by_awg):
        lines.append(f"| {awg}AWG | {by_awg[awg]} mm | {int(by_awg[awg] * 1.2)} mm |")
    lines += [
        "",
        "## 3. 走线示意",
        "",
        "![线束走向](../docs/images/harness.png)",
        "",
        "> 示意只表达「谁连谁、大概走哪边」，不是装配定位图。实际以 [03-配电与线束](03-配电与线束.md) 为准。",
        "",
        "## 4. 加工步骤",
        "",
        "1. 按裁线表裁线（每根留 10mm 余量，压接后再修剪）；",
        "2. 剥线 3mm，**不要伤到铜丝**（断股会让 12V 回路发热）；",
        "3. 压接端子后拉一下（≥30N 不脱）；",
        "4. 两端套热缩管 + 编号标签（`W8` 这种），标签朝同一方向；",
        "5. 万用表通断档逐根测：两端导通、相邻两线不短路；",
        "6. 上电前再测一次 12V 与 GND 是否短路（蜂鸣档不应响）。",
        "",
        "## 5. 验收",
        "",
        "- [ ] 14 根全部有编号，标签不脱落",
        "- [ ] 每根通断正常，线间无短路",
        "- [ ] 12V 回路（W1–W3、W12）用 18AWG，压接处不发热",
        "- [ ] 舵机链（W8–W11）插头方向一致（DATA 对 DATA）",
        "- [ ] 分压线（W13）接到 GPIO5，不是 5V",
        "",
        "## 6. 还没做的",
        "",
        "- 没有做线束长度实测（等实物装配后回填）",
        "- 没有做弯折寿命测试（关节处反复弯折）",
        "- 没有做 EMI 测试（1Mbps 半双工 + 电机噪声）",
        "",
    ]
    (DOCS / "26-线束加工.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"线束 {len(cables)} 根，总长 {total} mm；按线号 {dict(sorted(by_awg.items()))}")
    print(f"图：{img.relative_to(ROOT)}")
    print("表：docs/26-线束加工.md")
    if fails:
        print("未通过：")
        for f in fails:
            print("  -", f)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
