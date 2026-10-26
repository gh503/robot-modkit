"""三维世界/实验环境 schema：把“现实房间/水池/管道”变成可校验、可复现的 JSON。

坐标系（与 CAD 一致）：
  X 向前/东，Y 向左/北，Z 向上；单位 m；原点由场景定义。
  对象 position 是**底面中心** [x,y,z]，尺寸沿局部轴；旋转为绕 Z 的 yaw（度）。
  Three.js 查看器会转成 Y-up 渲染，不改 JSON。

世界不是渲染贴图：每个对象有碰撞体/语义/材质，流体有体积/液位/温度/盐度，
机器人有装配引用和位姿；`validate` 先挡住物理上不可能的布置。
"""

from __future__ import annotations

import copy
import json
import math
import pathlib
from dataclasses import asdict, dataclass, field
from typing import Any

from . import fluid as fl

SCHEMA = "modkit.world/1"
OBJECT_TYPES = ("box", "cylinder", "sphere", "plane", "mesh", "heightfield")
FLUID_TYPES = ("pool", "tank", "pipe", "puddle", "rain", "reservoir")
SENSOR_TYPES = ("level", "pressure", "flow", "temperature", "turbidity", "camera", "imu")


class WorldError(ValueError):
    pass


@dataclass
class WorldObject:
    id: str
    type: str
    name: str = ""
    position: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    size: list[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    radius: float | None = None
    height: float | None = None
    material: str = "default"
    color: str = "#8a96a8"
    opacity: float = 1.0
    collider: str = "box"          # box|mesh|none
    semantic: str = ""             # floor|wall|pool|pipe|obstacle|table|...
    source: str = ""              # mesh/heightfield URI
    metadata: dict = field(default_factory=dict)

    def bounds(self) -> tuple[list[float], list[float]]:
        x, y, z = self.position
        if self.type == "box":
            sx, sy, sz = self.size
        elif self.type == "cylinder":
            sx = sy = 2.0 * (self.radius or 0.0)
            sz = self.height or 0.0
        elif self.type == "sphere":
            sx = sy = sz = 2.0 * (self.radius or 0.0)
        elif self.type == "plane":
            sx, sy = self.size[0], self.size[1]
            sz = 0.0
        else:
            sx, sy, sz = self.size
        return [x - sx / 2, y - sy / 2, z], [x + sx / 2, y + sy / 2, z + sz]

    def validate(self, errors: list[str]) -> None:
        if not self.id:
            errors.append("对象缺少 id")
        if self.type not in OBJECT_TYPES:
            errors.append(f"{self.id}: 未知类型 {self.type}")
        if len(self.position) != 3 or len(self.rotation) != 3:
            errors.append(f"{self.id}: position/rotation 需要 3 个数")
        if any(not math.isfinite(float(v)) for v in self.position + self.rotation):
            errors.append(f"{self.id}: position/rotation 含 NaN/Inf")
        if self.type == "box":
            if len(self.size) != 3 or any(v <= 0 for v in self.size):
                errors.append(f"{self.id}: box.size 需要 3 个正数")
        elif self.type == "cylinder":
            if not self.radius or self.radius <= 0:
                errors.append(f"{self.id}: cylinder.radius 必须 >0")
            if not self.height or self.height <= 0:
                errors.append(f"{self.id}: cylinder.height 必须 >0")
        elif self.type == "sphere":
            if not self.radius or self.radius <= 0:
                errors.append(f"{self.id}: sphere.radius 必须 >0")
        elif self.type == "plane":
            if len(self.size) < 2 or self.size[0] <= 0 or self.size[1] <= 0:
                errors.append(f"{self.id}: plane.size 需要 [x,y] 正数")
        elif self.type in ("mesh", "heightfield"):
            if not self.source:
                errors.append(f"{self.id}: {self.type} 需要 source")
            if len(self.size) != 3 or any(v <= 0 for v in self.size):
                errors.append(f"{self.id}: {self.type}.size 需要 3 个正数")
        if not 0 <= self.opacity <= 1:
            errors.append(f"{self.id}: opacity 必须在 0..1")
        if self.collider not in ("box", "mesh", "none"):
            errors.append(f"{self.id}: collider 只能是 box/mesh/none")
        bmin, bmax = self.bounds()
        if bmin[2] < -1e-6:
            errors.append(f"{self.id}: 底面 z={bmin[2]:.3f} 低于地面（允许 0）")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FluidBody:
    id: str
    type: str
    fluid: str
    name: str = ""
    position: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    size: list[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    level: float = 1.0              # 0..1，占容器高度
    radius: float | None = None
    height: float | None = None
    volume_m3: float | None = None
    flow_m3_s: float = 0.0
    temperature_c: float = 20.0
    salinity_ppt: float = 0.0
    color: str | None = None
    opacity: float | None = None
    metadata: dict = field(default_factory=dict)

    def validate(self, errors: list[str], warnings: list[str]) -> None:
        if not self.id:
            errors.append("流体缺少 id")
        if self.type not in FLUID_TYPES:
            errors.append(f"{self.id}: 未知流体类型 {self.type}")
        try:
            fl.get(self.fluid)
        except fl.FluidError as e:
            errors.append(f"{self.id}: {e}")
        if len(self.position) != 3:
            errors.append(f"{self.id}: position 需要 3 个数")
        if not 0 <= self.level <= 1:
            errors.append(f"{self.id}: level 必须在 0..1")
        if self.type in ("pool", "reservoir", "puddle"):
            if len(self.size) != 3 or any(v <= 0 for v in self.size):
                errors.append(f"{self.id}: {self.type}.size 需要 3 个正数")
        elif self.type == "tank":
            if self.radius or self.height:
                if not self.radius or not self.height:
                    errors.append(f"{self.id}: tank 需要同时给 radius/height")
                elif self.radius <= 0 or self.height <= 0:
                    errors.append(f"{self.id}: tank.radius/height 必须 >0")
            elif len(self.size) != 3 or any(v <= 0 for v in self.size):
                errors.append(f"{self.id}: tank 需要 radius/height 或 3 个正 size")
        elif self.type == "pipe":
            if not self.radius or not self.height:
                errors.append(f"{self.id}: pipe 需要 radius/height（半径/长度）")
        if self.volume_m3 is not None and self.volume_m3 < 0:
            errors.append(f"{self.id}: volume_m3 不能为负")
        if self.temperature_c < -273.15:
            errors.append(f"{self.id}: 温度低于绝对零度")
        if self.salinity_ppt < 0 or self.salinity_ppt > 300:
            errors.append(f"{self.id}: 盐度必须在 0..300 ppt")
        if self.fluid in fl.FLUIDS and fl.get(self.fluid).category != "water" and self.salinity_ppt:
            warnings.append(f"{self.id}: 非 water 流体忽略 salinity")
        if self.volume_m3 is not None and self.capacity_m3 > 0 and self.volume_m3 > self.capacity_m3 * 1.001:
            warnings.append(f"{self.id}: 体积 {self.volume_m3:.3f} 超过容器 {self.capacity_m3:.3f}")

    @property
    def capacity_m3(self) -> float:
        if self.type in ("pool", "reservoir", "puddle"):
            return max(0.0, self.size[0] * self.size[1] * self.size[2])
        if self.type == "tank":
            if self.radius and self.height:
                return math.pi * self.radius**2 * self.height
            return max(0.0, self.size[0] * self.size[1] * self.size[2])
        if self.type == "pipe":
            return math.pi * (self.radius or 0.0) ** 2 * (self.height or 0.0)
        return 0.0

    @property
    def volume(self) -> float:
        if self.volume_m3 is not None:
            return self.volume_m3
        return self.capacity_m3 * self.level

    @property
    def depth_m(self) -> float:
        if self.type in ("pool", "reservoir", "puddle"):
            return self.size[2] * self.level
        if self.type == "tank" and not (self.radius and self.height):
            return self.size[2] * self.level
        if self.type == "pipe":
            return 2.0 * (self.radius or 0.0) * self.level
        return (self.height or 0.0) * self.level

    @property
    def surface_z(self) -> float:
        if self.type == "pipe":
            return self.position[2] + (self.radius or 0.0) * (2.0 * self.level - 1.0)
        return self.position[2] + self.depth_m

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RobotPlacement:
    assembly: str = "assemblies/m1_pen.json"
    position: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    yaw_deg: float = 0.0
    task: str = "idle"

    def validate(self, errors: list[str]) -> None:
        if len(self.position) != 3:
            errors.append("robot.position 需要 3 个数")
        if self.position[2] < -1e-6:
            errors.append("robot.position.z 不能低于地面")


@dataclass
class Sensor:
    id: str
    type: str
    position: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    target: str = ""
    unit: str = ""
    metadata: dict = field(default_factory=dict)

    def validate(self, errors: list[str], fluid_ids: set[str]) -> None:
        if self.type not in SENSOR_TYPES:
            errors.append(f"{self.id}: 未知传感器类型 {self.type}")
        if len(self.position) != 3:
            errors.append(f"{self.id}: position 需要 3 个数")
        if self.target and self.target not in fluid_ids:
            errors.append(f"{self.id}: target {self.target} 不存在")


@dataclass
class World:
    name: str = "未命名世界"
    description: str = ""
    units: str = "m"
    gravity: float = 9.80665
    environment: str = "empty"
    objects: list[WorldObject] = field(default_factory=list)
    fluids: list[FluidBody] = field(default_factory=list)
    robot: RobotPlacement = field(default_factory=RobotPlacement)
    sensors: list[Sensor] = field(default_factory=list)
    custom_fluids: list[dict] = field(default_factory=list)
    lighting: dict = field(default_factory=lambda: {
        "sun_azimuth_deg": 135.0, "sun_elevation_deg": 45.0,
        "intensity": 1.0, "ambient": 0.35, "sky": "#0b1017"})
    georeference: dict | None = None
    metadata: dict = field(default_factory=dict)
    schema: str = SCHEMA

    def add(self, obj: WorldObject) -> "World":
        if any(o.id == obj.id for o in self.objects):
            raise WorldError(f"对象 id 重复：{obj.id}")
        self.objects.append(obj)
        return self

    def add_fluid(self, body: FluidBody) -> "World":
        if any(f.id == body.id for f in self.fluids):
            raise WorldError(f"流体 id 重复：{body.id}")
        self.fluids.append(body)
        return self

    def object(self, oid: str) -> WorldObject:
        for o in self.objects:
            if o.id == oid:
                return o
        raise WorldError(f"没有对象 {oid}")

    def register_fluids(self) -> None:
        """把世界自带的自定义流体注册进进程内材料库。"""
        for d in self.custom_fluids:
            try:
                fl.register(fl.Fluid(**d), replace_existing=True)
            except (TypeError, fl.FluidError) as e:
                raise WorldError(f"自定义流体无效：{e}") from e

    def validate(self) -> dict:
        errors: list[str] = []
        try:
            self.register_fluids()
        except WorldError as e:
            errors.append(str(e))
        warnings: list[str] = []
        if self.schema != SCHEMA:
            errors.append(f"schema 必须是 {SCHEMA}")
        if self.units != "m":
            errors.append("单位必须是 m（米）")
        if self.gravity <= 0:
            errors.append("gravity 必须 >0")
        if not self.objects:
            warnings.append("世界没有对象")
        ids: set[str] = set()
        for o in self.objects:
            if o.id in ids:
                errors.append(f"对象 id 重复：{o.id}")
            ids.add(o.id)
            o.validate(errors)
        fids: set[str] = set()
        for f in self.fluids:
            if f.id in fids:
                errors.append(f"流体 id 重复：{f.id}")
            fids.add(f.id)
            f.validate(errors, warnings)
        self.robot.validate(errors)
        for s in self.sensors:
            s.validate(errors, fids)
        # 池壁/地面：有 pool 时检查池底对象
        if self.fluids and not any(o.semantic in ("floor", "pool_floor", "ground") for o in self.objects):
            warnings.append("没有 floor/pool_floor 对象；查看器会用默认地面")
        if self.georeference:
            for k in ("lat", "lon"):
                if k not in self.georeference:
                    warnings.append(f"georeference 缺少 {k}")
        return {"ok": not errors, "errors": errors, "warnings": warnings,
                "objects": len(self.objects), "fluids": len(self.fluids)}

    def summary(self) -> dict:
        v = self.validate()
        total_water = sum(f.volume for f in self.fluids)
        bmin = [min((o.bounds()[0][i] for o in self.objects), default=0.0) for i in range(3)]
        bmax = [max((o.bounds()[1][i] for o in self.objects), default=0.0) for i in range(3)]
        return {
            "name": self.name, "environment": self.environment,
            "schema": self.schema, "objects": len(self.objects),
            "fluids": len(self.fluids), "sensors": len(self.sensors),
            "water_volume_m3": total_water,
            "fluid_types": sorted({f.fluid for f in self.fluids}),
            "bounds": {"min": bmin, "max": bmax},
            "ok": v["ok"], "errors": v["errors"], "warnings": v["warnings"],
        }

    def to_dict(self) -> dict:
        return {
            "schema": self.schema, "name": self.name, "description": self.description,
            "units": self.units, "gravity": self.gravity, "environment": self.environment,
            "objects": [o.to_dict() for o in self.objects],
            "fluids": [f.to_dict() for f in self.fluids],
            "robot": asdict(self.robot),
            "sensors": [asdict(s) for s in self.sensors],
            "custom_fluids": self.custom_fluids,
            "lighting": self.lighting, "georeference": self.georeference,
            "metadata": self.metadata,
        }

    def save(self, path: str | pathlib.Path) -> pathlib.Path:
        p = pathlib.Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")
        return p

    @classmethod
    def load(cls, path: str | pathlib.Path) -> "World":
        d = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(d)

    @classmethod
    def from_dict(cls, d: dict) -> "World":
        try:
            objs = [WorldObject(**o) for o in d.get("objects", [])]
            fluids = [FluidBody(**f) for f in d.get("fluids", [])]
            robot = RobotPlacement(**d.get("robot", {}))
            sensors = [Sensor(**s) for s in d.get("sensors", [])]
            return cls(name=d.get("name", "未命名世界"),
                       description=d.get("description", ""),
                       units=d.get("units", "m"), gravity=float(d.get("gravity", 9.80665)),
                       environment=d.get("environment", "empty"),
                       objects=objs, fluids=fluids, robot=robot, sensors=sensors,
                       custom_fluids=d.get("custom_fluids", []),
                       lighting=d.get("lighting", {}), georeference=d.get("georeference"),
                       metadata=d.get("metadata", {}), schema=d.get("schema", SCHEMA))
        except TypeError as e:
            raise WorldError(f"世界字段不匹配：{e}") from e


# ---------------------------------------------------------------- 环境预设
def _box(oid: str, name: str, pos: list[float], size: list[float],
         color: str = "#5a6678", semantic: str = "", opacity: float = 1.0) -> WorldObject:
    return WorldObject(oid, "box", name, pos, [0, 0, 0], size, color=color,
                       opacity=opacity, semantic=semantic)


def presets() -> dict[str, str]:
    return {
        "pool": "8x4m 泳池 + 池边 + 池水",
        "lab": "6x4m 实验室 + 工作台 + 水槽",
        "kitchen": "4x3m 厨房 + 台面 + 水槽/水渍",
        "greenhouse": "10x6m 温室 + 种植槽 + 灌溉罐",
        "pipeline": "6m 管道 + 检查机器人",
        "factory": "12x8m 车间 + 冷却液罐 + 地坪",
        "outdoor": "20x20m 室外 + 地形 + 水坑",
        "aquarium": "1.2x0.6m 水族箱",
    }


def from_preset(key: str) -> World:
    if key == "pool":
        w = World("泳池清洗实验", "8x4m，水深 1.2m；泳池机器人的典型场景。", environment="pool")
        w.add(_box("deck", "池边地坪", [0, 0, 0], [10.0, 6.0, 0.1], "#6b7280", "floor"))
        w.add(_box("pool_shell", "池体", [0, 0, 0.1], [8.0, 4.0, 1.5],
                   "#34495e", "pool", opacity=0.25))
        w.add_fluid(FluidBody("water", "pool", "water", "池水", [0, 0, 0.1],
                              [8.0, 4.0, 1.5], level=0.8, temperature_c=26, salinity_ppt=2))
        w.sensors = [Sensor("level", "level", [0, 0, 1.5], "water", "m"),
                     Sensor("temp", "temperature", [0, 0, 2.0], "water", "C"),
                     Sensor("turb", "turbidity", [0, 0, 2.0], "water", "NTU")]
        w.robot = RobotPlacement("assemblies/m1_pen.json", [4.5, 0, 0.1], 0, "pool_clean")
        w.lighting = {"sun_azimuth_deg": 135, "sun_elevation_deg": 55,
                      "intensity": 1.2, "ambient": 0.45, "sky": "#0a1622"}
        return w
    if key == "lab":
        w = World("实验室水槽实验", "6x4m 实验室；工作台 + 0.6m 水槽。", environment="lab")
        w.add(_box("floor", "地面", [0, 0, 0], [6.0, 4.0, 0.1], "#4b5563", "floor"))
        w.add(_box("bench", "工作台", [-1.2, 0.4, 0.1], [2.0, 0.8, 0.85], "#8a6a3f", "table"))
        w.add(_box("sink", "水槽", [1.4, 0, 0.1], [0.8, 0.6, 0.4], "#9aa7b8", "tank"))
        w.add_fluid(FluidBody("water", "tank", "water", "水槽水", [1.4, 0, 0.1],
                              [0.8, 0.6, 0.4], level=0.7, temperature_c=22))
        w.sensors = [Sensor("level", "level", [1.4, 0, 0.5], "water", "m"),
                     Sensor("pressure", "pressure", [1.4, 0, 0.3], "water", "Pa")]
        w.robot = RobotPlacement("assemblies/bench_arm.json", [0, 0, 0.1], 0, "manipulate")
        return w
    if key == "kitchen":
        w = World("厨房湿区", "4x3m；台面、水槽和地面水渍。", environment="kitchen")
        w.add(_box("floor", "地面", [0, 0, 0], [4.0, 3.0, 0.1], "#5f6b7a", "floor", 1.0))
        w.add(_box("counter", "台面", [-0.8, 0, 0.1], [2.0, 0.7, 0.9], "#d8d2c4", "table"))
        w.add(_box("sink", "水槽", [0.4, 0, 0.1], [0.6, 0.5, 0.3], "#aeb9c6", "tank"))
        w.add_fluid(FluidBody("water", "tank", "water", "水槽水", [0.4, 0, 0.1],
                              [0.6, 0.5, 0.3], level=0.55, temperature_c=35))
        w.add_fluid(FluidBody("spill", "puddle", "water", "地面水渍", [-0.2, -1.2, 0.1],
                              [1.0, 0.6, 0.005], level=1.0, volume_m3=0.002))
        w.sensors = [Sensor("level", "level", [0.4, 0, 0.4], "water", "m")]
        w.robot = RobotPlacement("assemblies/m1_pen.json", [1.2, 0.8, 0.1], 180, "wipe")
        return w
    if key == "greenhouse":
        w = World("温室灌溉", "10x6m 温室；种植槽 + 1m³ 灌溉罐。", environment="greenhouse")
        w.add(_box("floor", "地面", [0, 0, 0], [10.0, 6.0, 0.1], "#4f5b45", "floor"))
        for i, x in enumerate((-3.0, 0.0, 3.0)):
            w.add(_box(f"bed{i}", f"种植槽 {i+1}", [x, 0, 0.1], [1.2, 4.0, 0.35], "#6b4f2a", "obstacle"))
        w.add(_box("tank_shell", "灌溉罐", [4.2, 0, 0.1], [1.0, 1.0, 1.2], "#7d8b99", "tank"))
        w.add_fluid(FluidBody("water", "tank", "water", "灌溉水", [4.2, 0, 0.1],
                              [1.0, 1.0, 1.2], level=0.75, temperature_c=24))
        w.sensors = [Sensor("level", "level", [4.2, 0, 1.3], "water", "m"),
                     Sensor("flow", "flow", [4.2, 0, 0.6], "water", "L/min")]
        w.robot = RobotPlacement("assemblies/m1_pen.json", [0, -2.4, 0.1], 90, "irrigate")
        return w
    if key == "pipeline":
        w = World("管道检查", "6m 水平管道；水 + 检查机器人。", environment="pipeline")
        w.add(_box("floor", "地面", [0, 0, 0], [8.0, 3.0, 0.1], "#3f4a57", "floor"))
        w.add(WorldObject("pipe", "cylinder", "管道", [0, 0, 0.6], [90, 0, 0],
                          [1, 1, 1], radius=0.3, height=6.0, color="#7f8c9a",
                          opacity=0.45, semantic="pipe"))
        w.add_fluid(FluidBody("water", "pipe", "water", "管道水", [0, 0, 0.3],
                              [1, 1, 1], radius=0.3, height=6.0, level=0.6,
                              flow_m3_s=0.002, temperature_c=18))
        w.sensors = [Sensor("flow", "flow", [0, 0, 0.3], "water", "m3/s"),
                     Sensor("pressure", "pressure", [2.8, 0, 0.3], "water", "Pa")]
        w.robot = RobotPlacement("assemblies/bench_joint.json", [0, 0, 0.1], 0, "inspect")
        return w
    if key == "factory":
        w = World("车间冷却液", "12x8m；冷却液罐 + 泄漏水坑。", environment="factory")
        w.add(_box("floor", "地坪", [0, 0, 0], [12.0, 8.0, 0.1], "#4a4f57", "floor"))
        w.add(_box("tank_shell", "冷却液罐", [-3.5, 0, 0.1], [1.2, 1.2, 1.5], "#6d7682", "tank"))
        w.add_fluid(FluidBody("coolant", "tank", "glycol50", "冷却液", [-3.5, 0, 0.1],
                              [1.2, 1.2, 1.5], level=0.65, temperature_c=40))
        w.add_fluid(FluidBody("spill", "puddle", "glycol50", "泄漏", [0.5, -2.0, 0.1],
                              [2.0, 1.2, 0.01], level=1.0, volume_m3=0.02))
        w.sensors = [Sensor("level", "level", [-3.5, 0, 1.6], "coolant", "m"),
                     Sensor("temp", "temperature", [-3.5, 0, 1.2], "coolant", "C")]
        w.robot = RobotPlacement("assemblies/m1_pen.json", [2, 1, 0.1], 180, "inspect")
        return w
    if key == "outdoor":
        w = World("室外地形", "20x20m；缓坡 + 水坑；用于户外/农业机器人。", environment="outdoor")
        w.add(_box("ground", "地面", [0, 0, 0], [20.0, 20.0, 0.1], "#4e5b43", "ground"))
        w.add(WorldObject("slope", "box", "缓坡", [0, 4, 0.1], [0, 0, 0],
                          [12, 4, 0.3], color="#55624a", semantic="obstacle"))
        w.add_fluid(FluidBody("puddle", "puddle", "water", "水坑", [2, -3, 0.1],
                              [3.0, 2.0, 0.15], level=0.6, temperature_c=16,
                              volume_m3=0.54))
        w.sensors = [Sensor("level", "level", [2, -3, 0.2], "puddle", "m")]
        w.robot = RobotPlacement("assemblies/rover_base.json", [0, 0, 0.1], 0, "traverse")
        return w
    if key == "aquarium":
        w = World("水族箱", "1.2x0.6x0.6m 玻璃缸；海水/淡水实验。", environment="aquarium")
        w.add(_box("floor", "地面", [0, 0, 0], [2.0, 1.5, 0.1], "#3b4652", "floor"))
        w.add(_box("glass", "缸体", [0, 0, 0.1], [1.2, 0.6, 0.6], "#8fd3ff", "tank", 0.18))
        w.add_fluid(FluidBody("water", "tank", "seawater", "海水", [0, 0, 0.1],
                              [1.2, 0.6, 0.6], level=0.8, temperature_c=25, salinity_ppt=35))
        w.sensors = [Sensor("level", "level", [0, 0, 0.7], "water", "m"),
                     Sensor("temp", "temperature", [0, 0, 0.45], "water", "C")]
        w.robot = RobotPlacement("assemblies/bench_joint.json", [0, 0, 0.1], 0, "observe")
        return w
    raise WorldError(f"未知环境预设：{key}；可用：{', '.join(presets())}")


__all__ = ["SCHEMA", "WorldError", "WorldObject", "FluidBody", "RobotPlacement",
           "Sensor", "World", "presets", "from_preset"]
