"""AquaTwin 核心：覆盖 → 阻力/泵 → 时间/能耗 → 过滤 → 成本/回收期。

所有公式都在报告里展开；输入是场景 JSON，输出是确定性 dict。
"""

from __future__ import annotations

import copy
import math
from dataclasses import asdict

from . import coverage as cv
from .scenario import Study

G = 9.80665


def water_density(temp_c: float, salinity_ppt: float) -> float:
    """工程近似：20°C 淡水 998.2；盐度 +0.8 kg/m3/ppt；温度 -0.25 kg/m3/K。"""
    return max(950.0, 998.2 + 0.8 * salinity_ppt - 0.25 * (temp_c - 20.0))


def run(study: Study) -> dict:
    v = study.validate()
    if not v["ok"]:
        raise ValueError("场景校验失败：" + "；".join(v["errors"]))
    p, r, ft, ec = study.pool, study.robot, study.filter, study.economics
    cov = cv.plan(p, r)
    rho = water_density(p.water_temp_c, p.salinity_ppt)
    drag = 0.5 * rho * r.drag_cd * r.body_area_m2 * r.speed_m_s ** 2
    drive_w = drag * r.speed_m_s / r.drive_efficiency + r.brush_power_w + r.electronics_power_w
    pump_hyd_w = rho * G * r.pump_flow_m3_s * r.pump_head_m
    pump_shaft_w = pump_hyd_w / r.pump_efficiency
    total_power_w = drive_w + pump_shaft_w

    active_s = cov.path_length_m / r.speed_m_s + cov.turns * r.turn_time_s
    active_h = active_s / 3600.0
    active_energy_wh = total_power_w * active_h
    usable = max(1e-9, r.battery_wh * 0.8)
    charges = max(0, int(math.ceil(active_energy_wh / usable)) - 1)
    charge_h = charges * r.charge_time_h
    total_h = active_h + charge_h
    energy_kwh = active_energy_wh / 1000.0

    captured_g = p.volume * p.debris_g_m3 * ft.capture_efficiency
    filter_cycles = captured_g / ft.capacity_g if ft.capacity_g else 0.0
    pressure_rise = captured_g / 100.0 * ft.pressure_rise_kpa_per_100g
    backwash_cost = filter_cycles * ft.backwash_cost_cny
    backwash_water_l = filter_cycles * 200.0

    energy_cost = energy_kwh * ec.electricity_cny_kwh
    supervision_cost = ec.supervision_h_per_cleaning * ec.labor_cny_h
    annual_cleanings = max(1e-9, ec.cleanings_per_week * 52.0)
    maintenance_per = ec.maintenance_cny_year / annual_cleanings
    depreciation_per = ec.robot_capex_cny / (ec.robot_life_years * annual_cleanings)
    operating_cost = energy_cost + backwash_cost + supervision_cost + maintenance_per
    cost_per_cleaning = operating_cost + depreciation_per
    revenue = ec.service_price_cny
    margin = revenue - cost_per_cleaning
    manual_cost = ec.manual_hours_per_cleaning * ec.labor_cny_h + ec.chemical_cny_per_cleaning
    savings = manual_cost - operating_cost

    annual_revenue = revenue * annual_cleanings
    annual_operating = operating_cost * annual_cleanings
    annual_profit = annual_revenue - annual_operating
    annual_depreciation = ec.robot_capex_cny / ec.robot_life_years
    annual_net = annual_profit - annual_depreciation
    annual_savings = savings * annual_cleanings

    payback_service = (ec.robot_capex_cny / (annual_profit / 12.0)
                       if annual_profit > 0 else None)
    payback_savings = (ec.robot_capex_cny / (annual_savings / 12.0)
                       if annual_savings > 0 else None)
    roi_1y = (annual_net / ec.robot_capex_cny * 100.0) if ec.robot_capex_cny else None

    warnings = list(v["warnings"])
    if pressure_rise > ft.max_pressure_kpa:
        warnings.append(f"过滤压升 {pressure_rise:.1f} kPa 超过上限 {ft.max_pressure_kpa:.1f}；"
                        "需中途清洗/反冲洗")
    if charges:
        warnings.append(f"单次清洁需要 {charges} 次补电，已计入时间")
    if cov.coverage_pct < 99.0:
        warnings.append(f"覆盖率 {cov.coverage_pct:.1f}% < 99%；可能需要二次路径")
    if savings <= 0:
        warnings.append("相对人工没有运行成本优势；回收期不成立")
    if p.debris_g_m3 == 0:
        warnings.append("碎屑浓度为 0：过滤/反冲洗结果没有意义")

    results = {
        "pool_volume_m3": p.volume,
        "water_mass_kg": p.volume * rho,
        "water_density_kg_m3": rho,
        "effective_swath_m": cov.effective_swath_m,
        "lanes": cov.lanes,
        "path_length_m": cov.path_length_m,
        "coverage_pct": cov.coverage_pct,
        "turns": cov.turns,
        "active_time_min": active_h * 60.0,
        "charge_time_min": charge_h * 60.0,
        "total_time_min": total_h * 60.0,
        "charges": charges,
        "drag_n": drag,
        "drive_power_w": drive_w,
        "pump_hydraulic_w": pump_hyd_w,
        "pump_shaft_w": pump_shaft_w,
        "total_power_w": total_power_w,
        "energy_wh": active_energy_wh,
        "energy_kwh": energy_kwh,
        "debris_captured_g": captured_g,
        "filter_cycles": filter_cycles,
        "filter_pressure_rise_kpa": pressure_rise,
        "backwash_water_l": backwash_water_l,
        "energy_cost_cny": energy_cost,
        "backwash_cost_cny": backwash_cost,
        "supervision_cost_cny": supervision_cost,
        "maintenance_per_cleaning_cny": maintenance_per,
        "depreciation_per_cleaning_cny": depreciation_per,
        "operating_cost_cny": operating_cost,
        "cost_per_cleaning_cny": cost_per_cleaning,
        "service_price_cny": revenue,
        "margin_per_cleaning_cny": margin,
        "manual_cost_cny": manual_cost,
        "savings_per_cleaning_cny": savings,
        "annual_cleanings": annual_cleanings,
        "annual_revenue_cny": annual_revenue,
        "annual_operating_cny": annual_operating,
        "annual_profit_cny": annual_profit,
        "annual_net_after_depreciation_cny": annual_net,
        "annual_savings_cny": annual_savings,
        "payback_service_months": payback_service,
        "payback_savings_months": payback_savings,
        "roi_1y_pct": roi_1y,
        "manual_labor_h": ec.manual_hours_per_cleaning,
        "supervision_h": ec.supervision_h_per_cleaning,
        "labor_hours_saved": ec.manual_hours_per_cleaning - ec.supervision_h_per_cleaning,
    }
    assumptions = [
        "水密度用 998.2 + 0.8*盐度 - 0.25*(温度-20) 的工程近似；不是实测",
        "机器人阻力按 0.5*rho*Cd*A*v^2；Cd/面积需实物/CFD 标定",
        "泵功率按 rho*g*Q*H/效率；未计管路损失/过滤器堵塞曲线",
        "过滤按碎屑全部进入过滤器、捕获率固定；未计旁通/回流",
        "电池可用容量按 80%；补电时间按场景值；未计充电效率",
        "价格为示例假设，不是市场报价；ROI 仅作方案比较",
        "覆盖是矩形 boustrophedon 近似；不含障碍/斜池/水流",
    ]
    return {
        "schema": "aquatwin.result/1",
        "study": study.name,
        "description": study.description,
        "inputs": study.to_dict(),
        "coverage": asdict(cov),
        "results": results,
        "assumptions": assumptions,
        "warnings": warnings,
        "validation": v,
    }


def sensitivity(study: Study) -> list[dict]:
    """关键参数 ± 的确定性敏感性；用于报告里的“别只信一个点”。"""
    variants = []
    specs = [
        ("基准", None, None),
        ("速度 -20%", "speed_m_s", 0.8),
        ("速度 +20%", "speed_m_s", 1.2),
        ("清洁宽度 -10%", "swath_m", 0.9),
        ("清洁宽度 +10%", "swath_m", 1.1),
    ]
    for label, field, factor in specs:
        s = copy.deepcopy(study)
        if field:
            setattr(s.robot, field, getattr(s.robot, field) * factor)
        r = run(s)["results"]
        variants.append({"variant": label, "time_min": r["total_time_min"],
                         "energy_wh": r["energy_wh"], "cost_cny": r["cost_per_cleaning_cny"],
                         "coverage_pct": r["coverage_pct"]})
    for label, factor in (("碎屑 -50%", 0.5), ("碎屑 +100%", 2.0)):
        s = copy.deepcopy(study)
        s.pool.debris_g_m3 *= factor
        r = run(s)["results"]
        variants.append({"variant": label, "time_min": r["total_time_min"],
                         "energy_wh": r["energy_wh"], "cost_cny": r["cost_per_cleaning_cny"],
                         "coverage_pct": r["coverage_pct"]})
    return variants


__all__ = ["G", "water_density", "run", "sensitivity"]
