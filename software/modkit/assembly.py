"""装配图：从组件库拼机器人，并在生成 BOM/CAD 前做结构、功率、稳定性检查。

设计目标
--------
* **自由拼装**：组件只通过端口连接，不把 M1 的尺寸写死。
* **失败可解释**：每个错误都有组件 id、端口、原因；不是一句"装配失败"。
* **不冒充 CAD**：碰撞用有向包围盒（OBB 的保守 AABB 版本）粗查；文档
  明确它不是网格碰撞。真正的干涉仍要回 CAD。
* **能交给安全层**：为位置关节生成 ``safety.json`` / 标定模板，直接接
  v1.4 的 ``SafetyPolicy``。

装配 JSON 最小例子::

    {
      "name": "demo",
      "components": [
        {"id": "base", "type": "frame.chassis_240"},
        {"id": "yaw", "type": "joint.yaw", "parent": "base", "port": "top",
         "at": [20, 0], "servo_id": 1}
      ]
    }
"""

from __future__ import annotations

import csv
import html
import json
import math
import pathlib
from dataclasses import dataclass, field, replace
from typing import Any, Iterable

from . import components as C

ERROR = "error"
WARN = "warn"
INFO = "info"


class AssemblyError(ValueError):
    """装配 JSON 本身不合法（不是"装得不对"，而是读不进来）。"""


@dataclass(frozen=True)
class Issue:
    level: str
    code: str
    message: str
    instance: str = ""

    def as_dict(self) -> dict:
        return {"level": self.level, "code": self.code,
                "message": self.message, "instance": self.instance}


@dataclass
class Instance:
    id: str
    type: str
    parent: str | None = None
    parent_port: str | None = None
    child_port: str = "mount"
    at: tuple[float, float] = (0.0, 0.0)
    spin: float = 0.0
    rot: tuple[float, float, float] = (0.0, 0.0, 0.0)
    pose: tuple[float, ...] | None = None
    servo_id: int | None = None
    offboard: bool = False
    joint_override: dict[str, Any] | None = None
    world: C.Mat | None = None
    component: C.Component | None = None

    @property
    def comp(self) -> C.Component:
        if self.component is None:
            raise AssemblyError(f"{self.id}: 未解析组件类型 {self.type}")
        return self.component

    def as_dict(self) -> dict:
        d: dict[str, Any] = {"id": self.id, "type": self.type, "parent": self.parent,
                             "port": self.parent_port, "child_port": self.child_port,
                             "at": list(self.at), "spin": self.spin,
                             "rot": list(self.rot)}
        if self.servo_id is not None:
            d["servo_id"] = self.servo_id
        if self.offboard:
            d["offboard"] = True
        if self.world is not None:
            d["world"] = _mat_pose(self.world)
        return d


@dataclass
class BomLine:
    name: str
    spec: str
    qty: int
    unit_cost: float
    mass_g: float
    category: str

    @property
    def cost(self) -> float:
        return self.qty * self.unit_cost

    def as_dict(self) -> dict:
        return {"name": self.name, "spec": self.spec, "qty": self.qty,
                "unit_cost": round(self.unit_cost, 2),
                "cost": round(self.cost, 2), "mass_g": round(self.mass_g, 1),
                "category": self.category}


@dataclass
class PowerResult:
    supply_a: float
    idle_a: float
    peak_a: float
    planning_a: float
    sources: list[str] = field(default_factory=list)
    ok: bool = True

    def as_dict(self) -> dict:
        return {"supply_a": round(self.supply_a, 2), "idle_a": round(self.idle_a, 2),
                "peak_a": round(self.peak_a, 2), "planning_a": round(self.planning_a, 2),
                "sources": self.sources, "ok": self.ok}


@dataclass
class Stability:
    com: tuple[float, float, float] | None
    support: list[tuple[float, float]]
    margin_mm: float | None
    tip_accel_m_s2: float | None
    inside: bool = True

    def as_dict(self) -> dict:
        return {"com": list(self.com) if self.com else None,
                "support": [list(x) for x in self.support],
                "margin_mm": None if self.margin_mm is None else round(self.margin_mm, 1),
                "tip_accel_m_s2": None if self.tip_accel_m_s2 is None else round(self.tip_accel_m_s2, 2),
                "inside": self.inside}


@dataclass
class JointLoad:
    instance: str
    name: str
    servo_id: int
    rated_nm: float
    load_nm: float
    ratio: float
    mass_g: float
    arm_mm: float
    gravity_nm: float = 0.0
    dynamic_nm: float = 0.0
    accel_m_s2: float = 0.0
    margin_nm: float = 0.0
    ok: bool = True

    def as_dict(self) -> dict:
        return {"instance": self.instance, "name": self.name,
                "servo_id": self.servo_id, "rated_nm": round(self.rated_nm, 2),
                "load_nm": round(self.load_nm, 2), "ratio": round(self.ratio, 2),
                "mass_g": round(self.mass_g, 1), "arm_mm": round(self.arm_mm, 1),
                "gravity_nm": round(self.gravity_nm, 2),
                "dynamic_nm": round(self.dynamic_nm, 2),
                "accel_m_s2": round(self.accel_m_s2, 2),
                "margin_nm": round(self.margin_nm, 2), "ok": self.ok}


@dataclass
class Report:
    name: str
    instances: list[Instance]
    issues: list[Issue] = field(default_factory=list)
    bom: list[BomLine] = field(default_factory=list)
    total_mass_g: float = 0.0
    total_cost_cny: float = 0.0
    power: PowerResult | None = None
    stability: Stability | None = None
    joint_loads: list[JointLoad] = field(default_factory=list)
    collision_mesh: list[dict] = field(default_factory=list)
    collision_stats: dict = field(default_factory=dict)
    servo_ids: dict[str, int] = field(default_factory=dict)
    safety: dict | None = None
    calibration: dict | None = None
    payload_g: float = 0.0
    strict: bool = False
    ignore_collision: set[tuple[str, str]] = field(default_factory=set)
    raw: dict | None = None

    @property
    def ok(self) -> bool:
        return not any(x.level == ERROR for x in self.issues)

    @property
    def errors(self) -> list[Issue]:
        return [x for x in self.issues if x.level == ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [x for x in self.issues if x.level == WARN]

    def add(self, level: str, code: str, message: str, instance: str = "") -> None:
        # 同一个问题只记一次；CAD/检查器可能从不同路径撞到同一条件。
        iss = Issue(level, code, message, instance)
        if iss not in self.issues:
            self.issues.append(iss)

    def as_dict(self) -> dict:
        return {
            "name": self.name, "ok": self.ok, "strict": self.strict,
            "payload_g": self.payload_g,
            "instances": [i.as_dict() for i in self.instances],
            "ignore_collision": [list(x) for x in sorted(self.ignore_collision)],
            "issues": [x.as_dict() for x in self.issues],
            "bom": [b.as_dict() for b in self.bom],
            "total_mass_g": round(self.total_mass_g, 1),
            "total_cost_cny": round(self.total_cost_cny, 2),
            "power": self.power.as_dict() if self.power else None,
            "stability": self.stability.as_dict() if self.stability else None,
            "joint_loads": [j.as_dict() for j in self.joint_loads],
            "collision_mesh": self.collision_mesh,
            "collision_stats": self.collision_stats,
            "servo_ids": self.servo_ids,
            "safety": self.safety,
            "calibration": self.calibration,
        }


# ---------------------------------------------------------------- 读入
def _num(v: Any, name: str) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError) as e:
        raise AssemblyError(f"{name} 必须是数字") from e
    if not math.isfinite(f):
        raise AssemblyError(f"{name} 必须是有限数")
    return f


def _vec(v: Any, n: int, name: str) -> tuple[float, ...]:
    if not isinstance(v, (list, tuple)) or len(v) != n:
        raise AssemblyError(f"{name} 必须是 {n} 个数字的数组")
    return tuple(_num(x, name) for x in v)


def parse(data: dict) -> tuple[str, list[Instance], float, float, bool, dict]:
    if not isinstance(data, dict):
        raise AssemblyError("装配文件顶层必须是对象")
    name = str(data.get("name") or "unnamed")
    raw = data.get("components")
    if not isinstance(raw, list) or not raw:
        raise AssemblyError("components 必须是非空数组")
    out: list[Instance] = []
    seen: set[str] = set()
    for n, row in enumerate(raw):
        if not isinstance(row, dict):
            raise AssemblyError(f"components[{n}] 必须是对象")
        cid = row.get("id")
        typ = row.get("type")
        if not isinstance(cid, str) or not cid:
            raise AssemblyError(f"components[{n}].id 必须是非空字符串")
        if cid in seen:
            raise AssemblyError(f"组件 id 重复：{cid}")
        seen.add(cid)
        if not isinstance(typ, str) or not typ:
            raise AssemblyError(f"{cid}.type 必须是非空字符串")
        parent = row.get("parent")
        if parent is not None and not isinstance(parent, str):
            raise AssemblyError(f"{cid}.parent 必须是字符串")
        at = _vec(row.get("at", [0, 0]), 2, f"{cid}.at")
        rot = _vec(row.get("rot", [0, 0, 0]), 3, f"{cid}.rot")
        pose = row.get("pose")
        if pose is not None:
            pose = _vec(pose, 6, f"{cid}.pose")
        sid = row.get("servo_id")
        if sid is not None:
            sid = int(sid)
            if not 1 <= sid <= 253:
                raise AssemblyError(f"{cid}.servo_id 必须在 1..253")
        jo = row.get("joint")
        if jo is not None and not isinstance(jo, dict):
            raise AssemblyError(f"{cid}.joint 必须是对象")
        out.append(Instance(
            id=cid, type=typ, parent=parent,
            parent_port=row.get("port"), child_port=str(row.get("child_port") or "mount"),
            at=(at[0], at[1]), spin=_num(row.get("spin", 0), f"{cid}.spin"),
            rot=(rot[0], rot[1], rot[2]), pose=pose, servo_id=sid,
            offboard=bool(row.get("offboard", False)), joint_override=jo,
        ))
    payload = _num(data.get("payload_g", 0.0), "payload_g")
    if payload < 0:
        raise AssemblyError("payload_g 不能为负")
    max_accel = _num(data.get("max_accel_m_s2", 0.5), "max_accel_m_s2")
    if max_accel < 0:
        raise AssemblyError("max_accel_m_s2 不能为负")
    strict = bool(data.get("strict", False))
    return name, out, payload, max_accel, strict, data


def load(path: str | pathlib.Path) -> tuple[str, list[Instance], float, float, bool, dict]:
    try:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise AssemblyError(f"找不到装配文件 {path}") from e
    except json.JSONDecodeError as e:
        raise AssemblyError(f"装配 JSON 语法错误：{e}") from e
    return parse(data)


# ---------------------------------------------------------------- 求解
def _tilde(v: float, q: float = 20.0) -> bool:
    return abs(v / q - round(v / q)) < 1e-7


def _mat_pose(m: C.Mat) -> list[float]:
    """从矩阵取 (x,y,z,rx,ry,rz) 仅用于展示；旋转用 ZYX 近似不够精确，
    所以这里只输出位置 + 前三个欧拉角（报告里够用）。"""
    x, y, z = m[0][3], m[1][3], m[2][3]
    # 不反解通用旋转；保留位置，旋转标成 0，真正的完整矩阵在 raw 里。
    return [round(x, 3), round(y, 3), round(z, 3), 0.0, 0.0, 0.0]


def _world_port(inst: Instance, port: C.Port) -> C.Mat:
    assert inst.world is not None
    return C.mat_mul(inst.world, port.transform.matrix())


def _mate(report: Report, parent: Instance, child: Instance) -> bool:
    p = parent.comp
    c = child.comp
    if not child.parent_port:
        report.add(ERROR, "port.missing", f"{child.id}: 缺少 parent 端口", child.id)
        return False
    try:
        pport = p.port(child.parent_port)
        cport = c.port(child.child_port)
    except KeyError as e:
        report.add(ERROR, "port.unknown", str(e), child.id)
        return False
    if pport.kind != cport.kind:
        report.add(ERROR, "port.kind",
                   f"{parent.id}.{pport.name} 是 {pport.kind}，"
                   f"{child.id}.{cport.name} 是 {cport.kind}", child.id)
        return False
    if not pport.compatible(cport):
        report.add(ERROR, "port.gender",
                   f"{parent.id}.{pport.name} 与 {child.id}.{cport.name} 公母不匹配",
                   child.id)
        return False

    dx, dy = child.at
    if pport.kind == "mech.grid":
        if not pport.grid:
            report.add(ERROR, "grid.missing", f"{parent.id}.{pport.name} 没有网格范围", parent.id)
            return False
        gw, gd = pport.grid
        if abs(dx) > gw / 2 + 1e-9 or abs(dy) > gd / 2 + 1e-9:
            report.add(ERROR, "grid.range",
                       f"{child.id}: at={[dx, dy]} 超出 {parent.id}.{pport.name} "
                       f"网格 ±{gw/2:g}/±{gd/2:g}", child.id)
            return False
        if not _tilde(dx) or not _tilde(dy):
            report.add(ERROR, "grid.pitch",
                       f"{child.id}: at={[dx, dy]} 不是 20mm 网格整数倍", child.id)
            return False
    else:
        if abs(dx) > 1e-9 or abs(dy) > 1e-9:
            report.add(ERROR, "port.offset", f"{child.id}: {pport.kind} 不允许网格偏移", child.id)
            return False

    if abs(child.spin / 90.0 - round(child.spin / 90.0)) > 1e-7:
        report.add(ERROR, "spin", f"{child.id}: spin 必须是 90° 的整数倍", child.id)
        return False
    if child.pose is not None:
        report.add(ERROR, "pose.parent", f"{child.id}: 有 parent 时不能同时给 pose", child.id)
        return False

    parent_world = parent.world
    assert parent_world is not None
    want = (C.mat_mul(parent_world, pport.transform.matrix()))
    want = C.mat_mul(want, C.Transform((dx, dy, 0)).matrix())
    want = C.mat_mul(want, C.mat_rot_z(child.spin))
    want = C.mat_mul(want, C.Transform((0, 0, 0), child.rot).matrix())
    child.world = C.mat_mul(want, C.mat_inv_rigid(cport.transform.matrix()))

    # 网格端口用位置去重；单端口只能一次。
    used = getattr(parent, "_used", None)
    if used is None:
        used = {}
        setattr(parent, "_used", used)
    key = (pport.name, round(dx, 3), round(dy, 3))
    if key in used:
        report.add(ERROR, "port.reuse",
                   f"{parent.id}.{pport.name} 的 {[dx, dy]} 已被 {used[key]} 使用", child.id)
        return False
    used[key] = child.id
    if len([k for k in used if k[0] == pport.name]) > pport.max_uses:
        report.add(ERROR, "port.max",
                   f"{parent.id}.{pport.name} 超过 max_uses={pport.max_uses}", child.id)
        return False
    return True


def solve(report: Report, instances: list[Instance]) -> None:
    by_id = {i.id: i for i in instances}
    for i in instances:
        try:
            comp = C.get(i.type)
        except KeyError as e:
            report.add(ERROR, "type.unknown", str(e), i.id)
            continue
        if i.joint_override and comp.joint:
            try:
                allowed = set(comp.joint.as_dict()) | {"min", "max", "dir"}
                bad = sorted(set(i.joint_override) - allowed)
                if bad:
                    raise ValueError(f"不认识的 joint 字段 {bad}")
                d = {**comp.joint.as_dict(), **i.joint_override}
                js = C.JointSpec(
                    name=str(d.get("name", comp.joint.name)),
                    min_value=float(d.get("min", d.get("min_value", comp.joint.min_value))),
                    max_value=float(d.get("max", d.get("max_value", comp.joint.max_value))),
                    unit=str(d.get("unit", comp.joint.unit)),
                    zero_ticks=int(d.get("zero_ticks", comp.joint.zero_ticks)),
                    direction=int(d.get("dir", d.get("direction", comp.joint.direction))),
                    ticks_per_unit=float(d.get("ticks_per_unit", comp.joint.ticks_per_unit)),
                    max_step=float(d.get("max_step", comp.joint.max_step)),
                    rated_torque_nm=float(d.get("rated_torque_nm", comp.joint.rated_torque_nm)),
                    mode=str(d.get("mode", comp.joint.mode)),
                    center=tuple(float(x) for x in d.get("center", comp.joint.center)),
                )
                comp = replace(comp, joint=js)
            except Exception as e:
                report.add(ERROR, "joint.override", f"{i.id}: {e}", i.id)
        i.component = comp

    for i in instances:
        if i.offboard:
            if i.parent:
                report.add(ERROR, "offboard.parent", f"{i.id}: offboard 不能有 parent", i.id)
            if i.pose is not None:
                i.world = C.Transform(tuple(i.pose[:3]), tuple(i.pose[3:])).matrix()
            else:
                i.world = C.mat_identity()
    roots = [i for i in instances if not i.parent and not i.offboard]
    if len(roots) != 1:
        report.add(ERROR, "root.count", f"必须有且只有一个机械根组件；当前 {len(roots)} 个",
                   ",".join(i.id for i in roots))
        return
    root = roots[0]
    if root.pose is not None:
        root.world = C.Transform(tuple(root.pose[:3]), tuple(root.pose[3:])).matrix()
    else:
        root.world = C.mat_identity()
    if root.parent_port:
        report.add(WARN, "root.port", f"根组件 {root.id} 的 port 被忽略", root.id)

    unresolved = {i.id: i for i in instances if i is not root and not i.offboard}
    while unresolved:
        progressed = False
        for i in list(unresolved.values()):
            if not i.parent:
                continue
            parent = by_id.get(i.parent)
            if parent is None:
                report.add(ERROR, "parent.unknown", f"{i.id}: 父组件 {i.parent} 不存在", i.id)
                unresolved.pop(i.id, None)
                progressed = True
                continue
            if parent.world is None or parent.component is None:
                continue
            if _mate(report, parent, i):
                unresolved.pop(i.id, None)
                progressed = True
            else:
                unresolved.pop(i.id, None)
                progressed = True
        if not progressed:
            for i in unresolved.values():
                report.add(ERROR, "cycle", f"{i.id}: 父链有环或无法求解", i.id)
            break

    # 根组件本身也可能有 parent 端口/姿态错误，先记录有效类型
    for i in instances:
        if i.component is None:
            report.add(ERROR, "type.unknown", f"{i.id}: 未知类型 {i.type}", i.id)


def _aabb(world: C.Mat, bbox: tuple[float, float, float, float, float, float]) -> tuple[float, ...]:
    x0, y0, z0, x1, y1, z1 = bbox
    pts = [C.mat_apply(world, x, y, z)
           for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    return (min(p[0] for p in pts), min(p[1] for p in pts), min(p[2] for p in pts),
            max(p[0] for p in pts), max(p[1] for p in pts), max(p[2] for p in pts))


def _box_corners(world: C.Mat, bbox: tuple[float, float, float, float, float, float]):
    x0, y0, z0, x1, y1, z1 = bbox
    # 索引 i = x + 2*y + 4*z，和 _box_tris 的面表一致。
    return [C.mat_apply(world, x, y, z) for z in (z0, z1)
            for y in (y0, y1) for x in (x0, x1)]


def _box_tris(pts: list[tuple[float, float, float]]):
    # 顶点顺序：(x,y,z) 的 0/1 组合，索引 i = x + 2*y + 4*z
    f = ((0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
         (0, 1, 5), (0, 5, 4), (1, 3, 7), (1, 7, 5),
         (2, 6, 7), (2, 7, 3), (0, 4, 6), (0, 6, 2))
    return [(pts[a], pts[b], pts[c]) for a, b, c in f]


def _sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def _cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
                          a[0] * b[1] - a[1] * b[0])
def _dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _point_in_tri(p, a, b, c, n=None, eps: float = 1e-6) -> bool:
    if n is None:
        n = _cross(_sub(b, a), _sub(c, a))
    if abs(_dot(_sub(p, a), n)) > eps * max(1.0, math.sqrt(_dot(n, n))):
        return False
    v0, v1, v2 = _sub(c, a), _sub(b, a), _sub(p, a)
    d00, d01, d11 = _dot(v0, v0), _dot(v0, v1), _dot(v1, v1)
    d20, d21 = _dot(v2, v0), _dot(v2, v1)
    den = d00 * d11 - d01 * d01
    if abs(den) < 1e-12:
        return False
    u = (d11 * d20 - d01 * d21) / den
    v = (d00 * d21 - d01 * d20) / den
    return u >= -eps and v >= -eps and u + v <= 1 + eps


def _seg_tri(p, q, a, b, c, eps: float = 1e-7) -> bool:
    n = _cross(_sub(b, a), _sub(c, a))
    den = _dot(n, _sub(q, p))
    if abs(den) < eps:
        return False
    t = _dot(n, _sub(a, p)) / den
    if t < -eps or t > 1 + eps:
        return False
    x = (p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1]), p[2] + t * (q[2] - p[2]))
    return _point_in_tri(x, a, b, c, n, eps)


def _inside_obb(world: C.Mat, bbox, pt, eps: float = 1e-4) -> bool:
    inv = C.mat_inv_rigid(world)
    x, y, z = C.mat_apply(inv, *pt)
    return (bbox[0] - eps <= x <= bbox[3] + eps and
            bbox[1] - eps <= y <= bbox[4] + eps and
            bbox[2] - eps <= z <= bbox[5] + eps)


def _mesh_hit(wa, ba, wb, bb) -> bool:
    ca, cb = _box_corners(wa, ba), _box_corners(wb, bb)
    # 完全包含：一个盒子的 8 个角都在另一个盒子里。
    if all(_inside_obb(wb, bb, p) for p in ca) or all(_inside_obb(wa, ba, p) for p in cb):
        return True
    ta, tb = _box_tris(ca), _box_tris(cb)
    for a in ta:
        for b in tb:
            for i in range(3):
                if _seg_tri(a[i], a[(i + 1) % 3], *b):
                    return True
                if _seg_tri(b[i], b[(i + 1) % 3], *a):
                    return True
    return False


def _descendants(inst: Instance, instances: list[Instance]) -> list[Instance]:
    out = []
    changed = True
    ids = {inst.id}
    while changed:
        changed = False
        for i in instances:
            if i.id not in ids and i.parent in ids:
                ids.add(i.id)
                changed = True
    return [i for i in instances if i.id in ids and i.id != inst.id]


def _com(instances: list[Instance], payload_g: float, payload_at: tuple[float, float, float] | None):
    total = 0.0
    sx = sy = sz = 0.0
    for i in instances:
        if i.world is None or i.component is None or i.offboard:
            continue
        b = i.component.bbox
        cx, cy, cz = ((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2)
        x, y, z = C.mat_apply(i.world, cx, cy, cz)
        m = i.component.mass_g
        total += m
        sx += m * x
        sy += m * y
        sz += m * z
    if payload_at and payload_g > 0:
        total += payload_g
        sx += payload_g * payload_at[0]
        sy += payload_g * payload_at[1]
        sz += payload_g * payload_at[2]
    if total <= 0:
        return None
    return (sx / total, sy / total, sz / total)


def _convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    pts = sorted(set((round(x, 6), round(y, 6)) for x, y in points))
    if len(pts) <= 1:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _point_in_poly(p: tuple[float, float], poly: list[tuple[float, float]]) -> bool:
    x, y = p
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _edge_distance(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    px, py = p
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    den = dx * dx + dy * dy
    if den <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / den))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _stability(root: Instance, com: tuple[float, float, float] | None,
               max_accel: float, report: Report) -> Stability | None:
    if root.component is None or root.world is None:
        return None
    poly = root.component.support
    if not poly:
        b = root.component.bbox
        poly = ((b[0], b[1]), (b[3], b[1]), (b[3], b[4]), (b[0], b[4]))
    world_poly = [C.mat_apply(root.world, x, y, 0)[:2] for x, y in poly]
    hull = _convex_hull(world_poly)
    if com is None or len(hull) < 3:
        return Stability(com, hull, None, None, True)
    p2 = (com[0], com[1])
    inside = _point_in_poly(p2, hull)
    margin = min(_edge_distance(p2, hull[i], hull[(i + 1) % len(hull)])
                 for i in range(len(hull)))
    if not inside:
        margin = -margin
    tip = 9.81 * max(0.0, margin) / max(1.0, com[2]) if com else None
    st = Stability(com, hull, margin, tip, inside)
    if not inside:
        report.add(ERROR, "stability.outside",
                   f"整机重心 ({com[0]:.0f},{com[1]:.0f}) 在支撑多边形外", root.id)
    elif margin < 10:
        report.add(WARN, "stability.margin", f"重心离支撑边仅 {margin:.1f}mm（建议 ≥10mm）", root.id)
    if tip is not None and max_accel > 0 and tip < max_accel:
        report.add(WARN, "stability.accel",
                   f"静态估算倾覆加速度 {tip:.2f} m/s² < 设计 {max_accel:.2f}", root.id)
    return st


def _joint_loads(report: Report, instances: list[Instance], payload_g: float,
                 payload_at: tuple[float, float, float] | None,
                 max_accel: float = 0.0) -> list[JointLoad]:
    out: list[JointLoad] = []
    for i in instances:
        if i.component is None or i.world is None or i.offboard or i.component.joint is None:
            continue
        js = i.component.joint
        if js.mode != "position":
            continue
        sub = _descendants(i, instances)
        masses = [x for x in sub if x.world is not None and x.component is not None]
        if not masses and payload_g <= 0:
            continue
        total = sum(x.component.mass_g for x in masses)  # type: ignore[union-attr]
        sx = sy = sz = 0.0
        for x in masses:
            b = x.component.bbox  # type: ignore[union-attr]
            cx, cy, cz = (b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2
            wx, wy, wz = C.mat_apply(x.world, cx, cy, cz)  # type: ignore[arg-type]
            sx += wx * x.component.mass_g  # type: ignore[union-attr]
            sy += wy * x.component.mass_g  # type: ignore[union-attr]
            sz += wz * x.component.mass_g  # type: ignore[union-attr]
        if payload_at and payload_g > 0:
            total += payload_g
            sx += payload_at[0] * payload_g
            sy += payload_at[1] * payload_g
            sz += payload_at[2] * payload_g
        if total <= 0:
            continue
        cx, cy, cz = sx / total, sy / total, sz / total
        ox, oy, oz = C.mat_apply(i.world, *js.center)
        # 保守：把力臂取 3D 距离，等价于“手臂转到水平”的最坏姿态；
        # 不假装是当前姿态的瞬时动力学。
        arm = math.sqrt((cx - ox) ** 2 + (cy - oy) ** 2 + (cz - oz) ** 2)
        gravity = (total / 1000.0) * 9.81 * (arm / 1000.0)
        dynamic = (total / 1000.0) * max(0.0, max_accel) * (arm / 1000.0)
        load = gravity + dynamic
        ratio = load / max(js.rated_torque_nm, 1e-9)
        out.append(JointLoad(i.id, js.name, report.servo_ids.get(i.id, 0),
                             js.rated_torque_nm, load, ratio,
                             total, arm, gravity, dynamic, max_accel,
                             js.rated_torque_nm - load, ratio <= 1.0))
        if ratio > 1.0:
            report.add(ERROR, "joint.overload",
                       f"{i.id}({js.name}) 静+动力矩 {load:.2f} N·m > 额定 "
                       f"{js.rated_torque_nm:.2f}（重力 {gravity:.2f} + 动态 {dynamic:.2f}）",
                       i.id)
        elif ratio > 0.5:
            report.add(WARN, "joint.margin",
                       f"{i.id}({js.name}) 静+动力矩 {load:.2f} N·m 超过额定的 50% "
                       f"（重力 {gravity:.2f} + 动态 {dynamic:.2f}）", i.id)
    return out


def _assign_servos(report: Report, instances: list[Instance]) -> dict[str, int]:
    ids: dict[str, int] = {}
    used: dict[int, str] = {}
    nxt = 1
    servo_instances = [i for i in instances if i.component and i.component.joint]
    for i in servo_instances:
        sid = i.servo_id
        if sid is None:
            while nxt in used:
                nxt += 1
            sid = nxt
        if sid in used:
            report.add(ERROR, "servo.duplicate", f"舵机 ID {sid} 同时给 {used[sid]} 和 {i.id}", i.id)
            continue
        used[sid] = i.id
        i.servo_id = sid
        ids[i.id] = sid
    max_servos = None
    for i in instances:
        if i.component and i.component.max_servos:
            max_servos = i.component.max_servos if max_servos is None else min(max_servos, i.component.max_servos)
    if max_servos is not None and len(ids) > max_servos:
        report.add(ERROR, "controller.capacity",
                   f"{len(ids)} 个舵机超过控制器上限 {max_servos}")
    for i in servo_instances:
        c = i.component
        assert c is not None
        names = {p_.name for p_ in c.ports}
        if not {"bus_in", "bus_out"} <= names:
            report.add(WARN, "bus.missing", f"{i.id}: 没有 bus_in/bus_out，接线要单独处理", i.id)
    return ids


def _power(report: Report, instances: list[Instance]) -> PowerResult:
    idle = peak = 0.0
    supply = 0.0
    sources: list[str] = []
    for i in instances:
        if not i.component or not i.component.power:
            continue
        p = i.component.power
        if p.supply_a > 0:
            supply = max(supply, p.supply_a)
            sources.append(i.id)
        else:
            idle += p.idle_a
            peak += p.peak_a
    planning = idle + 0.25 * max(0.0, peak - idle)
    ok = True
    if supply <= 0:
        report.add(WARN, "power.source", "没有电源组件（power.*）；只做结构校验")
    else:
        if planning > supply:
            ok = False
            report.add(ERROR, "power.planning",
                       f"规划电流 {planning:.2f}A > 电源 {supply:.1f}A")
        if peak > supply:
            report.add(WARN, "power.peak",
                       f"峰值电流 {peak:.2f}A > 电源 {supply:.1f}A；避免所有关节同时堵转")
    return PowerResult(supply, idle, peak, planning, sources, ok)


def _bom(report: Report, instances: list[Instance]) -> tuple[list[BomLine], float, float]:
    agg: dict[tuple[str, str], BomLine] = {}
    for i in instances:
        if not i.component:
            continue
        for b in i.component.bom:
            key = (b.name, b.spec)
            line = agg.get(key)
            if line is None:
                agg[key] = BomLine(b.name, b.spec, b.qty, b.unit_cost,
                                  b.mass_g * b.qty, b.category)
            else:
                line.qty += b.qty
                line.mass_g += b.mass_g * b.qty
    lines = sorted(agg.values(), key=lambda x: (x.category, x.name, x.spec))
    total_cost = sum(x.cost for x in lines)
    total_mass = sum(x.mass_g for x in lines)
    return lines, total_mass, total_cost


def _safety(report: Report, instances: list[Instance], ids: dict[str, int],
            name: str) -> tuple[dict | None, dict | None]:
    joints: dict[str, dict] = {}
    cal: dict[str, dict] = {}
    for i in instances:
        if not i.component or not i.component.joint:
            continue
        js = i.component.joint
        if js.mode != "position":
            continue
        if js.name in joints:
            report.add(ERROR, "joint.duplicate", f"位置关节名重复：{js.name}", i.id)
            continue
        sid = ids.get(i.id, i.servo_id or 0)
        joints[js.name] = {
            "servo_id": sid, "min": js.min_value, "max": js.max_value,
            "unit": js.unit, "zero_ticks": js.zero_ticks, "dir": js.direction,
            "ticks_per_unit": js.ticks_per_unit, "max_step": js.max_step,
        }
        cal[js.name] = {
            "name": js.name, "servo_id": sid, "zero_ticks": js.zero_ticks,
            "dir": js.direction,
            "min_deg": js.min_value if js.unit == "deg" else 0.0,
            "max_deg": js.max_value if js.unit == "deg" else 1.0,
            "speed_unit": 1.0,
        }
    if not joints:
        return None, None
    safety = {"robot": name, "calibrated": False, "joints": joints}
    calibration = {"robot": name, "created": "", "joints": cal}
    return safety, calibration


# ---------------------------------------------------------------- 主入口
def validate(name: str, instances: list[Instance], payload_g: float,
             max_accel: float, strict: bool, raw: dict | None = None) -> Report:
    report = Report(name=name, instances=instances, payload_g=payload_g, strict=strict, raw=raw)
    if raw:
        ic = raw.get("ignore_collision") or []
        if not isinstance(ic, list):
            report.add(ERROR, "ignore.invalid", "ignore_collision 必须是数组")
        else:
            for pair in ic:
                if (isinstance(pair, (list, tuple)) and len(pair) == 2
                        and all(isinstance(x, str) for x in pair)):
                    report.ignore_collision.add(tuple(sorted(pair)))  # type: ignore[arg-type]
                else:
                    report.add(ERROR, "ignore.invalid", f"ignore_collision 项不合法：{pair!r}")
    solve(report, instances)
    # 类型未知的实例没有 world；后续只处理已解决的
    solved = [i for i in instances if i.world is not None and i.component is not None]
    if len(solved) != len(instances):
        report.add(ERROR, "solve.incomplete", f"{len(instances)-len(solved)} 个组件未能求解")

    # 重复 id 在 parse 已拦；这里处理无根/环

    # 碰撞：AABB 粗查，父子相邻不算。
    for a in range(len(solved)):
        for b in range(a + 1, len(solved)):
            ia, ib = solved[a], solved[b]
            if ia.offboard or ib.offboard:
                continue
            if ia.parent == ib.id or ib.parent == ia.id:
                continue
            if tuple(sorted((ia.id, ib.id))) in report.ignore_collision:
                continue
            ba = _aabb(ia.world, ia.component.bbox)  # type: ignore[arg-type]
            bb = _aabb(ib.world, ib.component.bbox)  # type: ignore[arg-type]
            overlap = [min(ba[3], bb[3]) - max(ba[0], bb[0]),
                       min(ba[4], bb[4]) - max(ba[1], bb[1]),
                       min(ba[5], bb[5]) - max(ba[2], bb[2])]
            if all(v > 1.0 for v in overlap):
                vol = overlap[0] * overlap[1] * overlap[2]
                report.collision_stats["aabb_pairs"] = report.collision_stats.get("aabb_pairs", 0) + 1
                hit = _mesh_hit(ia.world, ia.component.bbox, ib.world, ib.component.bbox)  # type: ignore[arg-type]
                report.collision_stats["mesh_tests"] = report.collision_stats.get("mesh_tests", 0) + 1
                if hit:
                    report.collision_stats["mesh_hits"] = report.collision_stats.get("mesh_hits", 0) + 1
                    report.collision_mesh.append({"a": ia.id, "b": ib.id, "volume_mm3": round(vol, 1)})
                    msg = f"{ia.id} 与 {ib.id} 的实体盒网格相交（AABB 重叠约 {vol:.0f}mm³）"
                    report.add(ERROR if strict else WARN, "collision.mesh", msg, ia.id)
                    # 保留 AABB 粗查代码，旧报告/测试仍能按原口径过滤。
                    report.add(ERROR if (strict and vol > 500) else WARN, "collision.aabb",
                               f"{ia.id} 与 {ib.id} 的包围盒重叠约 {vol:.0f}mm³", ia.id)
                else:
                    msg = f"{ia.id} 与 {ib.id} 的包围盒重叠约 {vol:.0f}mm³，但实体盒网格未相交"
                    report.add(ERROR if (strict and vol > 500) else WARN, "collision.aabb", msg, ia.id)

    # 工具/载荷
    roots = [i for i in instances if not i.parent and not i.offboard]
    tool_inst = [i for i in solved if i.component and i.component.tool and not i.offboard]
    payload_at = None
    if tool_inst:
        t = tool_inst[-1]
        assert t.component and t.component.tool and t.world is not None
        tip = C.mat_apply(t.world, *t.component.tool.tip.pos)
        payload_at = tip
        if payload_g > t.component.tool.max_payload_g:
            report.add(ERROR, "payload.max",
                       f"载荷 {payload_g:g}g > {t.id} 标称 {t.component.tool.max_payload_g:g}g", t.id)
    elif payload_g > 0:
        report.add(WARN, "payload.no_tool", "设置了载荷但没有工具组件")

    ids = _assign_servos(report, solved)
    report.servo_ids = ids
    for jl in _joint_loads(report, solved, payload_g, payload_at, max_accel):
        jl.servo_id = ids.get(jl.instance, 0)
        report.joint_loads.append(jl)
    report.power = _power(report, solved)
    report.bom, bom_mass, report.total_cost_cny = _bom(report, solved)
    report.total_mass_g = sum(i.component.mass_g for i in solved if i.component)
    com = _com(solved, payload_g, payload_at)
    if roots:
        report.stability = _stability(roots[0], com, max_accel, report)
    else:
        report.add(ERROR, "root.none", "没有根组件")
    report.safety, report.calibration = _safety(report, solved, ids, name)
    for i in solved:
        if i.component and i.component.status == "concept":
            report.add(WARN, "component.concept",
                       f"{i.id}({i.component.id}) 是 concept 级，CAD/实物未验证", i.id)
    return report


def load_and_validate(path: str | pathlib.Path) -> Report:
    name, inst, payload, accel, strict, raw = load(path)
    return validate(name, inst, payload, accel, strict, raw)


# ---------------------------------------------------------------- 报告/输出
def _fmt_money(v: float) -> str:
    return f"¥{v:.0f}"


def to_markdown(r: Report) -> str:
    lines = [f"# 装配报告 · {r.name}", "",
             f"**结论：{'PASS' if r.ok else 'BLOCK'}**  "
             f"组件 {len(r.instances)} · 舵机 {len(r.servo_ids)} · "
             f"质量 {r.total_mass_g:.0f}g · BOM {_fmt_money(r.total_cost_cny)}", ""]
    if r.issues:
        lines += ["## 检查结果", "", "| 级别 | 代码 | 对象 | 说明 |", "|---|---|---|---|"]
        for x in r.issues:
            lines.append(f"| {x.level} | `{x.code}` | {x.instance or '-'} | {x.message} |")
        lines.append("")
    lines += ["## 组件", "", "| id | 类型 | 父级 | 舵机 | 质量 g |", "|---|---|---|---:|---:|"]
    for i in r.instances:
        c = i.component
        lines.append(f"| `{i.id}` | `{i.type}` | {i.parent or '-'} | "
                     f"{i.servo_id if i.servo_id is not None else '-'} | "
                     f"{c.mass_g if c else '?'} |")
    lines += ["", "## BOM", "", "| 物料 | 规格 | 数量 | 单价 | 小计 |", "|---|---|---:|---:|---:|"]
    for b in r.bom:
        lines.append(f"| {b.name} | {b.spec} | {b.qty} | ¥{b.unit_cost:.0f} | ¥{b.cost:.0f} |")
    lines += ["", f"合计 **{_fmt_money(r.total_cost_cny)}** / **{r.total_mass_g:.0f}g**", ""]
    if r.power:
        p = r.power
        lines += ["## 电源", "",
                  f"- 电源：{p.supply_a:.1f}A（{', '.join(p.sources) or '无'}）",
                  f"- 规划：{p.planning_a:.2f}A；峰值：{p.peak_a:.2f}A",
                  f"- 判定：{'PASS' if p.ok else 'BLOCK'}", ""]
    if r.stability:
        s = r.stability
        lines += ["## 稳定性", "",
                  f"- 重心：{tuple(round(x, 1) for x in s.com) if s.com else '—'}",
                  f"- 支撑边距：{'—' if s.margin_mm is None else f'{s.margin_mm:.1f}mm'}",
                  f"- 静态倾覆加速度：{'—' if s.tip_accel_m_s2 is None else f'{s.tip_accel_m_s2:.2f} m/s²'}",
                  ""]
    if r.joint_loads:
        lines += ["## 关节静载+动载（保守：3D 力臂×全部下游质量）", "",
                  "| 关节 | 舵机 | 下游质量 g | 力臂 mm | 重力 N·m | 动态 N·m | 合计 | 额定 | 比例 |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for j in r.joint_loads:
            lines.append(f"| {j.name} | {j.servo_id} | {j.mass_g:.0f} | {j.arm_mm:.0f} | "
                         f"{j.gravity_nm:.2f} | {j.dynamic_nm:.2f} | {j.load_nm:.2f} | "
                         f"{j.rated_nm:.2f} | {j.ratio:.2f}× |")
        lines.append("")
    if r.servo_ids:
        lines += ["## 总线顺序", "", "| ID | 实例 | 关节 |", "|---:|---|---|"]
        for i in r.instances:
            if i.servo_id is not None:
                lines.append(f"| {i.servo_id} | `{i.id}` | {i.component.joint.name if i.component and i.component.joint else '-'} |")
        lines.append("")
    if r.safety:
        lines += ["## 安全配置", "", "位置关节已生成 `safety.json`；先标定，再 `preflight --policy`。", ""]
    lines += ["## 边界", "",
              "- 这是**接口/质量/功率/静力+简化动态**检查，不是整机动力学仿真。",
              "- 碰撞用每个组件 bbox 的 12 个三角面做三角-三角相交（AABB 仅粗筛）；"
              "组件不是 STEP 实体网格，`collision.aabb` 仍可能保守。",
              "- 关节力矩用 3D 力臂 + 设计加速度做最坏姿态估算；不含角加速度/惯量/摩擦。",
              "- 物理闸门仍 0/5；本报告不能替代实物验证。", ""]
    return "\n".join(lines)


def to_svg(r: Report, width: int = 1000, height: int = 620) -> str:
    cats = {"frame": "#7aa6c2", "joint": "#e0a458", "link": "#8fb573",
            "adapter": "#b9a3c9", "drive": "#6b8e9e", "tool": "#d97b7b",
            "sensor": "#c9b458", "electronics": "#7f9f7f", "power": "#a88b6a"}
    boxes = []
    for i in r.instances:
        if i.world is None or i.component is None:
            continue
        b = _aabb(i.world, i.component.bbox)
        boxes.append((i, b))
    if not boxes:
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"></svg>'
    minx = min(b[0] for _, b in boxes); maxx = max(b[3] for _, b in boxes)
    miny = min(b[1] for _, b in boxes); maxy = max(b[4] for _, b in boxes)
    minz = min(b[2] for _, b in boxes); maxz = max(b[5] for _, b in boxes)
    spanx = max(1.0, maxx - minx); spany = max(1.0, maxy - miny); spanz = max(1.0, maxz - minz)
    panel_w = (width - 60) / 2
    panel_h = height - 120
    scale = min(panel_w / spanx, panel_h / spany, panel_w / spanx, panel_h / spanz, 1.2)
    ox1, oy1 = 30, 80
    ox2, oy2 = 30 + panel_w + 20, 80
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}" font-family="sans-serif">',
           '<rect width="100%" height="100%" fill="#f7f6f2"/>',
           f'<text x="30" y="32" font-size="20" font-weight="bold">装配预览 · {html.escape(r.name)}</text>',
           f'<text x="30" y="55" font-size="13" fill="#555">'
           f'{"PASS" if r.ok else "BLOCK"} · {len(r.instances)} 组件 · '
           f'{r.total_mass_g:.0f}g · ¥{r.total_cost_cny:.0f}</text>',
           f'<text x="{ox1}" y="{oy1-12}" font-size="13" fill="#666">俯视 XY</text>',
           f'<text x="{ox2}" y="{oy2-12}" font-size="13" fill="#666">侧视 XZ</text>']
    for ox, oy, axes in ((ox1, oy1, (0, 1)), (ox2, oy2, (0, 2))):
        out.append(f'<rect x="{ox}" y="{oy}" width="{panel_w:.1f}" height="{panel_h}" '
                   f'fill="#fff" stroke="#ddd"/>')
    for i, b in boxes:
        color = cats.get(i.component.category, "#999")
        for ox, oy, (a1, a2) in ((ox1, oy1, (0, 1)), (ox2, oy2, (0, 2))):
            x = ox + (b[a1] - (minx if a1 == 0 else minz)) * scale + 4
            y = oy + panel_h - (b[a2 + 3] - (miny if a2 == 1 else minz)) * scale - 4
            w = max(2.0, (b[a1 + 3] - b[a1]) * scale)
            h = max(2.0, (b[a2 + 3] - b[a2]) * scale)
            out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                       f'fill="{color}" fill-opacity="0.35" stroke="{color}" stroke-width="1"/>')
            if a1 == 0:
                out.append(f'<text x="{x+2:.1f}" y="{y+11:.1f}" font-size="9" fill="#333">'
                           f'{html.escape(i.id)}</text>')
    if r.stability and r.stability.support:
        pts = " ".join(f"{ox1 + (x-minx)*scale + 4:.1f},{oy1 + panel_h - (y-miny)*scale - 4:.1f}"
                       for x, y in r.stability.support)
        out.append(f'<polygon points="{pts}" fill="none" stroke="#2b7a4b" stroke-width="2" stroke-dasharray="5 4"/>')
        if r.stability.com:
            cx, cy, _ = r.stability.com
            out.append(f'<circle cx="{ox1 + (cx-minx)*scale + 4:.1f}" '
                       f'cy="{oy1 + panel_h - (cy-miny)*scale - 4:.1f}" r="5" fill="#c0392b"/>')
    out += ['<text x="30" y="{0}" font-size="11" fill="#777"></text>'.format(height - 20),
            "</svg>"]
    return "\n".join(out)


def write_plan(r: Report, outdir: str | pathlib.Path) -> dict[str, str]:
    out = pathlib.Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    plan = out / "plan.json"
    plan.write_text(json.dumps(r.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paths["plan"] = str(plan)
    bom = out / "bom.csv"
    with bom.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["name", "spec", "qty", "unit_cost_cny", "subtotal_cny", "mass_g", "category"])
        for b in r.bom:
            w.writerow([b.name, b.spec, b.qty, f"{b.unit_cost:.2f}",
                        f"{b.cost:.2f}", f"{b.mass_g:.0f}", b.category])
    paths["bom"] = str(bom)
    md = out / "assembly.md"
    md.write_text(to_markdown(r), encoding="utf-8")
    paths["markdown"] = str(md)
    svg = out / "preview.svg"
    svg.write_text(to_svg(r), encoding="utf-8")
    paths["svg"] = str(svg)
    if r.safety:
        safety = out / "safety.json"
        safety.write_text(json.dumps(r.safety, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        paths["safety"] = str(safety)
    if r.calibration:
        cal = out / "calibration.template.json"
        cal.write_text(json.dumps(r.calibration, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        paths["calibration"] = str(cal)
    return paths


__all__ = ["AssemblyError", "Issue", "Instance", "Report", "load", "parse",
           "validate", "load_and_validate", "to_markdown", "to_svg", "write_plan"]
