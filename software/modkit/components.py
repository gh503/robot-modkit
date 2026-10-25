"""可自由组装的组件库：统一的机械/电气端口 + 质量/功率/载荷元数据。

这一层只描述"组件是什么、能和谁接、接在哪里"，不依赖 build123d，
所以没有 CAD 环境也能在 CI 里验证装配图。

坐标约定
--------
* 每个组件局部坐标：原点在**底部安装面中心**，+Z 朝组件"向上"的方向。
* 端口 frame 也用 +Z 朝上的右手系；两个端口对接时直接对齐 frame，
  不额外翻转 180°（翻转只会让链式装配的 Y 方向莫名其妙地镜像）。
* 网格端口用 ``grid=(宽, 深)`` 表示可用的 20mm 孔阵范围；装配时用
  ``at=[dx, dy]`` 选孔位，必须是 20mm 的整数倍且落在范围内。

证据等级
--------
``validated``：有现成 CAD/测试或已用于 M1；``preview``：有参数化几何但未实物；
``concept``：只定义接口/质量/功率，CAD 待补。不要把 concept 当成已验证。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Iterable

from . import protocol as p

# ---------------------------------------------------------------- 4x4 刚体变换
Mat = tuple[tuple[float, float, float, float], ...]


def mat_identity() -> Mat:
    return ((1.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0))


def mat_mul(a: Mat, b: Mat) -> Mat:
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4))
                 for i in range(4))


def mat_apply(m: Mat, x: float, y: float, z: float) -> tuple[float, float, float]:
    return (m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3],
            m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3],
            m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3])


def mat_inv_rigid(m: Mat) -> Mat:
    """刚体矩阵求逆：R^T, -R^T t。"""
    r = tuple(tuple(m[j][i] for j in range(3)) for i in range(3))
    t = (m[0][3], m[1][3], m[2][3])
    inv_t = tuple(-sum(r[i][j] * t[j] for j in range(3)) for i in range(3))
    return ((r[0][0], r[0][1], r[0][2], inv_t[0]),
            (r[1][0], r[1][1], r[1][2], inv_t[1]),
            (r[2][0], r[2][1], r[2][2], inv_t[2]),
            (0.0, 0.0, 0.0, 1.0))


def mat_rot_x(deg: float) -> Mat:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return ((1, 0, 0, 0), (0, c, -s, 0), (0, s, c, 0), (0, 0, 0, 1))


def mat_rot_y(deg: float) -> Mat:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return ((c, 0, s, 0), (0, 1, 0, 0), (-s, 0, c, 0), (0, 0, 0, 1))


def mat_rot_z(deg: float) -> Mat:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return ((c, -s, 0, 0), (s, c, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))


@dataclass(frozen=True)
class Transform:
    """位置 mm + 欧拉角 XYZ（度）；矩阵按 Rz·Ry·Rx 组合。"""
    pos: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rot: tuple[float, float, float] = (0.0, 0.0, 0.0)

    def matrix(self) -> Mat:
        x, y, z = self.pos
        rx, ry, rz = self.rot
        m = mat_identity()
        m = mat_mul(m, mat_rot_z(rz))
        m = mat_mul(m, mat_rot_y(ry))
        m = mat_mul(m, mat_rot_x(rx))
        m = mat_mul(((1, 0, 0, x), (0, 1, 0, y), (0, 0, 1, z), (0, 0, 0, 1)), m)
        return m

    def as_list(self) -> list[float]:
        return [*self.pos, *self.rot]


def T(x: float = 0, y: float = 0, z: float = 0,
      rx: float = 0, ry: float = 0, rz: float = 0) -> Transform:
    return Transform((float(x), float(y), float(z)), (float(rx), float(ry), float(rz)))


# ---------------------------------------------------------------- 端口
@dataclass(frozen=True)
class Port:
    name: str
    kind: str
    transform: Transform = T()
    gender: str = "neutral"
    grid: tuple[float, float] | None = None
    max_uses: int = 1
    note: str = ""

    def compatible(self, other: "Port") -> bool:
        if self.kind != other.kind:
            return False
        # 网格面是对称孔阵，任意两块都能接；单端口必须一公一母或中性。
        if self.kind in ("mech.grid",):
            return True
        if self.gender == "neutral" or other.gender == "neutral":
            return True
        return self.gender != other.gender

    def as_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind, "gender": self.gender,
                "transform": self.transform.as_list(),
                "grid": list(self.grid) if self.grid else None,
                "max_uses": self.max_uses, "note": self.note}


# ---------------------------------------------------------------- 规格
@dataclass(frozen=True)
class BomItem:
    name: str
    spec: str
    qty: int
    unit_cost: float
    mass_g: float = 0.0
    category: str = "printed"

    def as_dict(self) -> dict:
        return {"name": self.name, "spec": self.spec, "qty": self.qty,
                "unit_cost": round(self.unit_cost, 2),
                "mass_g": round(self.mass_g * self.qty, 1), "category": self.category}


@dataclass(frozen=True)
class PowerSpec:
    voltage_v: float = 12.0
    idle_a: float = 0.0
    peak_a: float = 0.0
    supply_a: float = 0.0       # >0 表示这是电源，不是负载

    def as_dict(self) -> dict:
        return {"voltage_v": self.voltage_v, "idle_a": self.idle_a,
                "peak_a": self.peak_a, "supply_a": self.supply_a}


@dataclass(frozen=True)
class JointSpec:
    name: str
    min_value: float
    max_value: float
    unit: str = "deg"
    zero_ticks: int = 2048
    direction: int = 1
    ticks_per_unit: float = 1.0 / p.DEG_PER_TICK
    max_step: float = 45.0
    rated_torque_nm: float = 2.94
    mode: str = "position"       # position | speed
    center: tuple[float, float, float] = (0.0, 0.0, 30.0)

    def as_dict(self) -> dict:
        return {"name": self.name, "min": self.min_value, "max": self.max_value,
                "unit": self.unit, "zero_ticks": self.zero_ticks,
                "dir": self.direction, "ticks_per_unit": self.ticks_per_unit,
                "max_step": self.max_step, "rated_torque_nm": self.rated_torque_nm,
                "mode": self.mode, "center": list(self.center)}


@dataclass(frozen=True)
class ToolSpec:
    tip: Transform
    max_payload_g: float = 100.0
    kind: str = "gripper"

    def as_dict(self) -> dict:
        return {"tip": self.tip.as_list(), "max_payload_g": self.max_payload_g,
                "kind": self.kind}


@dataclass(frozen=True)
class Component:
    id: str
    name: str
    category: str
    status: str
    description: str
    dims: tuple[float, float, float]
    bbox: tuple[float, float, float, float, float, float]  # xmin,ymin,zmin,xmax,ymax,zmax
    mass_g: float
    cost_cny: float
    ports: tuple[Port, ...] = ()
    bom: tuple[BomItem, ...] = ()
    power: PowerSpec | None = None
    joint: JointSpec | None = None
    tool: ToolSpec | None = None
    support: tuple[tuple[float, float], ...] | None = None
    max_servos: int | None = None
    cad: str | None = None
    tags: tuple[str, ...] = ()
    note: str = ""

    def port(self, name: str) -> Port:
        for p_ in self.ports:
            if p_.name == name:
                return p_
        raise KeyError(f"{self.id}: 没有端口 {name}；可用 {[p_.name for p_ in self.ports]}")

    def as_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "category": self.category,
            "status": self.status, "description": self.description,
            "dims_mm": list(self.dims), "bbox": list(self.bbox),
            "mass_g": self.mass_g, "cost_cny": self.cost_cny,
            "ports": [p_.as_dict() for p_ in self.ports],
            "bom": [b.as_dict() for b in self.bom],
            "power": self.power.as_dict() if self.power else None,
            "joint": self.joint.as_dict() if self.joint else None,
            "tool": self.tool.as_dict() if self.tool else None,
            "support": [list(x) for x in self.support] if self.support else None,
            "max_servos": self.max_servos, "cad": self.cad,
            "tags": list(self.tags), "note": self.note,
        }


# ---------------------------------------------------------------- 注册表
COMPONENTS: dict[str, Component] = {}
CATEGORIES = ("frame", "joint", "link", "adapter", "drive", "tool",
              "sensor", "electronics", "power")


def register(c: Component) -> Component:
    if c.id in COMPONENTS:
        raise ValueError(f"重复组件 {c.id}")
    if c.category not in CATEGORIES:
        raise ValueError(f"{c.id}: 未知类别 {c.category}")
    if c.status not in ("validated", "preview", "concept"):
        raise ValueError(f"{c.id}: 未知证据等级 {c.status}")
    if c.mass_g <= 0 or c.cost_cny < 0:
        raise ValueError(f"{c.id}: 质量/成本必须为正")
    names = [p_.name for p_ in c.ports]
    if len(names) != len(set(names)):
        raise ValueError(f"{c.id}: 端口名重复")
    COMPONENTS[c.id] = c
    return c


def get(component_id: str) -> Component:
    if component_id not in COMPONENTS:
        raise KeyError(f"未知组件 {component_id}；用 `modkit components` 查看"
                       f"（共 {len(COMPONENTS)} 个）")
    return COMPONENTS[component_id]


def by_category(category: str | None = None) -> list[Component]:
    rows = sorted(COMPONENTS.values(), key=lambda c: (c.category, c.id))
    return [c for c in rows if category is None or c.category == category]


def registry_problems() -> list[str]:
    """自检：注册表本身的接口一致性（不装配）。"""
    out: list[str] = []
    for c in COMPONENTS.values():
        if c.status == "validated" and not c.cad:
            out.append(f"{c.id}: validated 但没有 CAD 映射")
        if c.joint and not any(p_.kind == "mech.grid" or p_.kind == "mech.disc" for p_ in c.ports):
            out.append(f"{c.id}: 有 joint 但没有机械安装端口")
        if c.tool and not any(p_.kind.startswith("mech.") for p_ in c.ports):
            out.append(f"{c.id}: 有 tool 但没有安装端口")
        for p_ in c.ports:
            if p_.kind == "mech.grid" and not p_.grid:
                out.append(f"{c.id}.{p_.name}: grid 端口缺 grid 范围")
            if p_.max_uses < 1:
                out.append(f"{c.id}.{p_.name}: max_uses < 1")
    return out


# ---------------------------------------------------------------- 通用零件构造函数
def _printed(name: str, spec: str, qty: int, cost: float, mass: float) -> BomItem:
    return BomItem(name, spec, qty, cost, mass, "printed")


def _purchased(name: str, spec: str, qty: int, cost: float, mass: float = 0.0) -> BomItem:
    return BomItem(name, spec, qty, cost, mass, "purchased")


def _servo_item() -> BomItem:
    return _purchased("总线舵机", "ST-3215-C018 12V/30kg·cm", 1, 115.0, 55.0)


# ================================================================ 结构
def _chassis(cid: str, name: str, x: float, y: float, top: tuple[float, float],
             support: tuple[tuple[float, float], ...], mass: float, cost: float,
             status: str = "preview", drive_y: float = 50.0,
             caster_x: float = 90.0) -> Component:
    return register(Component(
        cid, name, "frame", status,
        f"{x:.0f}×{y:.0f}mm 差速底盘，20mm 网格；含驱动/万向轮安装口。",
        (x, y, 5.0), (-x / 2, -y / 2, -5.0, x / 2, y / 2, 0.0),
        mass, cost,
        ports=(
            Port("top", "mech.grid", T(0, 0, 0), grid=top, max_uses=40),
            Port("drive_left", "mech.disc", T(0, drive_y, -5), "male"),
            Port("drive_right", "mech.disc", T(0, -drive_y, -5), "male"),
            Port("caster_front", "mech.grid", T(caster_x, 0, -5), grid=(20, 20), max_uses=1),
            Port("caster_rear", "mech.grid", T(-caster_x, 0, -5), grid=(20, 20), max_uses=1),
            Port("power_in", "elec.power", T(-x / 2 + 20, 0, -2), "female"),
        ),
        bom=(_printed("底盘板", "5mm 亚克力/PETG", 3, 20.0, 180.0),
             _purchased("M3 螺钉/螺母", "M3×10/12", 1, 20.0)),
        power=PowerSpec(12, 0.0, 0.0),
        support=support,
        cad="chassis",
        tags=("differential", "base"),
    ))


_chassis("frame.chassis_240", "标准差速底盘 240×200", 240, 200, (200, 160),
         ((-90, 0), (0, -75), (0, 75), (90, 0)), 260.0, 65.0, "validated",
         drive_y=50.0, caster_x=90.0)
_chassis("frame.chassis_160", "小差速底盘 160×140", 160, 140, (140, 100),
         ((-60, 0), (0, -55), (0, 55), (60, 0)), 180.0, 45.0,
         drive_y=45.0, caster_x=60.0)

register(Component(
    "frame.deck_120x80", "通用甲板 120×80", "frame", "preview",
    "带 20mm 网格的平板，可做桌面云台/传感器塔底座。",
    (120, 80, 4), (-60, -40, -4, 60, 40, 0), 55, 15,
    ports=(Port("top", "mech.grid", T(0, 0, 0), grid=(100, 60), max_uses=24),
           Port("bottom", "mech.grid", T(0, 0, -4), grid=(100, 60), max_uses=24)),
    bom=(_printed("甲板", "4mm PETG", 1, 15.0, 55.0),), cad="plate",
    support=((-60, -40), (60, -40), (60, 40), (-60, 40))))

register(Component(
    "frame.deck_160x100", "大甲板 160×100", "frame", "preview",
    "比 120×80 多一排孔，适合树莓派/电池同板。",
    (160, 100, 4), (-80, -50, -4, 80, 50, 0), 85, 22,
    ports=(Port("top", "mech.grid", T(0, 0, 0), grid=(140, 80), max_uses=32),
           Port("bottom", "mech.grid", T(0, 0, -4), grid=(140, 80), max_uses=32)),
    bom=(_printed("甲板", "4mm PETG", 1, 22.0, 85.0),), cad="plate",
    support=((-80, -50), (80, -50), (80, 50), (-80, 50))))

register(Component(
    "frame.mast_100", "立柱 100mm", "frame", "preview",
    "20×20 方管立柱，两端 4×M3 网格；抬高相机/云台。",
    (20, 20, 100), (-10, -10, 0, 10, 10, 100), 22, 8,
    ports=(Port("mount", "mech.grid", T(0, 0, 0), grid=(20, 20), max_uses=1),
           Port("top", "mech.grid", T(0, 0, 100), grid=(20, 20), max_uses=1)),
    bom=(_printed("立柱", "20×20 PETG", 1, 8.0, 22.0),), cad="beam"))

register(Component(
    "frame.mast_200", "立柱 200mm", "frame", "preview",
    "高立柱；用于俯视相机或第二层甲板。",
    (20, 20, 200), (-10, -10, 0, 10, 10, 200), 42, 14,
    ports=(Port("mount", "mech.grid", T(0, 0, 0), grid=(20, 20), max_uses=1),
           Port("top", "mech.grid", T(0, 0, 200), grid=(20, 20), max_uses=1)),
    bom=(_printed("立柱", "20×20 PETG", 1, 14.0, 42.0),), cad="beam"))

# ================================================================ 关节
def _joint(cid: str, name: str, js: JointSpec, mass: float = 145.0,
           description: str = "标准总线关节模块：底座+盖板+输出盘，浅槽限位。") -> Component:
    return register(Component(
        cid, name, "joint", "validated", description,
        (60, 60, 40), (-30, -30, 0, 30, 30, 40), mass, 150,
        ports=(
            Port("mount", "mech.grid", T(0, 0, 0), grid=(40, 40), max_uses=1),
            Port("out", "mech.disc", T(0, 0, 40), "male"),
            Port("lid", "mech.grid", T(0, 0, 35.4), grid=(44, 44), max_uses=4,
                 note="固定盖板顶面；中心输出盘会转，传感器支架要避开中心"),
            Port("bus_in", "elec.bus", T(-31, 0, 20), "female"),
            Port("bus_out", "elec.bus", T(31, 0, 20), "male"),
        ),
        bom=(_servo_item(),
             _printed("关节底座", "PETG 4 层壁", 1, 8.0, 38.0),
             _printed("关节盖板", "PETG", 1, 4.0, 20.0),
             _printed("输出盘", "PETG 60%", 1, 5.0, 18.0),
             _purchased("M3 紧固件", "M3×8/10/12", 1, 8.0)),
        power=PowerSpec(12, 0.03, 2.5),
        joint=js, cad="joint", tags=("servo", "position") if js.mode == "position" else ("servo", "speed"),
    ))


_joint("joint.yaw", "偏航关节", JointSpec("yaw", -120, 120, max_step=45))
_joint("joint.pitch", "俯仰/肩关节", JointSpec("shoulder", -25, 100, max_step=45))
_joint("joint.elbow", "肘关节", JointSpec("elbow", -150, 5, direction=-1, max_step=60))
_joint("joint.generic", "通用关节", JointSpec("joint", -90, 90, max_step=45),
       description="未命名的通用位置关节；装配时可覆盖名称/限位。")
_joint("joint.continuous", "连续旋转关节", JointSpec(
    "wheel", -180, 180, max_step=3600, mode="speed", rated_torque_nm=2.94),
    description="恒速模式；用于轮子或连续云台，不做位置限位联锁。")

# ================================================================ 转接/连杆
register(Component(
    "adapter.disc_grid", "输出盘→网格转接板", "adapter", "preview",
    "把 4×M3 输出盘转成 20mm 网格；自由拼装最常用的转接件。",
    (40, 40, 8), (-20, -20, 0, 20, 20, 8), 25, 8,
    ports=(Port("mount", "mech.disc", T(0, 0, 0), "female"),
           Port("out", "mech.grid", T(0, 0, 8), grid=(40, 40), max_uses=4)),
    bom=(_printed("转接板", "PETG 4 层壁", 1, 8.0, 25.0),), cad="plate"))

register(Component(
    "adapter.grid_disc", "网格→输出盘转接板", "adapter", "preview",
    "反方向转接：把网格面接到舵机输出盘。",
    (40, 40, 8), (-20, -20, 0, 20, 20, 8), 25, 8,
    ports=(Port("mount", "mech.grid", T(0, 0, 0), grid=(40, 40), max_uses=1),
           Port("out", "mech.disc", T(0, 0, 8), "female")),
    bom=(_printed("转接板", "PETG 4 层壁", 1, 8.0, 25.0),), cad="plate"))


def _beam(length: float, cid: str, name: str) -> Component:
    return register(Component(
        cid, name, "link", "preview",
        f"{length:.0f}mm 方梁，两端 4×M3 网格；长度可换，孔距仍是 20mm。",
        (20, 20, length), (-10, -10, 0, 10, 10, length), 18 + length * 0.28, 6 + length * 0.09,
        ports=(Port("mount", "mech.grid", T(0, 0, 0), grid=(20, 20), max_uses=1),
               Port("out", "mech.grid", T(0, 0, length), grid=(20, 20), max_uses=1)),
        bom=(_printed("方梁", f"{length:.0f}mm PETG", 1, 6 + length * 0.09, 18 + length * 0.28),),
        cad="beam"))


_beam(60, "link.beam_60", "方梁 60mm")
_beam(100, "link.beam_100", "方梁 100mm")
_beam(140, "link.beam_140", "方梁 140mm")
_beam(200, "link.beam_200", "方梁 200mm")

# ================================================================ 驱动
def _wheel(cid: str, name: str, d: float, mass: float) -> Component:
    return register(Component(
        cid, name, "drive", "preview",
        f"Ø{d:.0f}mm 驱动轮 + 轮毂 + 总线舵机；恒速模式，装在底盘 drive_left/right。",
        (d, 40, d / 2 + 8), (-d / 2, -20, -d / 2 - 8, d / 2, 20, 0), mass, 155,
        ports=(Port("mount", "mech.disc", T(0, 0, 0), "female"),
               Port("bus_in", "elec.bus", T(-d / 2 - 2, 0, -10), "female"),
               Port("bus_out", "elec.bus", T(d / 2 + 2, 0, -10), "male")),
        bom=(_servo_item(), _printed("轮毂", "PETG 50%", 1, 8.0, 22.0),
             _purchased("橡胶轮", f"Ø{d:.0f}mm", 1, 25.0, 45.0)),
        power=PowerSpec(12, 0.03, 2.5),
        joint=JointSpec("wheel", -180, 180, max_step=3600, mode="speed"),
        cad="wheel", tags=("differential", "wheel")))


_wheel("drive.wheel_65", "驱动轮 Ø65", 65, 160)
_wheel("drive.wheel_80", "驱动轮 Ø80", 80, 185)

register(Component(
    "drive.caster", "万向球轮 Ø15", "drive", "preview",
    "15mm 滚珠万向轮；前后各一，形成四点支撑。",
    (30, 30, 30), (-15, -15, -30, 15, 15, 0), 20, 12,
    ports=(Port("mount", "mech.grid", T(0, 0, 0), grid=(20, 20), max_uses=1),),
    bom=(_purchased("万向球轮", "Ø15 滚珠", 1, 12.0, 20.0),), cad="caster"))

# ================================================================ 工具
def _gripper(cid: str, name: str, opening: float, mass: float, cost: float) -> Component:
    return register(Component(
        cid, name, "tool", "preview",
        f"{opening:.0f}mm 平行夹爪；含 1 个位置舵机，夹持力受 0x30 转矩限制。",
        (60, 60, 95), (-30, -30, 0, 30, 30, 95), mass, cost,
        ports=(Port("mount", "mech.grid", T(0, 0, 0), grid=(40, 40), max_uses=1),
               Port("disc", "mech.disc", T(0, 0, 0), "female"),
               Port("tool", "mech.tool", T(0, 30, 65), "male"),
               Port("bus_in", "elec.bus", T(-31, 0, 20), "female"),
               Port("bus_out", "elec.bus", T(31, 0, 20), "male")),
        bom=(_servo_item(), _printed("夹爪定爪", "PETG", 1, 6.0, 30.0),
             _printed("夹爪动爪", "PETG", 1, 6.0, 25.0),
             _printed("关节底座/盖板/输出盘", "PETG", 1, 12.0, 76.0)),
        power=PowerSpec(12, 0.03, 2.5),
        joint=JointSpec("gripper", 0.0, 1.0, unit="ratio",
                        zero_ticks=p.deg_to_ticks(120.0), direction=1,
                        ticks_per_unit=opening / p.DEG_PER_TICK, max_step=0.5,
                        rated_torque_nm=2.94),
        tool=ToolSpec(T(0, 55, 70), max_payload_g=200, kind="gripper"),
        cad="gripper", tags=("gripper", "end_effector")))


_gripper("tool.gripper_40", "平行夹爪 40mm", 40, 230, 170)
_gripper("tool.gripper_70", "宽口夹爪 70mm", 70, 255, 175)

register(Component(
    "tool.pen", "笔夹工具", "tool", "preview",
    "Ø10mm 笔/记号笔夹；用于画线、写标签。",
    (30, 30, 80), (-15, -15, 0, 15, 15, 80), 28, 10,
    ports=(Port("mount", "mech.grid", T(0, 0, 0), grid=(40, 40), max_uses=1),
           Port("disc", "mech.disc", T(0, 0, 0), "female"),
           Port("tool", "mech.tool", T(0, 0, 75), "male")),
    bom=(_printed("笔夹", "PETG", 1, 10.0, 28.0),), cad="plate",
    tool=ToolSpec(T(0, 0, 80), 50, "pen")))

register(Component(
    "tool.vacuum_20", "真空吸盘 Ø20", "tool", "concept",
    "20mm 吸盘 + 12V 微型泵；适合平整纸盒/玻璃，不适合粗糙面。",
    (50, 50, 70), (-25, -25, 0, 25, 25, 70), 110, 95,
    ports=(Port("mount", "mech.grid", T(0, 0, 0), grid=(40, 40), max_uses=1),
           Port("disc", "mech.disc", T(0, 0, 0), "female"),
           Port("tool", "mech.tool", T(0, 0, 60), "male")),
    bom=(_purchased("真空泵", "12V 微型", 1, 55.0, 70.0),
         _purchased("吸盘", "Ø20 硅胶", 1, 8.0, 5.0),
         _printed("泵座", "PETG", 1, 12.0, 35.0)),
    power=PowerSpec(12, 0.0, 0.6),
    tool=ToolSpec(T(0, 0, 70), 150, "vacuum"), cad=None, tags=("vacuum",)))

# ================================================================ 传感器
def _sensor(cid: str, name: str, dims: tuple[float, float, float],
            mass: float, cost: float, desc: str, power: PowerSpec,
            status: str = "concept") -> Component:
    x, y, z = dims
    return register(Component(
        cid, name, "sensor", status, desc,
        dims, (-x / 2, -y / 2, 0, x / 2, y / 2, z), mass, cost,
        ports=(Port("mount", "mech.grid", T(0, 0, 0), grid=(20, 20), max_uses=1),
               Port("data", "elec.data", T(0, 0, z / 2), "female")),
        bom=(_purchased(name, "", 1, cost, mass),),
        power=power, cad=None, tags=("sensor",)))


_sensor("sensor.camera_usb", "USB 相机", (45, 35, 55), 90, 90,
        "1080p 广角 USB 相机 + 俯角支架；5V 供电。", PowerSpec(5, 0.05, 0.25),
        "preview")
_sensor("sensor.tof", "ToF 测距", (22, 16, 12), 10, 18,
        "VL53L1X 类 4m ToF；用于桌面/障碍测距。", PowerSpec(5, 0.01, 0.02))
_sensor("sensor.imu", "IMU 6 轴", (16, 16, 5), 5, 12,
        "MPU6050/ICM 类；偏航漂移大，不能单独当里程计。", PowerSpec(5, 0.005, 0.01))
_sensor("sensor.line_array", "循迹阵列", (60, 22, 12), 15, 25,
        "5 路红外循迹；离地 8–15mm 安装。", PowerSpec(5, 0.02, 0.04))

# ================================================================ 电控/电源
register(Component(
    "electronics.esp32", "ESP32-S3 主控", "electronics", "preview",
    "6 路总线舵机 + USB；3.3V 逻辑，12V 经降压供电。",
    (70, 50, 20), (-35, -25, 0, 35, 25, 20), 55, 45,
    ports=(Port("mount", "mech.grid", T(0, 0, 0), grid=(40, 20), max_uses=1),
           Port("bus_out", "elec.bus", T(35, 0, 10), "male"),
           Port("power_in", "elec.power", T(-35, 0, 10), "female"),
           Port("usb", "elec.data", T(0, -25, 10), "female")),
    bom=(_purchased("ESP32-S3 开发板", "USB-C", 1, 40.0, 20.0),
         _printed("主控托盘", "PETG", 1, 5.0, 35.0)),
    power=PowerSpec(5, 0.08, 0.5), max_servos=6, cad="plate", tags=("controller",)))

register(Component(
    "electronics.buck_5v", "12V→5V 降压 2A", "electronics", "preview",
    "MP1584/LM2596 模块；给主控/相机供电，输入 12V。",
    (40, 25, 16), (-20, -12.5, 0, 20, 12.5, 16), 18, 10,
    ports=(Port("mount", "mech.grid", T(0, 0, 0), grid=(20, 20), max_uses=1),
           Port("power_in", "elec.power", T(-20, 0, 8), "female"),
           Port("power_out", "elec.power", T(20, 0, 8), "male")),
    bom=(_purchased("降压模块", "12V→5V 2A", 1, 10.0, 18.0),),
    power=PowerSpec(12, 0.01, 0.05), cad="plate"))

register(Component(
    "electronics.power_dist", "配电板", "electronics", "preview",
    "12V 端子排 + 保险丝座；单点接地。",
    (70, 50, 20), (-35, -25, 0, 35, 25, 20), 45, 22,
    ports=(Port("mount", "mech.grid", T(0, 0, 0), grid=(40, 20), max_uses=1),
           Port("power_in", "elec.power", T(-35, 0, 10), "female"),
           Port("power_out", "elec.power", T(35, 0, 10), "male")),
    bom=(_purchased("端子排", "5.08mm 2×6", 1, 12.0),
         _purchased("自恢复保险丝", "2A/8A", 1, 10.0, 5.0)),
    power=PowerSpec(12, 0.0, 0.0), cad="plate"))

register(Component(
    "power.adapter_12v5a", "12V/5A 台面电源", "power", "preview",
    "调试用台面适配器；移动构型换 3S 电池。",
    (100, 60, 40), (-50, -30, 0, 50, 30, 40), 300, 45,
    ports=(Port("mount", "mech.grid", T(0, 0, 0), grid=(40, 20), max_uses=1),
           Port("power_out", "elec.power", T(50, 0, 20), "male")),
    bom=(_purchased("12V/5A 适配器", "DC 5.5×2.1", 1, 45.0, 300.0),),
    power=PowerSpec(12, 0.0, 0.0, 5.0), cad=None, tags=("power_source",)))

register(Component(
    "power.battery_3s", "3S 锂电池 2200mAh", "power", "concept",
    "移动构型电源；必须配 BMS/保险丝，禁止直接裸接。",
    (100, 60, 30), (-50, -30, 0, 50, 30, 30), 220, 180,
    ports=(Port("mount", "mech.grid", T(0, 0, 0), grid=(40, 20), max_uses=1),
           Port("power_out", "elec.power", T(50, 0, 15), "male")),
    bom=(_purchased("3S 锂电", "2200mAh + BMS", 1, 180.0, 220.0),),
    power=PowerSpec(12, 0.0, 0.0, 10.0), cad=None, tags=("power_source", "mobile")))

register(Component(
    "power.estop", "急停/总开关面板", "power", "preview",
    "常闭急停串在 12V 总正极；按下即断电。",
    (60, 40, 30), (-30, -20, 0, 30, 20, 30), 40, 18,
    ports=(Port("mount", "mech.grid", T(0, 0, 0), grid=(40, 20), max_uses=1),
           Port("power_in", "elec.power", T(-30, 0, 15), "female"),
           Port("power_out", "elec.power", T(30, 0, 15), "male")),
    bom=(_purchased("急停按钮", "Ø16 常闭", 1, 8.0, 20.0),
         _purchased("保险丝座+5A", "5×20", 1, 5.0, 10.0),
         _printed("面板", "PETG", 1, 5.0, 10.0)),
    power=PowerSpec(12, 0.0, 0.0), cad="plate", tags=("safety",)))

register(Component(
    "compute.pi4", "树莓派 4B", "electronics", "concept",
    "视觉/任务计算；5V 2A，必须独立降压，不能从舵机 5V 取。",
    (90, 60, 30), (-45, -30, 0, 45, 30, 30), 50, 450,
    ports=(Port("mount", "mech.grid", T(0, 0, 0), grid=(40, 40), max_uses=1),
           Port("power_in", "elec.power", T(-45, 0, 15), "female"),
           Port("usb", "elec.data", T(45, 0, 15), "female")),
    bom=(_purchased("树莓派 4B", "2GB", 1, 450.0, 50.0),),
    power=PowerSpec(5, 0.3, 2.0), cad=None))

register(Component(
    "frame.power_bay", "电池仓/扎带板", "frame", "preview",
    "电池扎带槽 + 保险丝座位置；把电池放在底盘后部抵消臂前伸。",
    (110, 70, 6), (-55, -35, 0, 55, 35, 6), 60, 15,
    ports=(Port("mount", "mech.grid", T(0, 0, 0), grid=(80, 40), max_uses=1),
           Port("top", "mech.grid", T(0, 0, 6), grid=(80, 40), max_uses=4)),
    bom=(_printed("电池仓", "PETG", 1, 15.0, 60.0),), cad="plate"))


__all__ = [
    "Mat", "Transform", "T", "Port", "BomItem", "PowerSpec", "JointSpec",
    "ToolSpec", "Component", "COMPONENTS", "CATEGORIES", "register", "get",
    "by_category", "registry_problems", "mat_mul", "mat_apply", "mat_inv_rigid",
    "mat_identity", "mat_rot_x", "mat_rot_y", "mat_rot_z", "json",
]
