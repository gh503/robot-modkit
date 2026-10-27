"""把 World + Fluid 变成可复现实验：域/水箱/管道/传感器 + 指标/帧。

实验输出三件套：
  metrics.json  —— 机器可读，CI 回归用
  frames.json   —— 查看器/动画用（浅水高度场）
  report.md     —— 人读，带模型边界
"""

from __future__ import annotations

import csv
import json
import math
import pathlib
import random
from dataclasses import dataclass
from typing import Any

import numpy as np

from . import fluid as fl
from . import fluid_sim as fs
from . import world as wd

G = fl.G


@dataclass
class WorldRun:
    world: wd.World
    duration: float = 5.0
    dt: float | None = None
    dx: float = 0.2
    frame_every: int = 10
    out: str | None = None

    def __post_init__(self) -> None:
        if self.duration <= 0:
            raise fs.FluidSimError("duration 必须 >0")
        if self.dx <= 0:
            raise fs.FluidSimError("dx 必须 >0")

    def run(self) -> dict:
        v = self.world.validate()
        if not v["ok"]:
            raise fs.FluidSimError("世界校验失败：" + "；".join(v["errors"]))
        result: dict[str, Any] = {
            "world": self.world.name, "environment": self.world.environment,
            "duration_s": self.duration, "fluids": {}, "sensors": {},
            "warnings": list(v["warnings"]),
            "model": "reduced-order: 2D shallow water / 0D tank / steady pipe",
        }
        for body in self.world.fluids:
            result["fluids"][body.id] = self._body(body)
        for s in self.world.sensors:
            result["sensors"][s.id] = self._sensor(s)
        result["robot"] = self._robot()
        if self.out:
            result["outputs"] = self.write(result, self.out)
        return result

    # ------------------------------------------------------------ 单个流体
    def _body(self, body: wd.FluidBody) -> dict:
        fluid = fl.get(body.fluid)
        if body.type in ("pool", "reservoir", "puddle"):
            return self._shallow(body, fluid)
        if body.type == "tank":
            return self._tank(body, fluid)
        if body.type == "pipe":
            return self._pipe(body, fluid)
        return {"type": body.type, "volume_m3": body.volume,
                "warning": "rain 未实现粒子/降雨模型；只做体积记账"}

    def _shallow(self, body: wd.FluidBody, fluid: fl.Fluid) -> dict:
        w, h = body.size[0], body.size[1]
        # 固定 dx 由包围盒决定；多边形只影响 mask，不再用 mask 面积反推 dx。
        # （反推会让 dx 与 mask 网格面积不一致，L 形池会凭空多水、出现假波。）
        dx = min(self.dx, w / 8.0, h / 8.0)
        nx = max(8, int(round(w / dx)))
        ny = max(8, int(round(h / dx)))
        mask = None
        if body.footprint:
            xs = (np.arange(nx) + 0.5) * dx - w / 2
            ys = (np.arange(ny) + 0.5) * dx - h / 2
            gx, gy = np.meshgrid(xs, ys)
            mask = np.array([[wd._point_in_polygon(body.footprint, float(gx[j, i]), float(gy[j, i]))
                              for i in range(nx)] for j in range(ny)], dtype=bool)
            wet_cells = int(np.count_nonzero(mask))
            if wet_cells == 0:
                raise fs.FluidSimError(f"{body.id}: polygon 与网格没有交集；减小 dx")
            area = wet_cells * dx * dx
        else:
            area = w * h
        depth = body.volume / area      # 用实际湿格面积反推初始水深
        if depth <= 0:
            return {"type": body.type, "volume_m3": 0.0, "frames": [],
                    "metrics": {"volume_m3": 0.0, "max_depth_m": 0.0}}
        sim = fs.ShallowWater(fluid, nx=nx, ny=ny, dx=dx, depth=depth, mask=mask,
                              manning=float(body.metadata.get("manning", 0.025)),
                              boundary=body.metadata.get("boundary", "closed"))
        for s in body.metadata.get("sources", []):
            sim.sources.append(fs.Source(float(s["x"]), float(s["y"]),
                                         float(s["rate_m3_s"]),
                                         float(s.get("radius_m", 0.05))))
        frames = []
        i = 0
        while sim.t < self.duration:
            sim.step(self.dt)
            i += 1
            if i % max(1, self.frame_every) == 0 or sim.t >= self.duration:
                frames.append(sim.frame(downsample=max(1, int(body.metadata.get("downsample", 1)))))
        return {"type": body.type, "fluid": fluid.key,
                "capacity_m3": body.capacity_m3, "volume_m3": body.volume,
                "footprint": body.footprint,
                "frames": frames, "metrics": sim.metrics()}

    def _tank(self, body: wd.FluidBody, fluid: fl.Fluid) -> dict:
        height = body.height or body.size[2]
        area = body.capacity_m3 / height
        t = fs.Tank(fluid, area_m2=area, height_m=height,
                    outlet_area_m2=float(body.metadata.get("outlet_area_m2", 0.001)),
                    cd=float(body.metadata.get("cd", 0.62)),
                    inflow_m3_s=float(body.flow_m3_s),
                    level_m=body.depth_m)
        dt = self.dt or min(0.05, self.duration / 100)
        n = max(1, int(math.ceil(self.duration / dt)))
        levels = []
        for i in range(n):
            if t.t >= self.duration:
                break
            t.step(min(dt, self.duration - t.t))
            if i % max(1, self.frame_every) == 0:
                levels.append({"t_s": round(t.t, 4), "level_m": round(float(t.level_m), 6)})
        m = t.metrics()
        return {"type": "tank", "fluid": fluid.key, "area_m2": area,
                "capacity_m3": body.capacity_m3, "levels": levels, "metrics": m}

    def _pipe(self, body: wd.FluidBody, fluid: fl.Fluid) -> dict:
        d = 2.0 * (body.radius or 0.0)
        length = body.height or 0.0
        q = body.flow_m3_s
        if q <= 0 or d <= 0:
            return {"type": "pipe", "fluid": fluid.key, "velocity_m_s": 0.0,
                    "dp_total_pa": 0.0, "warning": "无流量/无直径，只做几何"}
        r = fl.pipe_drop(fluid, q, d, length,
                         roughness=float(body.metadata.get("roughness", 1.5e-6)),
                         minor_k=float(body.metadata.get("minor_k", 0.0)))
        r["capacity_m3"] = body.capacity_m3
        r["volume_m3"] = body.volume
        return r

    # ------------------------------------------------------------ 传感器
    def _sensor(self, s: wd.Sensor) -> dict:
        body = None
        for f in self.world.fluids:
            if f.id == s.target:
                body = f
                break
        if body is None:
            return {"type": s.type, "value": None, "modeled": False,
                    "note": "无 target 流体"}
        fluid = fl.get(body.fluid)
        def noisy(raw: float, unit: str) -> dict:
            d = {"type": s.type, "value": raw, "unit": unit, "modeled": True}
            md = s.metadata if isinstance(s.metadata, dict) else {}
            std = float(md.get("noise_std", 0.0) or 0.0)
            if std > 0:
                seed = int(md.get("noise_seed", 0)) + sum(ord(c) for c in s.id)
                d["raw_value"] = raw
                d["noise_std"] = std
                d["value"] = raw + random.Random(seed).gauss(0.0, std)
                d["noise_seed"] = seed
                d["note"] = "seeded Gaussian sensor noise; not field calibration"
            return d

        if s.type == "level":
            return noisy(body.depth_m, "m")
        if s.type == "pressure":
            d = noisy(fluid.density * G * body.depth_m, "Pa")
            d.setdefault("note", "gauge pressure at bottom")
            return d
        if s.type == "flow":
            return noisy(body.flow_m3_s, "m3/s")
        if s.type == "temperature":
            return noisy(body.temperature_c, "C")
        if s.type == "turbidity":
            return {"type": s.type, "value": None, "unit": "NTU", "modeled": False,
                    "note": "需要水质/颗粒模型；当前不伪造"}
        return {"type": s.type, "value": None, "modeled": False,
                "note": "camera/imu 由其他仿真链提供"}

    # ------------------------------------------------------------ 机器人
    def _robot(self) -> dict:
        md = self.world.robot.metadata if hasattr(self.world.robot, "metadata") else {}
        # RobotPlacement 没有 metadata 字段；从 world.metadata 读
        md = self.world.metadata.get("robot", {}) if isinstance(self.world.metadata, dict) else {}
        area = float(md.get("area_m2", 0.0))
        vol = float(md.get("volume_m3", 0.0))
        speed = float(md.get("speed_m_s", 0.0))
        out = {"assembly": self.world.robot.assembly, "task": self.world.robot.task,
               "modeled": bool(area or vol)}
        if area and speed:
            # 取机器人所在流体的密度；没有则水
            f = fl.get("water")
            for b in self.world.fluids:
                f = fl.get(b.fluid); break
            out["drag_n"] = fl.drag_force(f, speed, area, float(md.get("cd", 1.0)))
            out["drag_fluid"] = f.key
        if vol:
            f = fl.get("water")
            for b in self.world.fluids:
                f = fl.get(b.fluid); break
            out["buoyancy_n"] = fl.buoyant_force(f, vol)
            out["buoyancy_fluid"] = f.key
        if not out["modeled"]:
            out["note"] = "未给 world.metadata.robot.area_m2/volume_m3；不估算阻力/浮力"
        return out

    # ------------------------------------------------------------ 输出
    def write(self, result: dict, out: str) -> dict:
        d = pathlib.Path(out)
        d.mkdir(parents=True, exist_ok=True)
        (d / "metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")
        (d / "frames.json").write_text(json.dumps(
            {k: v.get("frames", v.get("levels", [])) for k, v in result["fluids"].items()},
            ensure_ascii=False) + "\n", encoding="utf-8")
        # 传感器 CSV
        with (d / "sensors.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["id", "type", "value", "unit", "modeled", "note"])
            for k, v in result["sensors"].items():
                w.writerow([k, v.get("type"), v.get("value"), v.get("unit"),
                            v.get("modeled"), v.get("note", "")])
        (d / "report.md").write_text(self.report(result), encoding="utf-8")
        return {"metrics": str(d / "metrics.json"), "frames": str(d / "frames.json"),
                "sensors": str(d / "sensors.csv"), "report": str(d / "report.md")}

    def report(self, result: dict) -> str:
        lines = [f"# 世界仿真报告：{self.world.name}", "",
                 f"- 环境：`{self.world.environment}`",
                 f"- 时长：{self.duration:g}s；dx={self.dx:g}m；模型：{result['model']}",
                 f"- 对象 {len(self.world.objects)}；流体 {len(self.world.fluids)}；"
                 f"传感器 {len(self.world.sensors)}", "",
                 "## 流体", ""]
        for k, v in result["fluids"].items():
            m = v.get("metrics", {})
            lines.append(f"### `{k}`（{v.get('type')} / {v.get('fluid','-')}）")
            if "volume_m3" in m:
                lines.append(f"- 体积 {m['volume_m3']:.4f} m³；最大水深 "
                             f"{m.get('max_depth_m', 0):.3f} m；最大速度 "
                             f"{m.get('max_speed_m_s', 0):.3f} m/s")
                lines.append(f"- 体积误差 {m.get('volume_error_rel', 0):.2e}；"
                             f"CFL dt {m.get('cfl_dt_s', 0):.4f}s")
            if "dp_total_pa" in v:
                lines.append(f"- 流速 {v.get('velocity_m_s', 0):.3f} m/s；压降 "
                             f"{v.get('dp_total_pa', 0):.1f} Pa；Re {v.get('reynolds', 0):.0f}")
            if "level_m" in m:
                lines.append(f"- 液位 {m['level_m']:.3f} m；出口流量 "
                             f"{m.get('outlet_flow_m3_s', 0):.3e} m³/s；溢出 {m.get('overflow')}")
            lines.append("")
        lines += ["## 传感器", ""]
        for k, v in result["sensors"].items():
            lines.append(f"- `{k}` {v.get('type')}: {v.get('value')} {v.get('unit','')}"
                         + (f"（{v['note']}）" if v.get("note") else ""))
        lines += ["", "## 机器人", ""]
        for k, v in result["robot"].items():
            lines.append(f"- {k}: {v}")
        lines += ["", "## 边界", "",
                  "- 浅水模型是降阶模型，不含自由表面破碎/气泡/多相；",
                  "- 水箱是 0D、管道是稳态；不是瞬态水锤/CFD；",
                  "- 未标定的参数（曼宁系数/局部损失/机器人阻力面积）只用于方案比较；",
                  "- 不代表实物安全/性能验收。", ""]
        return "\n".join(lines)


def run_world(world: wd.World, *, duration: float = 5.0, dt: float | None = None,
              dx: float = 0.2, frame_every: int = 10, out: str | None = None) -> dict:
    return WorldRun(world, duration, dt, dx, frame_every, out).run()


__all__ = ["G", "WorldRun", "run_world"]
