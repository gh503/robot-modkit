"""M1 整机零件：底盘（分块）、驱动支架、夹爪（复用关节模块）、相机支架。

设计取舍（都是被自检逼出来的）：
1. 底盘 240×200 超出多数打印床（220）→ 拆成两块 120×200 + 一块 60×200 连接板，
   三块都能打印、也能激光切割。
2. 驱动舵机吊在板下方，用打印支架环抱固定 —— 仍然**不依赖舵机安装孔坐标**。
3. 夹爪不新做一套舵机保持结构，直接复用 joint_base + joint_lid + output_disc，
   换工具只是换爪指。
"""

from __future__ import annotations

import math

from build123d import Align, Axis, Box, Cylinder, Pos, Rot, fillet

import params as P
from parts import Z_LID_TOP, Z_DISC_TOP, _cyl, _hole, grid_points

# ------------------------------------------------------------------ 关键基准
Z_PLATE_BOT = -P.CHASSIS_T                 # 底盘板底面
Z_DRIVE = P.SERVO_Z                        # 驱动舵机中心


# ------------------------------------------------------------------ 驱动舵机包络（检查用，不打印）
def drive_servo_reference(side: int = 1):
    """驱动舵机横躺：输出轴朝 ±Y。机身 45.2(X) × 35(Z) × 24.7(Y)。"""
    return Pos(0, side * P.DRIVE_Y, Z_DRIVE) * Rot(-90, 0, 0) * Box(
        P.SERVO_L, P.SERVO_W, P.SERVO_H
    )


# ------------------------------------------------------------------ 底盘（两半 + 连接板）
def chassis_half(side: int = 1):
    """side=+1 为右半（x 0..120），side=-1 为左半。

    孔位一律按**全局 20mm 网格**布置，所以两半互换、翻转都能对上。
    """
    part = Pos(side * P.CHASSIS_X / 4, 0, Z_PLATE_BOT / 2) * Box(
        P.CHASSIS_X / 2, P.CHASSIS_Y, P.CHASSIS_T
    )

    # 万向球轮（前后各一，装在 x=±90）
    cx = side * P.CASTER_X
    part -= _hole(22.0, P.CHASSIS_T, cx, 0, Z_PLATE_BOT)
    for dy in (-12, 12):
        part -= _hole(P.M3_CLR, P.CHASSIS_T, cx, dy, Z_PLATE_BOT)

    # 驱动支架安装孔：以舵机中心 (0, ±DRIVE_Y) 为基准，x=±20 / y=±10
    for dx in (-20, 20):
        for dy in (-10, 10):
            part -= _hole(P.M3_CLR, P.CHASSIS_T, dx, side * P.DRIVE_Y + dy, Z_PLATE_BOT)

    # 与连接板对接：x = ±30，y = ±40、±60
    for dy in (-60, -40, 40, 60):
        part -= _hole(P.M3_CLR, P.CHASSIS_T, side * 30, dy, Z_PLATE_BOT)

    # 电池扎带槽（左半）
    if side < 0:
        for dx in (-60, -30):
            part -= Pos(dx, 0, 0) * Box(P.BATT_SLOT_W, P.BATT_SLOT_L, P.CHASSIS_T + 2)

    # 通用 20mm 网格（避开舵机、万向轮、连接区）
    for (x, y) in grid_points(P.CHASSIS_X / 2 - 8, P.CHASSIS_Y / 2 - 8):
        if x * side <= 0:                       # 只在该半边
            continue
        if abs(abs(x) - P.CASTER_X) < 20 and abs(y) < 20:
            continue
        if abs(y - side * P.DRIVE_Y) < 22 and abs(x) < 30:
            continue
        if abs(abs(x) - 30) < 12 and abs(y) > 26:
            continue
        part -= _hole(P.M3_CLR_FIT, P.CHASSIS_T, x, y, Z_PLATE_BOT)

    # 线缆过孔
    part -= _hole(12.0, P.CHASSIS_T, side * 70, 0, Z_PLATE_BOT)
    return part


def chassis_joiner():
    """中间连接板：跨接两半，8 个 M3 位。"""
    part = Pos(0, 0, Z_PLATE_BOT / 2) * Box(60, P.CHASSIS_Y, P.CHASSIS_T)
    for dy in (-60, -40, 40, 60):
        for dx in (-30, 30):
            part -= _hole(P.M3_CLR_FIT, P.CHASSIS_T, dx, dy, Z_PLATE_BOT)
    part -= _hole(14.0, P.CHASSIS_T, 0, 0, Z_PLATE_BOT)
    return part


# ------------------------------------------------------------------ 驱动支架
def drive_bracket():
    """环抱驱动舵机的 U 形支架：顶板贴底盘下方，两侧腿夹住机身。"""
    z_top = Z_PLATE_BOT
    part = Pos(0, 0, z_top - 2) * Box(60, 44, 4)

    leg_h = 31.0
    for sy in (-1, 1):
        part += Pos(0, sy * 14.75, z_top - 4 - leg_h / 2) * Box(52, 4, leg_h)
        # 底部托盘：舵机整个重量由这两条翻边承担（不是靠夹紧）
        part += Pos(0, sy * 10.75, Z_DRIVE - P.SERVO_W / 2 - 2) * Box(52, 8, 4)

    for dx in (-20, 20):
        for dy in (-10, 10):
            part -= _hole(P.M3_CLR, 4, dx, dy, z_top - 4)
    return part


# ------------------------------------------------------------------ 夹爪
def jaw_fixed():
    """定爪：装在盖板顶面（-Y 侧）。螺钉只钻 4mm 基座，不碰爪壁。"""
    z0 = Z_LID_TOP
    base = Pos(0, -19, z0 + 2) * Box(48, 10, 4)
    wall = Pos(0, -22, z0 + 4 + P.JAW_H / 2) * Box(P.JAW_W, P.JAW_T, P.JAW_H)
    part = base + wall

    for dx in (0, -P.GRID, P.GRID):
        part -= _hole(P.M3_CLR, 4, dx, -20, z0)
    return part


def jaw_moving(swing_deg: float = 0.0):
    """动爪：装在输出盘上，绕盘心摆动。0° 全开，JAW_SWING 全闭。"""
    z0 = Z_DISC_TOP
    base = Pos(0, 8, z0 + 2) * Box(34, 30, 4)
    wall = Pos(0, 24, z0 + 4 + P.JAW_H / 2) * Box(P.JAW_W, P.JAW_T, P.JAW_H)
    part = base + wall

    r = P.DISC_BC_D / 2
    for k in range(P.DISC_BOLTS):
        a = math.radians(45 + 90 * k)
        part -= _hole(P.M3_CLR, 4, r * math.cos(a), r * math.sin(a), z0)
    part -= _hole(7.0, 4, 0, 0, z0)      # 舵机中心螺钉头让位

    return Rot(0, 0, -swing_deg) * part if swing_deg else part


def jaw_inner_y(swing_deg: float) -> float:
    """动爪内侧面的 y 坐标（解析值，不用 bbox 猜）。"""
    y_inner = P.JAW_GAP_OPEN / 2
    return y_inner * math.cos(math.radians(swing_deg))


def jaw_gap(swing_deg: float) -> float:
    return jaw_inner_y(swing_deg) + P.JAW_GAP_OPEN / 2


# ------------------------------------------------------------------ 相机支架
def camera_mount():
    base = Pos(0, 0, 2.5) * Box(P.CAM_BASE_X, P.CAM_BASE_Y, 5)
    plate_len = 60.0
    tilt = P.CAM_TILT - 90
    plate = Pos(0, P.CAM_BASE_Y / 2 - 2, 5) * Rot(tilt, 0, 0) * Box(P.CAM_BASE_X, plate_len, 4)
    part = base + plate

    part -= Pos(0, P.CAM_BASE_Y / 2 - 2, 5) * Rot(tilt, 0, 0) * _cyl(P.CAM_HOLE, 30, 0, 10, 0)
    for dx in (-16, 16):
        part -= Pos(dx, P.CAM_BASE_Y / 2 - 2, 5) * Rot(tilt, 0, 0) * Box(4.2, 26, 30)

    for dx in (-P.GRID, P.GRID):
        for dy in (-10, 10):
            part -= _hole(P.M3_CLR, 5, dx, dy, 0)
    return part


ALL_PARTS_M1 = {
    "chassis_right": lambda: chassis_half(+1),
    "chassis_left": lambda: chassis_half(-1),
    "chassis_joiner": chassis_joiner,
    "drive_bracket": drive_bracket,
    "jaw_fixed": jaw_fixed,
    "jaw_moving": jaw_moving,
    "camera_mount": camera_mount,
}

MATERIAL_M1 = {
    "chassis_right": "5mm 亚克力/玻纤；打印则 PETG 6 层壁",
    "chassis_left": "同上",
    "chassis_joiner": "同上",
    "drive_bracket": "PETG，5 层壁 60% 填充（承整机重量与扭矩反力）",
    "jaw_fixed": "PETG，4 层壁 50% 填充",
    "jaw_moving": "PETG，4 层壁 50% 填充",
    "camera_mount": "PETG，3 层壁",
}