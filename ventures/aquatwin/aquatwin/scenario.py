"""AquaTwin 场景 schema：泳池 + 机器人 + 过滤 + 经济假设。

输入全部显式，禁止“默认值藏在代码里”。每个默认值都在 README/报告里标为假设。
"""

from __future__ import annotations

import json
import math
import pathlib
from dataclasses import asdict, dataclass, field

from . import geometry as geo


class ScenarioError(ValueError):
    pass


@dataclass
class Pool:
    length_m: float = 8.0
    width_m: float = 4.0
    depth_m: float = 1.5
    water_temp_c: float = 26.0
    salinity_ppt: float = 2.0
    debris_g_m3: float = 5.0
    shape: str = "rect"
    footprint: list[list[float]] | None = None
    volume_m3: float | None = None
    notes: str = ""

    @property
    def area_m2(self) -> float:
        if self.footprint:
            return geo.polygon_area(self.footprint)
        return self.length_m * self.width_m

    @property
    def volume(self) -> float:
        if self.volume_m3 is not None:
            return self.volume_m3
        if self.shape == "rect":
            return self.length_m * self.width_m * self.depth_m
        if self.shape == "polygon" and self.footprint:
            return self.area_m2 * self.depth_m
        raise ScenarioError("非矩形池必须给 footprint（或显式 volume_m3）")

    def validate(self, errors: list[str]) -> None:
        if self.length_m <= 0 or self.width_m <= 0 or self.depth_m <= 0:
            errors.append("pool length/width/depth 必须 >0")
        if self.volume_m3 is not None and self.volume_m3 <= 0:
            errors.append("pool.volume_m3 必须 >0")
        if self.shape not in ("rect", "polygon"):
            errors.append("pool.shape 只能是 rect/polygon")
        if self.shape == "polygon":
            if not self.footprint:
                errors.append("pool.shape=polygon 时必须给 footprint")
            else:
                try:
                    pts, area = geo.validate_polygon(self.footprint)
                except geo.GeometryError as e:
                    errors.append(f"pool.footprint 非法：{e}")
                else:
                    if area <= 0:
                        errors.append("pool.footprint 面积必须 >0")
                    for (x, y) in pts:
                        if x < -1e-6 or y < -1e-6 or x > self.length_m + 1e-6 or y > self.width_m + 1e-6:
                            errors.append("pool.footprint 必须落在 length_m×width_m 包围盒内（原点左下角）")
                            break
        elif self.footprint:
            errors.append("pool.footprint 只用于 shape=polygon")
        if not -2 <= self.water_temp_c <= 60:
            errors.append("pool.water_temp_c 超出 -2..60")
        if not 0 <= self.salinity_ppt <= 60:
            errors.append("pool.salinity_ppt 超出 0..60")
        if self.debris_g_m3 < 0:
            errors.append("pool.debris_g_m3 不能为负")


@dataclass
class Robot:
    swath_m: float = 0.45
    overlap: float = 0.10
    speed_m_s: float = 0.25
    turn_time_s: float = 4.0
    battery_wh: float = 90.0
    charge_time_h: float = 2.0
    drive_efficiency: float = 0.60
    pump_flow_m3_s: float = 0.0008
    pump_head_m: float = 3.0
    pump_efficiency: float = 0.35
    brush_power_w: float = 25.0
    electronics_power_w: float = 10.0
    body_area_m2: float = 0.12
    drag_cd: float = 1.0
    mass_kg: float = 8.0
    volume_m3: float = 0.006
    notes: str = ""

    @property
    def effective_swath(self) -> float:
        return self.swath_m * (1.0 - self.overlap)

    def validate(self, errors: list[str]) -> None:
        for name, v in (("swath_m", self.swath_m), ("speed_m_s", self.speed_m_s),
                        ("turn_time_s", self.turn_time_s), ("battery_wh", self.battery_wh),
                        ("charge_time_h", self.charge_time_h), ("drive_efficiency", self.drive_efficiency),
                        ("pump_flow_m3_s", self.pump_flow_m3_s), ("pump_head_m", self.pump_head_m),
                        ("pump_efficiency", self.pump_efficiency), ("body_area_m2", self.body_area_m2),
                        ("mass_kg", self.mass_kg), ("volume_m3", self.volume_m3)):
            if v <= 0:
                errors.append(f"robot.{name} 必须 >0")
        if not 0 <= self.overlap < 0.8:
            errors.append("robot.overlap 必须在 0..0.8")
        if not 0 < self.drive_efficiency <= 1:
            errors.append("robot.drive_efficiency 必须在 (0,1]")
        if not 0 < self.pump_efficiency <= 1:
            errors.append("robot.pump_efficiency 必须在 (0,1]")
        if self.drag_cd <= 0:
            errors.append("robot.drag_cd 必须 >0")


@dataclass
class Filter:
    capture_efficiency: float = 0.90
    capacity_g: float = 500.0
    backwash_cost_cny: float = 30.0
    pressure_rise_kpa_per_100g: float = 2.0
    max_pressure_kpa: float = 40.0
    notes: str = ""

    def validate(self, errors: list[str]) -> None:
        if not 0 <= self.capture_efficiency <= 1:
            errors.append("filter.capture_efficiency 必须在 0..1")
        for name, v in (("capacity_g", self.capacity_g),
                        ("backwash_cost_cny", self.backwash_cost_cny),
                        ("pressure_rise_kpa_per_100g", self.pressure_rise_kpa_per_100g),
                        ("max_pressure_kpa", self.max_pressure_kpa)):
            if v < 0:
                errors.append(f"filter.{name} 不能为负")
        if self.capacity_g <= 0:
            errors.append("filter.capacity_g 必须 >0")


@dataclass
class Economics:
    electricity_cny_kwh: float = 0.80
    labor_cny_h: float = 60.0
    service_price_cny: float = 300.0
    robot_capex_cny: float = 6000.0
    maintenance_cny_year: float = 600.0
    robot_life_years: float = 3.0
    supervision_h_per_cleaning: float = 0.15
    cleanings_per_week: float = 5.0
    manual_hours_per_cleaning: float = 1.5
    chemical_cny_per_cleaning: float = 20.0
    notes: str = "价格/工资为示例假设，不是市场报价"

    def validate(self, errors: list[str]) -> None:
        for name, v in (("electricity_cny_kwh", self.electricity_cny_kwh),
                        ("labor_cny_h", self.labor_cny_h),
                        ("service_price_cny", self.service_price_cny),
                        ("robot_capex_cny", self.robot_capex_cny),
                        ("maintenance_cny_year", self.maintenance_cny_year),
                        ("robot_life_years", self.robot_life_years),
                        ("cleanings_per_week", self.cleanings_per_week),
                        ("manual_hours_per_cleaning", self.manual_hours_per_cleaning),
                        ("chemical_cny_per_cleaning", self.chemical_cny_per_cleaning)):
            if v < 0:
                errors.append(f"economics.{name} 不能为负")
        if self.robot_life_years <= 0:
            errors.append("economics.robot_life_years 必须 >0")
        if not 0 <= self.supervision_h_per_cleaning <= 8:
            errors.append("economics.supervision_h_per_cleaning 超出 0..8")


@dataclass
class Study:
    name: str
    pool: Pool = field(default_factory=Pool)
    robot: Robot = field(default_factory=Robot)
    filter: Filter = field(default_factory=Filter)
    economics: Economics = field(default_factory=Economics)
    schema: str = "aquatwin.study/1"
    description: str = ""
    metadata: dict = field(default_factory=dict)

    def validate(self) -> dict:
        errors: list[str] = []
        warnings: list[str] = []
        if self.schema != "aquatwin.study/1":
            errors.append("schema 必须是 aquatwin.study/1")
        if not self.name:
            errors.append("name 不能为空")
        self.pool.validate(errors)
        self.robot.validate(errors)
        self.filter.validate(errors)
        self.economics.validate(errors)
        if self.robot.battery_wh and self.pool.volume > 0:
            pass
        if self.robot.swath_m > min(self.pool.width_m, self.pool.length_m):
            warnings.append("清洁宽度大于池宽/池长；覆盖路径会退化")
        if self.filter.capacity_g <= 0:
            warnings.append("过滤容量为 0")
        return {"ok": not errors, "errors": errors, "warnings": warnings}

    def to_dict(self) -> dict:
        return {"schema": self.schema, "name": self.name, "description": self.description,
                "pool": asdict(self.pool), "robot": asdict(self.robot),
                "filter": asdict(self.filter), "economics": asdict(self.economics),
                "metadata": self.metadata}

    @classmethod
    def from_dict(cls, d: dict) -> "Study":
        try:
            return cls(name=d.get("name", "未命名泳池"),
                       description=d.get("description", ""),
                       schema=d.get("schema", "aquatwin.study/1"),
                       pool=Pool(**d.get("pool", {})),
                       robot=Robot(**d.get("robot", {})),
                       filter=Filter(**d.get("filter", {})),
                       economics=Economics(**d.get("economics", {})),
                       metadata=d.get("metadata", {}))
        except TypeError as e:
            raise ScenarioError(f"字段不匹配：{e}") from e

    @classmethod
    def load(cls, path: str | pathlib.Path) -> "Study":
        try:
            d = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ScenarioError(f"JSON 解析失败：{e}") from e
        return cls.from_dict(d)

    def save(self, path: str | pathlib.Path) -> pathlib.Path:
        p = pathlib.Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")
        return p


__all__ = ["ScenarioError", "Pool", "Robot", "Filter", "Economics", "Study"]
