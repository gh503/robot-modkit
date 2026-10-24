"""modkit 全局参数 —— 单一真源（Single Source of Truth）

原则：
1. 所有尺寸只在这里定义一次，零件脚本不写魔术数字。
2. 每个尺寸标注证据等级：
   [DS] 官方规格书/官网原文（可引用）
   [TODO] 标称值，未经实物卡尺验证 —— 装配前必须复核
   [DESIGN] 本设计自定（公差、壁厚、网格），改它需要重新评审
3. 改尺寸后跑 `python cad/build.py`，自检脚本会把越界/干涉打出来。
"""

# ---------------------------------------------------------------- 舵机 ST-3215-C018
# 来源：ftservo-wiki 型号页（核对日期 2026-10-02）
SERVO_L = 45.2      # [DS] 尺寸 A
SERVO_W = 24.7      # [DS] 尺寸 B
SERVO_H = 35.0      # [DS] 尺寸 C（不含出力轴）
SERVO_SPLINE_OD = 5.9   # [DS] 出力轴花键外径 25T
SERVO_SPLINE_H = 2.0    # [TODO] 花键露出高度（图纸未给，按 2.0 建，实物复核）
SERVO_HORN_SCREW = "M3x6"   # [DS] 出力轴螺丝

# ---------------------------------------------------------------- 机械接口（设计自定）
GRID = 20.0          # [DESIGN] 通用孔位网格间距
M3_CLR = 3.4         # [DESIGN] M3 通孔（FDM 打印后收缩，取 +0.2）
M3_CLR_FIT = 3.6     # [DESIGN] 需要容错的对接孔：底盘↔连接板（错位 0.4mm 时仍能装上）
M3_INSERT_D = 4.2    # [DESIGN] M3 热熔铜螺母底孔（M3x5x4 常用规格）
M3_INSERT_H = 6.0    # [DESIGN] 底孔深度（螺母长 4 + 2 容渣）
M2_SELF_TAP_D = 1.9  # [DESIGN] M2 自攻底孔（打印件）
PLATE_T = 4.0        # [DESIGN] 主结构板厚
LID_T = 3.0          # [DESIGN] 盖板厚
FIT_CLR = 0.4        # [DESIGN] 舵机与腔体的单边总间隙（0.2/边，FDM 可保证）
Z_GAP = 0.4          # [DESIGN] 舵机顶面与盖板之间的间隙

# ---------------------------------------------------------------- 关节模块外壳
BASE_X = 60.0        # [DESIGN] 底板 X 尺寸
BASE_Y = 60.0        # [DESIGN] 底板 Y 尺寸
POST = 8.0           # [DESIGN] 角柱截面
POST_XY = 26.0       # [DESIGN] 角柱中心位置（±）
SERVO_RECESS = 2.4   # [DESIGN] 舵机定位浅槽深度（保证槽底剩余壁厚 ≥1.6）
CABLE_SLOT_W = 10.0  # [DESIGN] 出线槽宽

# ---------------------------------------------------------------- 输出盘 / 轮毂 / 连杆
DISC_D = 24.0        # [DESIGN] 输出盘直径
DISC_T = 4.0         # [DESIGN] 输出盘法兰厚
DISC_BOSS_D = 12.0   # [DESIGN] 插入盖板孔的凸台直径
DISC_BOSS_T = 2.5    # [DESIGN] 凸台高（要够到花键）
DISC_BC_D = 16.0     # [DESIGN] 输出盘螺栓分布圆直径
DISC_BOLTS = 4       # [DESIGN] 螺栓数

WHEEL_D = 56.0       # [DESIGN] 轮毂直径
WHEEL_T = 8.0        # [DESIGN] 轮毂厚

LINK_L = 100.0       # [DESIGN] 标准连杆长度
LINK_W = 20.0        # [DESIGN] 连杆宽
LINK_T = 6.0         # [DESIGN] 连杆厚（4mm 时 200g 载荷挠度 4mm，超差；6mm 降到 1.2mm）

# ---------------------------------------------------------------- 打印 / 设备约束
PRINTER_BED = (220.0, 220.0, 250.0)   # [DESIGN] 目标打印机成形空间（Bambu A1 mini 级别）
MIN_WALL = 1.2       # [DESIGN] FDM 最小可靠壁厚（0.4 喷嘴 ×3）

# ---------------------------------------------------------------- 采购与电气（详见 docs/02）
BUS_VOLTAGE = 12.0   # [DS] 额定工作电压
BUS_BAUD = 1_000_000 # [DS] 出厂默认波特率（内存表地址 0x06 = 0）
BUS_BAUD_IDX_115200 = 4  # [DS] 波特率索引表：0=1M,1=500k,2=250k,3=128k,4=115200
# ================================================================ M1 整机（底盘 / 夹爪 / 相机）
# ---------------------------------------------------------------- 底盘
CHASSIS_X = 240.0    # [DESIGN] 底盘长
CHASSIS_Y = 200.0    # [DESIGN] 底盘宽
CHASSIS_T = 5.0      # [DESIGN] 底盘板厚
CHASSIS_SPLIT = True # [DESIGN] True = 分两块打印（240 超出多数打印床）
DRIVE_Y = 50.0       # [DESIGN] 驱动舵机中心 |y|（轮子在 y=±75，轮距 150）
WHEEL_Y = 75.0       # [DESIGN] 轮平面 |y| → TRACK = 150
SERVO_Z = -22.5      # [DESIGN] 驱动舵机中心 z（吊在底盘板下方，板底 z=-5）
WHEEL_R = 32.5       # [DESIGN] 轮半径（Ø65 轮）
CASTER_X = 90.0      # [DESIGN] 万向球轮 |x| 位置
BATT_SLOT_W = 5.0    # [DESIGN] 电池扎带槽宽
BATT_SLOT_L = 70.0   # [DESIGN] 扎带槽长
ARM_ORIGIN_X = 20.0  # [DESIGN] 臂底座中心在底盘上的 x 偏移（靠后，给前方相机留位）

# ---------------------------------------------------------------- 夹爪（复用关节模块：底座+舵机+盖板）
JAW_T = 6.0          # [DESIGN] 夹爪壁厚
JAW_H = 60.0         # [DESIGN] 夹爪高度
JAW_W = 40.0         # [DESIGN] 夹爪宽度
JAW_GAP_OPEN = 40.0  # [DESIGN] 全开内距
JAW_SWING = 70.0     # [DESIGN] 动爪最大摆角（度）→ 全闭内距约 27mm
FINGER_PAD_T = 3.0   # [DESIGN] 指尖软胶垫厚度（不计入打印件）

# ---------------------------------------------------------------- 相机支架
CAM_BASE_X = 60.0    # [DESIGN]
CAM_BASE_Y = 50.0    # [DESIGN]
CAM_TILT = 55.0      # [DESIGN] 俯角（度）
CAM_HOLE = 14.0      # [DESIGN] 镜头孔
