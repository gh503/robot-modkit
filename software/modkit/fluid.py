"""流体材料库与工程计算：给机器人/世界仿真一个可解释的物性层。

这不是 CFD。它做三件事：
  1) 用统一 schema 描述流体（密度/粘度/表面张力/屈服应力/压缩性/温度/盐度…）；
  2) 给出可手算复核的工程公式（雷诺/阻力/管道压降/罐排空/泵功率…）；
  3) 给 `fluid_sim` / `world` 提供材料与边界条件。

所有物性都是**典型工程值**，不是实验室实测；温度/盐度模型是近似，用于方案比较。
"""

from __future__ import annotations

import json
import math
import pathlib
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Iterable

G = 9.80665


class FluidError(ValueError):
    pass


@dataclass(frozen=True)
class Fluid:
    key: str
    name: str
    name_en: str
    category: str                     # water/oil/gas/solution/food/slurry/foam
    density: float                    # kg/m3 @ 20C
    viscosity: float                  # Pa·s (dynamic) @ 20C
    surface_tension: float = 0.0      # N/m
    yield_stress: float = 0.0         # Pa；Bingham 屈服应力
    bulk_modulus: float = 2.2e9       # Pa
    vapor_pressure: float = 0.0       # Pa
    ph: float | None = None
    temperature_c: float = 20.0
    color: str = "#4da3ff"
    opacity: float = 0.55
    thermal_conductivity: float = 0.6 # W/mK
    specific_heat: float = 4180.0     # J/kgK
    thermal_expansion: float = 2.0e-4 # 1/K
    viscosity_b_k: float = 1800.0     # Andrade 近似：mu=mu_ref*exp(B(1/T-1/Tref))
    notes: str = ""
    source: str = "engineering handbook typical value"

    def __post_init__(self) -> None:
        if not self.key or not self.name:
            raise FluidError("流体需要 key/name")
        if self.density <= 0 or self.viscosity <= 0:
            raise FluidError(f"{self.key}: density/viscosity 必须 >0")
        if self.surface_tension < 0 or self.yield_stress < 0:
            raise FluidError(f"{self.key}: 表面张力/屈服应力不能为负")
        if not 0 <= self.opacity <= 1:
            raise FluidError(f"{self.key}: opacity 必须在 0..1")
        if self.category not in ("water", "oil", "gas", "solution", "food", "slurry", "foam"):
            raise FluidError(f"{self.key}: 未知 category {self.category}")

    @property
    def kinematic_viscosity(self) -> float:
        return self.viscosity / self.density

    @property
    def is_gas(self) -> bool:
        return self.category == "gas"

    @property
    def is_bingham(self) -> bool:
        return self.yield_stress > 0

    @property
    def is_newtonian(self) -> bool:
        return self.yield_stress <= 0

    def at_temperature(self, temp_c: float) -> "Fluid":
        """近似温度修正：液体 Andrade + 热膨胀；气体理想气体。"""
        if temp_c < -273.15:
            raise FluidError("温度低于绝对零度")
        t0 = self.temperature_c + 273.15
        t = temp_c + 273.15
        mu = self.viscosity * math.exp(self.viscosity_b_k * (1.0 / t - 1.0 / t0))
        if self.is_gas:
            rho = self.density * t0 / t
        else:
            rho = self.density / (1.0 + self.thermal_expansion * (temp_c - self.temperature_c))
        return replace(self, density=rho, viscosity=max(1e-9, mu), temperature_c=temp_c)

    def at_salinity(self, salinity_ppt: float) -> "Fluid":
        """海水/盐水近似：密度 +0.8 kg/m3 per ppt；粘度略升。仅 water。"""
        if self.category != "water":
            raise FluidError("盐度只适用于 water 类")
        if salinity_ppt < 0 or salinity_ppt > 300:
            raise FluidError("盐度必须在 0..300 ppt")
        rho = self.density + 0.8 * salinity_ppt
        mu = self.viscosity * (1.0 + 0.02 * salinity_ppt / 35.0)
        return replace(self, key=self.key, density=rho, viscosity=mu,
                       notes=(self.notes + f"；盐度 {salinity_ppt:g} ppt 近似").strip("；"))

    def with_properties(self, **kw: Any) -> "Fluid":
        allowed = set(self.__dataclass_fields__)
        bad = set(kw) - allowed
        if bad:
            raise FluidError(f"未知属性：{sorted(bad)}")
        return replace(self, **kw)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["kinematic_viscosity"] = round(self.kinematic_viscosity, 9)
        d["is_gas"] = self.is_gas
        d["is_bingham"] = self.is_bingham
        return d


# 典型工程值（20C 附近）；不要当供应商数据或实验结果。
_BUILTIN: tuple[Fluid, ...] = (
    Fluid("water", "淡水", "Fresh water", "water", 998.2, 1.002e-3,
          0.0728, 0, 2.2e9, 2339, 7.0, color="#3d8fd1", opacity=0.55,
          notes="20C；泳池/灌溉/清洗的基准流体"),
    Fluid("seawater", "海水", "Seawater", "water", 1025.0, 1.07e-3,
          0.0720, 0, 2.2e9, 2339, 8.1, color="#1f6f9f", opacity=0.62,
          notes="35 ppt 典型值；盐度可用 at_salinity 调整"),
    Fluid("distilled", "蒸馏水", "Distilled water", "water", 997.0, 0.89e-3,
          0.0720, 0, 2.2e9, 2339, 7.0, color="#67b7e8", opacity=0.45),
    Fluid("hydraulic_oil", "液压油 ISO46", "Hydraulic oil ISO46", "oil", 870.0, 0.090,
          0.030, 0, 1.5e9, 10, None, color="#b8862f", opacity=0.75,
          thermal_conductivity=0.14, specific_heat=1900, thermal_expansion=7e-4,
          viscosity_b_k=5000, notes="20C 近似；40C 约 46 cSt"),
    Fluid("engine_oil", "机油 5W-30", "Engine oil 5W-30", "oil", 850.0, 0.080,
          0.030, 0, 1.5e9, 10, None, color="#8a6a1f", opacity=0.8,
          thermal_conductivity=0.15, specific_heat=2000, thermal_expansion=7e-4,
          viscosity_b_k=4500),
    Fluid("air", "空气", "Air", "gas", 1.204, 1.825e-5,
          0.0, 0, 101325, 0, None, color="#cfe8ff", opacity=0.06,
          thermal_conductivity=0.0257, specific_heat=1005, thermal_expansion=3.4e-3,
          viscosity_b_k=120, notes="20C, 1 atm；可压缩气体"),
    Fluid("glycol50", "乙二醇 50%", "Glycol 50%", "solution", 1075.0, 0.006,
          0.050, 0, 2.4e9, 200, 7.5, color="#7bc8a4", opacity=0.6,
          thermal_conductivity=0.38, specific_heat=3300, viscosity_b_k=3000,
          notes="冷却液典型值"),
    Fluid("ethanol", "乙醇", "Ethanol", "solution", 789.0, 1.2e-3,
          0.0223, 0, 1.1e9, 5900, 7.0, color="#d6c7ff", opacity=0.45,
          thermal_conductivity=0.17, specific_heat=2440, viscosity_b_k=1500),
    Fluid("glycerin", "甘油", "Glycerin", "solution", 1260.0, 1.412,
          0.063, 0, 4.35e9, 0.02, 7.0, color="#e8d7a8", opacity=0.7,
          thermal_conductivity=0.29, specific_heat=2430, viscosity_b_k=5000),
    Fluid("milk", "牛奶", "Milk", "food", 1030.0, 2.0e-3,
          0.052, 0, 2.2e9, 2300, 6.6, color="#f2efe6", opacity=0.85,
          thermal_conductivity=0.56, specific_heat=3900, viscosity_b_k=2200),
    Fluid("latex_paint", "乳胶漆", "Latex paint", "slurry", 1200.0, 0.100,
          0.035, 2.0, 2.0e9, 2300, 8.5, color="#d9d9d9", opacity=0.95,
          thermal_conductivity=0.3, specific_heat=2000, viscosity_b_k=3500,
          notes="Bingham 近似；屈服应力 2 Pa"),
    Fluid("ketchup", "番茄酱", "Ketchup", "food", 1100.0, 0.500,
          0.050, 15.0, 2.0e9, 2300, 4.2, color="#b3261e", opacity=0.95,
          thermal_conductivity=0.4, specific_heat=3000, viscosity_b_k=4000,
          notes="Bingham 近似；仅用于演示，不用于食品工程认证"),
    Fluid("slurry20", "砂水浆 20%", "Sand slurry 20%", "slurry", 1200.0, 0.020,
          0.060, 0.5, 2.2e9, 2339, 7.0, color="#9b8060", opacity=0.85,
          thermal_conductivity=0.5, specific_heat=3000, viscosity_b_k=2500,
          notes="20% 体积砂；沉降/磨损需另算"),
    Fluid("foam", "泡沫", "Foam", "foam", 100.0, 0.050,
          0.030, 5.0, 1.0e6, 101325, 7.0, color="#f4f7fb", opacity=0.75,
          thermal_conductivity=0.04, specific_heat=1500, viscosity_b_k=3000,
          notes="低密度 Bingham 近似；压缩性显著"),
    Fluid("drilling_mud", "钻井泥浆", "Drilling mud", "slurry", 1200.0, 0.030,
          0.050, 5.0, 2.0e9, 2339, 8.5, color="#6f5a3e", opacity=0.9,
          thermal_conductivity=0.6, specific_heat=2500, viscosity_b_k=3000,
          notes="Bingham 近似；仅方案比较"),
)

FLUIDS: dict[str, Fluid] = {f.key: f for f in _BUILTIN}


def get(key: str) -> Fluid:
    try:
        return FLUIDS[key]
    except KeyError as e:
        raise FluidError(f"未知流体：{key}；可用：{', '.join(sorted(FLUIDS))}") from e


def list_fluids(category: str | None = None) -> list[Fluid]:
    rows = sorted(FLUIDS.values(), key=lambda f: f.key)
    if category:
        rows = [f for f in rows if f.category == category]
    return rows


def register(fluid: Fluid, *, replace_existing: bool = False) -> None:
    if fluid.key in FLUIDS and not replace_existing:
        raise FluidError(f"流体已存在：{fluid.key}")
    FLUIDS[fluid.key] = fluid


def load_file(path: str | pathlib.Path, *, replace_existing: bool = False) -> list[Fluid]:
    """从 JSON 加载自定义流体；支持单个对象或数组。"""
    d = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    rows = d if isinstance(d, list) else [d]
    out = []
    for row in rows:
        try:
            f = Fluid(**row)
        except TypeError as e:
            raise FluidError(f"字段不匹配：{e}") from e
        register(f, replace_existing=replace_existing)
        out.append(f)
    return out


def save_file(path: str | pathlib.Path, keys: Iterable[str] | None = None) -> pathlib.Path:
    rows = [get(k).to_dict() for k in (keys or sorted(FLUIDS))]
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


# ---------------------------------------------------------------- 无量纲数
def reynolds(fluid: Fluid, velocity: float, length: float) -> float:
    if length <= 0:
        raise FluidError("特征长度必须 >0")
    return fluid.density * abs(velocity) * length / fluid.viscosity


def froude(velocity: float, length: float, g: float = G) -> float:
    if length <= 0:
        raise FluidError("特征长度必须 >0")
    return abs(velocity) / math.sqrt(g * length)


def weber(fluid: Fluid, velocity: float, length: float) -> float:
    if fluid.surface_tension <= 0:
        return math.inf
    return fluid.density * velocity**2 * length / fluid.surface_tension


def capillary_length(fluid: Fluid) -> float:
    if fluid.surface_tension <= 0:
        return 0.0
    return math.sqrt(fluid.surface_tension / (fluid.density * G))


def drag_force(fluid: Fluid, velocity: float, area: float, cd: float = 1.0) -> float:
    if area < 0:
        raise FluidError("面积不能为负")
    return 0.5 * fluid.density * cd * area * velocity * abs(velocity)


def buoyant_force(fluid: Fluid, volume: float, g: float = G) -> float:
    if volume < 0:
        raise FluidError("体积不能为负")
    return fluid.density * volume * g


def terminal_velocity(fluid: Fluid, diameter: float, particle_density: float,
                      cd: float = 0.47, max_iter: int = 80) -> float:
    """球形颗粒终端速度；迭代 Re 修正。"""
    if diameter <= 0 or particle_density <= 0:
        raise FluidError("直径/颗粒密度必须 >0")
    area = math.pi * diameter**2 / 4.0
    volume = math.pi * diameter**3 / 6.0
    v = 0.1
    for _ in range(max_iter):
        re = reynolds(fluid, v, diameter)
        cd_eff = cd if re > 1.0 else 24.0 / max(re, 1e-9)
        # (rho_p-rho_f) V g = 0.5 rho_f cd A v^2
        num = 2.0 * (particle_density - fluid.density) * volume * G
        den = fluid.density * cd_eff * area
        if num <= 0:
            return 0.0
        v_new = math.sqrt(max(0.0, num / den))
        if abs(v_new - v) < 1e-6:
            return v_new
        v = v_new
    return v


# ---------------------------------------------------------------- 管道/罐/泵
def _friction_factor(re: float, roughness: float, diameter: float) -> float:
    if re <= 0:
        return 0.0
    if re < 2300:
        return 64.0 / re
    # Haaland 显式近似
    rr = max(0.0, roughness) / max(diameter, 1e-9)
    return 1.0 / (-1.8 * math.log10((rr / 3.7) ** 1.11 + 6.9 / re)) ** 2


def pipe_drop(fluid: Fluid, flow_m3_s: float, diameter: float, length: float,
              roughness: float = 1.5e-6, minor_k: float = 0.0,
              g: float = G) -> dict:
    """圆管稳态压降：Darcy-Weisbach + 局部损失；非牛顿只给等效粘度提示。"""
    if diameter <= 0 or length < 0:
        raise FluidError("直径必须 >0，长度不能为负")
    area = math.pi * diameter**2 / 4.0
    velocity = flow_m3_s / area
    re = reynolds(fluid, velocity, diameter)
    f = _friction_factor(re, roughness, diameter)
    dp_major = f * (length / diameter) * 0.5 * fluid.density * velocity**2
    dp_minor = minor_k * 0.5 * fluid.density * velocity**2
    return {
        "fluid": fluid.key, "flow_m3_s": flow_m3_s, "velocity_m_s": velocity,
        "diameter_m": diameter, "length_m": length, "reynolds": re,
        "friction_factor": f, "dp_major_pa": dp_major, "dp_minor_pa": dp_minor,
        "dp_total_pa": dp_major + dp_minor,
        "head_loss_m": (dp_major + dp_minor) / (fluid.density * g),
        "regime": "laminar" if re < 2300 else "turbulent",
        "warning": ("非牛顿流体：压降按等效粘度估算，需流变仪/管试"
                    if fluid.is_bingham else ""),
    }


def pump_power(fluid: Fluid, flow_m3_s: float, head_m: float,
               efficiency: float = 0.65, g: float = G) -> dict:
    if not 0 < efficiency <= 1:
        raise FluidError("效率必须在 (0,1]")
    hydraulic = fluid.density * g * flow_m3_s * head_m
    shaft = hydraulic / efficiency
    return {"hydraulic_w": hydraulic, "shaft_w": shaft,
            "flow_m3_s": flow_m3_s, "head_m": head_m, "efficiency": efficiency}


def tank_drain_time(tank_area: float, outlet_area: float, height: float,
                    fluid: Fluid, cd: float = 0.62, g: float = G) -> float:
    """无补液、薄壁孔口：t = A_t/(Cd A_o) * sqrt(2h/g)。"""
    if tank_area <= 0 or outlet_area <= 0 or height < 0:
        raise FluidError("面积必须 >0，液位不能为负")
    if outlet_area >= tank_area:
        raise FluidError("出口面积不能大于等于罐面积")
    return (tank_area / (cd * outlet_area)) * math.sqrt(2.0 * height / g)


def orifice_flow(outlet_area: float, height: float, fluid: Fluid,
                 cd: float = 0.62, g: float = G) -> float:
    if outlet_area < 0 or height < 0:
        raise FluidError("面积/液位不能为负")
    return cd * outlet_area * math.sqrt(2.0 * g * height)


def manning_flow(n: float, slope: float, area: float, hydraulic_radius: float) -> float:
    """Manning 明渠均匀流；n 为曼宁系数。"""
    if n <= 0 or area < 0 or hydraulic_radius < 0:
        raise FluidError("n 必须 >0；面积/水力半径不能为负")
    return (1.0 / n) * area * hydraulic_radius ** (2.0 / 3.0) * math.sqrt(max(0.0, slope))


def jet_force(fluid: Fluid, flow_m3_s: float, velocity: float) -> float:
    return fluid.density * flow_m3_s * abs(velocity)


def summarize(fluid: Fluid) -> dict:
    return {
        "key": fluid.key, "name": fluid.name, "category": fluid.category,
        "density_kg_m3": round(fluid.density, 3),
        "viscosity_pa_s": fluid.viscosity,
        "kinematic_viscosity_m2_s": round(fluid.kinematic_viscosity, 9),
        "surface_tension_n_m": fluid.surface_tension,
        "yield_stress_pa": fluid.yield_stress,
        "bulk_modulus_pa": fluid.bulk_modulus,
        "ph": fluid.ph,
        "temperature_c": fluid.temperature_c,
        "is_gas": fluid.is_gas, "is_bingham": fluid.is_bingham,
        "color": fluid.color, "opacity": fluid.opacity,
    }


__all__ = [
    "G", "Fluid", "FluidError", "FLUIDS", "get", "list_fluids", "register",
    "load_file", "save_file", "reynolds", "froude", "weber", "capillary_length",
    "drag_force", "buoyant_force", "terminal_velocity", "pipe_drop", "pump_power",
    "tank_drain_time", "orifice_flow", "manning_flow", "jet_force", "summarize",
]
