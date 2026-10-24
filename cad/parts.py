"""modkit 零件库（build123d，参数化）

坐标约定（全项目统一）：
  Z+  = 关节输出方向
  原点 = 舵机出力轴中心在底板上表面的投影
  z 轴堆叠：底板 [-PLATE_T, 0] → 舵机槽 → 舵机 → 盖板 → 输出盘

轴向间隙是设计出来的，不是"打印完看运气"：
  舵机顶面 → 盖板底面   0.4mm（盖板只压不夹，避免压伤外壳）
  输出盘法兰 → 盖板顶面 0.6mm（旋转件绝不摩擦固定件）
"""

from __future__ import annotations

import math

from build123d import (
    Align,
    Axis,
    Box,
    Cylinder,
    Pos,
    export_step,
    export_stl,
    fillet,
)

import params as P

# ------------------------------------------------------------------ 轴向堆叠（推导值）
Z_SERVO_BOT = -P.SERVO_RECESS
Z_SERVO_TOP = Z_SERVO_BOT + P.SERVO_H
Z_SPLINE_TOP = Z_SERVO_TOP + P.SERVO_SPLINE_H
Z_LID_BOT = Z_SERVO_TOP + P.Z_GAP
Z_LID_TOP = Z_LID_BOT + P.LID_T
Z_DISC_BOT = Z_SERVO_TOP + 0.2
Z_FLANGE_BOT = Z_LID_TOP + 0.6
Z_DISC_TOP = Z_FLANGE_BOT + P.DISC_T
Z_POST_TOP = Z_LID_BOT


# ------------------------------------------------------------------ 工具
def _cyl(d: float, h: float, x: float = 0, y: float = 0, z: float = 0):
    return Pos(x, y, z) * Cylinder(d / 2, h, align=(Align.CENTER, Align.CENTER, Align.MIN))


def _hole(d: float, h: float, x: float, y: float, z: float, pad: float = 1.0):
    return _cyl(d, h + 2 * pad, x, y, z - pad)


def grid_points(half_x: float, half_y: float):
    out = []
    for i in range(-int(half_x // P.GRID), int(half_x // P.GRID) + 1):
        for j in range(-int(half_y // P.GRID), int(half_y // P.GRID) + 1):
            x, y = i * P.GRID, j * P.GRID
            if abs(x) <= half_x and abs(y) <= half_y:
                out.append((x, y))
    return out


# ------------------------------------------------------------------ 参考体：舵机
def servo_reference():
    """舵机包络（不打印）：机身方体 + 顶部花键柱。刻意保守，比实物略大。"""
    body = Pos(0, 0, (Z_SERVO_BOT + Z_SERVO_TOP) / 2) * Box(P.SERVO_L, P.SERVO_W, P.SERVO_H)
    spline = _cyl(P.SERVO_SPLINE_OD, P.SERVO_SPLINE_H, 0, 0, Z_SERVO_TOP)
    return body.fuse(spline)


# ------------------------------------------------------------------ 1. 关节底板
def joint_base():
    plate = Pos(0, 0, -P.PLATE_T / 2) * Box(P.BASE_X, P.BASE_Y, P.PLATE_T)

    posts = [
        Pos(sx * P.POST_XY, sy * P.POST_XY, Z_POST_TOP / 2) * Box(P.POST, P.POST, Z_POST_TOP)
        for sx in (-1, 1)
        for sy in (-1, 1)
    ]
    part = plate
    for p in posts:
        part = part.fuse(p)

    # 舵机定位浅槽（留 FIT_CLR 总间隙，靠四周限位而不是靠夹紧）
    part -= Pos(0, 0, Z_SERVO_BOT + P.SERVO_RECESS / 2) * Box(
        P.SERVO_L + P.FIT_CLR, P.SERVO_W + P.FIT_CLR, P.SERVO_RECESS + 0.02
    )

    # +X 侧出线缺口（舵机线 15cm 从侧面出来）
    part -= Pos(P.BASE_X / 2 - 3, 0, -P.PLATE_T / 2) * Box(12, P.CABLE_SLOT_W, P.PLATE_T + 2)

    # 底面 20mm 网格 M3 通孔（舵机槽下方不开孔）
    for (x, y) in grid_points(P.BASE_X / 2 - 8, P.BASE_Y / 2 - 8):
        if abs(x) < P.SERVO_L / 2 + 3 and abs(y) < P.SERVO_W / 2 + 3:
            continue
        part -= _hole(P.M3_CLR, P.PLATE_T, x, y, -P.PLATE_T)

    # 角柱顶部 M3 热熔螺母底孔
    for sx in (-1, 1):
        for sy in (-1, 1):
            part -= _hole(P.M3_INSERT_D, P.M3_INSERT_H,
                          sx * P.POST_XY, sy * P.POST_XY, Z_POST_TOP - P.M3_INSERT_H)
    return part


# ------------------------------------------------------------------ 2. 盖板
def joint_lid():
    part = Pos(0, 0, Z_LID_BOT + P.LID_T / 2) * Box(P.BASE_X, P.BASE_Y, P.LID_T)

    # 输出盘让位孔（不是"刚好一样大"，是 +0.6 单边留空）
    part -= _hole(P.DISC_D + 0.6, P.LID_T, 0, 0, Z_LID_BOT)

    # 四角压紧螺钉
    for sx in (-1, 1):
        for sy in (-1, 1):
            part -= _hole(P.M3_CLR, P.LID_T, sx * P.POST_XY, sy * P.POST_XY, Z_LID_BOT)

    # 顶面 20mm 网格：给下一节 / 传感器支架
    for (x, y) in grid_points(P.BASE_X / 2 - 8, P.BASE_Y / 2 - 8):
        if math.hypot(x, y) < P.DISC_D / 2 + 4:
            continue
        part -= _hole(P.M3_CLR, P.LID_T, x, y, Z_LID_BOT)
    return part


# ------------------------------------------------------------------ 3. 输出盘
def output_disc():
    """直接坐在花键上，用原厂 M3x6 螺钉锁住；凸台穿出盖板孔。"""
    boss = _cyl(P.DISC_BOSS_D, Z_FLANGE_BOT - Z_DISC_BOT, 0, 0, Z_DISC_BOT)
    flange = _cyl(P.DISC_D, P.DISC_T, 0, 0, Z_FLANGE_BOT)
    part = boss.fuse(flange)

    # 25T 花键插座：Ø6.1，深度 = 花键高 + 0.4 余量
    part -= _cyl(6.1, P.SERVO_SPLINE_H + 0.4, 0, 0, Z_DISC_BOT - 0.3)
    # 中心 M3 螺钉：Ø3.2 通孔 + Ø6 沉头（从法兰顶面往下）
    part -= _hole(3.2, Z_DISC_TOP - Z_LID_TOP, 0, 0, Z_LID_TOP)
    part -= _cyl(6.0, 2.0, 0, 0, Z_DISC_TOP - 2.0)

    r = P.DISC_BC_D / 2
    for k in range(P.DISC_BOLTS):
        a = math.radians(45 + 90 * k)
        part -= _hole(P.M3_CLR, P.DISC_T, r * math.cos(a), r * math.sin(a), Z_FLANGE_BOT)
    return part


# ------------------------------------------------------------------ 4. 连杆
def link_bar(length: float = P.LINK_L):
    part = Pos(0, 0, P.PLATE_T / 2) * Box(length, P.LINK_W, P.PLATE_T)
    n = int((length / 2 - 8) // P.GRID)
    for i in range(-n, n + 1):
        part -= _hole(P.M3_CLR, P.PLATE_T, i * P.GRID, 0, 0)
    return part


# ------------------------------------------------------------------ 5. 轮毂
def wheel_hub():
    part = _cyl(P.WHEEL_D, P.WHEEL_T, 0, 0, 0)
    part -= _hole(3.2, P.WHEEL_T, 0, 0, 0)

    r = P.DISC_BC_D / 2
    for k in range(P.DISC_BOLTS):
        a = math.radians(45 + 90 * k)
        part -= _hole(P.M3_CLR, P.WHEEL_T, r * math.cos(a), r * math.sin(a), 0)

    for k in range(6):
        a = math.radians(60 * k)
        part -= _hole(4.5, P.WHEEL_T, 22 * math.cos(a), 22 * math.sin(a), 0)
    return part


ALL_PARTS = {
    "joint_base": joint_base,
    "joint_lid": joint_lid,
    "output_disc": output_disc,
    "link_bar": link_bar,
    "wheel_hub": wheel_hub,
}

MATERIAL = {
    "joint_base": "PETG，4 层壁 / 40% 填充",
    "joint_lid": "PETG，3 层壁",
    "output_disc": "PETG-CF 或 PETG，60% 填充（受扭矩件）",
    "link_bar": "PETG，4 层壁 / 30% 填充",
    "wheel_hub": "PETG，50% 填充",
}