"""打印前的校准件与拼盘工具（不属于整机 BOM）。

`print_gauge()`  —— 先打这个小件，量三件事：
    · M3 螺钉过孔：Ø3.2 / 3.4 / 3.6，选能轻松穿过又不旷的那一档
    · 舵机宽度槽：24.7 / 25.1 / 25.5，选能塞进 ST-3215 又不太松的那一档
    · 平面度：一件 5mm 厚的板，翘曲超过 0.3mm 就会让底盘装不平
这一步只花 15 分钟、几克料，却能避免打完 12 个零件才发现孔小了。

业界做法参考 TheRobotStudio/SO-ARM100 的 Gauges 目录（STL/Gauges/Gauge_0.STL）。
"""

from __future__ import annotations

import params as P
from build123d import Box, Cylinder, Pos

# 量具外形
GAUGE_X, GAUGE_Y, GAUGE_T = 100.0, 96.0, 5.0
SLOT_PITCH = 31.5      # 槽中心距：最宽槽 25.5 + 6mm 筋
HOLE_D = (3.2, 3.4, 3.6)
SLOT_W = (24.7, 25.1, 25.5)
SLOT_X = 14.0          # 槽从 x=0 边向内开 14mm
SLOT_GAP = 4.0         # 槽与槽之间的筋（要 ≥ MIN_WALL）


def print_gauge():
    """一块板上同时测 M3 过孔与舵机宽度。"""
    plate = Pos(GAUGE_X / 2, 0, GAUGE_T / 2) * Box(GAUGE_X, GAUGE_Y, GAUGE_T)

    # 三条开口槽，宽度分别对应三种打印补偿下的舵机座
    for i, w in enumerate(SLOT_W):
        y = (i - 1) * SLOT_PITCH
        slot = Pos(SLOT_X / 2, y, GAUGE_T / 2) * Box(SLOT_X, w, GAUGE_T + 2)
        plate -= slot

    # 三个过孔，沿 y 排开，间距 12mm（孔间最小筋 = 12 - 3.6 = 8.4mm）
    for i, d in enumerate(HOLE_D):
        y = (i - 1) * 12.0
        hole = Pos(GAUGE_X - 18.0, y, GAUGE_T / 2) * Cylinder(d / 2, GAUGE_T + 2)
        plate -= hole

    return plate


def gauge_expected_cut_volume() -> float:
    """量具被挖掉的体积（用来断言孔和槽真的挖出来了）。"""
    slots = sum(SLOT_X * w * GAUGE_T for w in SLOT_W)
    import math
    holes = sum(math.pi * (d / 2) ** 2 * GAUGE_T for d in HOLE_D)
    return slots + holes


def slot_rib() -> float:
    """两条槽之间的筋宽（必须 ≥ 最小壁厚，否则打印会粘在一起）。"""
    return SLOT_PITCH - max(SLOT_W)


TOOLS = {"print_gauge": print_gauge}
MATERIAL_TOOLS = {"print_gauge": "PETG / 4 层壁 / 0.2mm 层高 / 15% 填充 — 校准件，可重复使用"}