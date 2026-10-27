"""降阶流体实验：2D 浅水 + 0D 水箱 + 1D 管道。

定位：数字孪生里的“流体实验台”。用于比较方案、调试控制、生成可视化帧；
不是认证 CFD，不解析自由表面破碎/气泡/多相。所有结果必须带模型边界。

浅水方程（守恒形式，显式一阶）：
    ∂h/∂t + ∇·(h u) = q
    ∂u/∂t + (u·∇)u = -g ∇h - C_f |u|u/h + ν ∇²u
    C_f = n² g / h^(1/3)  (Manning 摩阻)
"""

from __future__ import annotations

import json
import math
import pathlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from . import fluid as fl

G = fl.G


class FluidSimError(ValueError):
    pass


@dataclass
class Source:
    """点源/点汇；rate_m3_s >0 注入，<0 抽水。"""
    x: float
    y: float
    rate_m3_s: float
    radius_m: float = 0.05
    kind: str = "source"

    def mask(self, xs: np.ndarray, ys: np.ndarray, dx: float) -> np.ndarray:
        r = max(self.radius_m, dx)
        return ((xs - self.x) ** 2 + (ys - self.y) ** 2) <= r * r


@dataclass
class ShallowWater:
    fluid: fl.Fluid
    nx: int = 64
    ny: int = 48
    dx: float = 0.05
    depth: float | np.ndarray = 0.2
    terrain: np.ndarray | None = None
    mask: np.ndarray | None = None
    u: np.ndarray | None = None
    v: np.ndarray | None = None
    manning: float = 0.025
    viscosity: float | None = None
    boundary: str = "closed"        # closed | open | periodic
    sources: list[Source] = field(default_factory=list)
    min_depth: float = 1e-5
    cfl: float = 0.35
    t: float = 0.0
    _initial_volume: float = field(default=0.0, repr=False)
    _injected: float = field(default=0.0, repr=False)

    def __post_init__(self) -> None:
        if self.nx < 4 or self.ny < 4:
            raise FluidSimError("网格至少 4x4")
        if self.dx <= 0:
            raise FluidSimError("dx 必须 >0")
        self.h = (np.full((self.ny, self.nx), float(self.depth))
                  if np.isscalar(self.depth) else np.array(self.depth, dtype=float))
        if self.h.shape != (self.ny, self.nx):
            raise FluidSimError(f"depth shape {self.h.shape} != {(self.ny, self.nx)}")
        self.b = (np.zeros_like(self.h) if self.terrain is None
                  else np.array(self.terrain, dtype=float))
        if self.b.shape != self.h.shape:
            raise FluidSimError("terrain shape 必须与 depth 一致")
        if self.mask is None:
            self.mask = np.ones_like(self.h, dtype=bool)
        else:
            self.mask = np.array(self.mask, dtype=bool)
            if self.mask.shape != self.h.shape:
                raise FluidSimError("mask shape 必须与 depth 一致")
        self.h = np.where(self.mask, self.h, 0.0)
        self.u = np.zeros_like(self.h) if self.u is None else np.array(self.u, dtype=float)
        self.v = np.zeros_like(self.h) if self.v is None else np.array(self.v, dtype=float)
        self.h = np.maximum(self.h, 0.0)
        self.nu = (self.fluid.kinematic_viscosity if self.viscosity is None
                   else max(0.0, self.viscosity))
        self._initial_volume = self.volume
        if self.fluid.is_gas:
            # 浅水只对液体/浆体有意义；气体走 0D/管道模型
            raise FluidSimError("浅水模型不支持气体；用 pipe/tank 或 world 0D 模型")

    # ------------------------------------------------------------ 基本量
    @property
    def xs(self) -> np.ndarray:
        return (np.arange(self.nx) + 0.5) * self.dx

    @property
    def ys(self) -> np.ndarray:
        return (np.arange(self.ny) + 0.5) * self.dx

    @property
    def volume(self) -> float:
        return float(np.sum(self.h) * self.dx * self.dx)

    @property
    def max_depth(self) -> float:
        return float(np.max(self.h)) if self.h.size else 0.0

    @property
    def max_speed(self) -> float:
        return float(max(np.max(np.abs(self.u)), np.max(np.abs(self.v))))

    def cfl_dt(self) -> float:
        c = math.sqrt(G * max(self.max_depth, 1e-6))
        return self.cfl * self.dx / max(c + self.max_speed, 1e-9)

    # ------------------------------------------------------------ 步进
    def _apply_sources(self, dt: float) -> None:
        if not self.sources:
            return
        xs, ys = np.meshgrid(self.xs, self.ys)
        cell_area = self.dx * self.dx
        for s in self.sources:
            m = s.mask(xs, ys, self.dx)
            n = int(np.count_nonzero(m))
            if not n:
                continue
            use = m & self.mask
            n2 = int(np.count_nonzero(use))
            if n2:
                self.h[use] = np.maximum(0.0, self.h[use] + s.rate_m3_s * dt / (n2 * cell_area))
            self._injected += s.rate_m3_s * dt

    def step(self, dt: float | None = None) -> float:
        """推进一个显式步；返回实际 dt。"""
        if dt is None:
            dt = self.cfl_dt()
        if dt <= 0:
            raise FluidSimError("dt 必须 >0")
        dt = min(dt, self.cfl_dt())
        h = self.h
        h_safe = np.maximum(h, self.min_depth)
        # 面速度/水深：upwind
        u = self.u
        v = self.v
        # x 方向面通量：形状 (ny, nx+1)
        ux = np.zeros((self.ny, self.nx + 1))
        hx = np.zeros_like(ux)
        ux[:, 1:-1] = 0.5 * (u[:, :-1] + u[:, 1:])
        hx[:, 1:-1] = np.where(ux[:, 1:-1] >= 0, h_safe[:, :-1], h_safe[:, 1:])
        if self.boundary == "closed":
            ux[:, 0] = 0.0; ux[:, -1] = 0.0
        elif self.boundary == "periodic":
            ux[:, 0] = 0.5 * (u[:, -1] + u[:, 0]); ux[:, -1] = ux[:, 0]
            hx[:, 0] = np.where(ux[:, 0] >= 0, h_safe[:, -1], h_safe[:, 0])
            hx[:, -1] = hx[:, 0]
        else:  # open
            hx[:, 0] = h_safe[:, 0]; hx[:, -1] = h_safe[:, -1]
        # 多边形/掩膜边界：跨越干格的面通量置零
        mx = self.mask[:, :-1] & self.mask[:, 1:]
        ux[:, 1:-1] = np.where(mx, ux[:, 1:-1], 0.0)
        hx[:, 1:-1] = np.where(mx, hx[:, 1:-1], 0.0)
        fx = ux * hx
        # y 方向面通量：形状 (ny+1, nx)
        vy = np.zeros((self.ny + 1, self.nx))
        hy = np.zeros_like(vy)
        vy[1:-1, :] = 0.5 * (v[:-1, :] + v[1:, :])
        hy[1:-1, :] = np.where(vy[1:-1, :] >= 0, h_safe[:-1, :], h_safe[1:, :])
        if self.boundary == "closed":
            vy[0, :] = 0.0; vy[-1, :] = 0.0
        elif self.boundary == "periodic":
            vy[0, :] = 0.5 * (v[-1, :] + v[0, :]); vy[-1, :] = vy[0, :]
            hy[0, :] = np.where(vy[0, :] >= 0, h_safe[-1, :], h_safe[0, :])
            hy[-1, :] = hy[0, :]
        else:
            hy[0, :] = h_safe[0, :]; hy[-1, :] = h_safe[-1, :]
        my = self.mask[:-1, :] & self.mask[1:, :]
        vy[1:-1, :] = np.where(my, vy[1:-1, :], 0.0)
        hy[1:-1, :] = np.where(my, hy[1:-1, :], 0.0)
        fy = vy * hy
        dh = -((fx[:, 1:] - fx[:, :-1]) + (fy[1:, :] - fy[:-1, :])) / self.dx
        self.h = np.where(self.mask, np.maximum(0.0, h + dt * dh), 0.0)

        # 压力（中心）+ 对流（迎风）+ Manning 摩阻 + 粘性
        hh = np.maximum(self.h, self.min_depth)
        dhdx = np.zeros_like(h)
        dhdy = np.zeros_like(h)
        # 只对“湿—湿”中心差分；干格/掩膜外不制造压力梯度。
        # 否则边界湿格会把 min_depth 的干格当成深水，产生假加速度。
        mx2 = np.ones_like(self.mask, dtype=bool)
        my2 = np.ones_like(self.mask, dtype=bool)
        mx2[:, 1:-1] = self.mask[:, :-2] & self.mask[:, 2:]
        my2[1:-1, :] = self.mask[:-2, :] & self.mask[2:, :]
        dhdx[:, 1:-1] = np.where(mx2[:, 1:-1],
                                 (hh[:, 2:] - hh[:, :-2]) / (2 * self.dx), 0.0)
        dhdy[1:-1, :] = np.where(my2[1:-1, :],
                                 (hh[2:, :] - hh[:-2, :]) / (2 * self.dx), 0.0)
        dhdx = np.where(self.mask, dhdx, 0.0)
        dhdy = np.where(self.mask, dhdy, 0.0)
        if self.boundary == "periodic":
            dhdx[:, 0] = (hh[:, 1] - hh[:, -1]) / (2 * self.dx)
            dhdx[:, -1] = (hh[:, 0] - hh[:, -2]) / (2 * self.dx)
            dhdy[0, :] = (hh[1, :] - hh[-1, :]) / (2 * self.dx)
            dhdy[-1, :] = (hh[0, :] - hh[-2, :]) / (2 * self.dx)
        cf = self.manning**2 * G / np.power(hh, 1.0 / 3.0)
        speed = np.sqrt(u * u + v * v)
        # 迎风对流
        dudx = np.zeros_like(u); dvdy = np.zeros_like(v)
        dudx[:, 1:-1] = np.where(mx2[:, 1:-1],
                                 np.where(u[:, 1:-1] >= 0,
                                          (u[:, 1:-1] - u[:, :-2]) / self.dx,
                                          (u[:, 2:] - u[:, 1:-1]) / self.dx), 0.0)
        dvdy[1:-1, :] = np.where(my2[1:-1, :],
                                 np.where(v[1:-1, :] >= 0,
                                          (v[1:-1, :] - v[:-2, :]) / self.dx,
                                          (v[2:, :] - v[1:-1, :]) / self.dx), 0.0)
        lap_u = np.zeros_like(u); lap_v = np.zeros_like(v)
        lap_u[:, 1:-1] = np.where(mx2[:, 1:-1],
                                  (u[:, 2:] - 2 * u[:, 1:-1] + u[:, :-2]) / self.dx**2, 0.0)
        lap_v[1:-1, :] = np.where(my2[1:-1, :],
                                  (v[2:, :] - 2 * v[1:-1, :] + v[:-2, :]) / self.dx**2, 0.0)
        wet = self.h > self.min_depth
        u_new = u + dt * (-u * dudx - G * dhdx - cf * speed * u + self.nu * lap_u)
        v_new = v + dt * (-v * dvdy - G * dhdy - cf * speed * v + self.nu * lap_v)
        u_new = np.where(wet, u_new, 0.0)
        v_new = np.where(wet, v_new, 0.0)
        # 干湿边界：不让水从干格被吸走
        self.u = np.where(self.mask, np.clip(u_new, -20.0, 20.0), 0.0)
        self.v = np.where(self.mask, np.clip(v_new, -20.0, 20.0), 0.0)
        self._apply_sources(dt)
        self.t += dt
        self._enforce_boundary()
        return dt

    def _enforce_boundary(self) -> None:
        if self.boundary == "closed":
            self.u[:, 0] = 0.0; self.u[:, -1] = 0.0
            self.v[0, :] = 0.0; self.v[-1, :] = 0.0
            self.u = np.where(self.mask, self.u, 0.0)
            self.v = np.where(self.mask, self.v, 0.0)
        elif self.boundary == "open":
            # 零梯度出流，避免反射
            self.u[:, 0] = self.u[:, 1]; self.u[:, -1] = self.u[:, -2]
            self.v[0, :] = self.v[1, :]; self.v[-1, :] = self.v[-2, :]

    def advance(self, seconds: float, dt: float | None = None) -> int:
        if seconds < 0:
            raise FluidSimError("seconds 不能为负")
        n = 0
        while self.t + 1e-15 < seconds:
            d = self.step(min(dt, self.cfl_dt()) if dt else None)
            n += 1
            if n > 2_000_000:
                raise FluidSimError("步数超限；检查 dt/网格")
        return n

    # ------------------------------------------------------------ 指标/帧
    def metrics(self) -> dict:
        vol = self.volume
        expected = self._initial_volume + self._injected
        return {
            "t_s": round(self.t, 6),
            "volume_m3": vol,
            "initial_volume_m3": self._initial_volume,
            "injected_m3": self._injected,
            "volume_error_m3": vol - expected,
            "volume_error_rel": (abs(vol - expected) / expected if expected else 0.0),
            "max_depth_m": self.max_depth,
            "max_speed_m_s": self.max_speed,
            "cfl_dt_s": self.cfl_dt(),
            "cells": int(self.h.size),
            "wet_cells": int(np.count_nonzero(self.h > self.min_depth)),
        }

    def frame(self, *, downsample: int = 1, precision: int = 4) -> dict:
        h = self.h[::downsample, ::downsample]
        return {
            "t_s": round(self.t, 6),
            "nx": int(h.shape[1]), "ny": int(h.shape[0]),
            "dx": self.dx * downsample,
            "height_m": np.round(h, precision).tolist(),
        }

    def to_json(self, path: str | pathlib.Path, *, downsample: int = 1) -> pathlib.Path:
        p = pathlib.Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"fluid": self.fluid.key,
                                 "metrics": self.metrics(),
                                 "frame": self.frame(downsample=downsample)},
                                ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return p


@dataclass
class Tank:
    """0D 水箱：面积、初始液位、出口、补液；用于泵/过滤/排空。"""
    fluid: fl.Fluid
    area_m2: float
    height_m: float = 1.0
    outlet_area_m2: float = 0.001
    cd: float = 0.62
    inflow_m3_s: float = 0.0
    level_m: float | None = None
    overflow: bool = False
    t: float = 0.0
    _outflow_total: float = 0.0

    def __post_init__(self) -> None:
        if self.area_m2 <= 0 or self.height_m <= 0 or self.outlet_area_m2 <= 0:
            raise FluidSimError("面积/高度/出口必须 >0")
        if self.level_m is None:
            self.level_m = self.height_m
        if not 0 <= self.level_m <= self.height_m:
            raise FluidSimError("液位必须在 0..height")

    def step(self, dt: float) -> float:
        if dt <= 0:
            raise FluidSimError("dt 必须 >0")
        h = max(0.0, self.level_m)
        q_out = fl.orifice_flow(self.outlet_area_m2, h, self.fluid, self.cd)
        dv = (self.inflow_m3_s - q_out) * dt
        level = self.level_m + dv / self.area_m2
        if level > self.height_m:
            self.overflow = True
            level = self.height_m
        if level < 0:
            self._outflow_total += max(0.0, -level) * self.area_m2
            level = 0.0
        self._outflow_total += max(0.0, q_out) * dt
        self.level_m = level
        self.t += dt
        return self.level_m

    def advance(self, seconds: float, dt: float = 0.01) -> None:
        """从当前时刻推进 seconds（相对时长）。"""
        if seconds < 0:
            raise FluidSimError("seconds 不能为负")
        if dt <= 0:
            raise FluidSimError("dt 必须 >0")
        end = self.t + seconds
        while self.t + 1e-15 < end:
            self.step(min(dt, end - self.t))

    def metrics(self) -> dict:
        return {
            "t_s": self.t, "level_m": self.level_m, "height_m": self.height_m,
            "volume_m3": self.level_m * self.area_m2,
            "outlet_flow_m3_s": fl.orifice_flow(self.outlet_area_m2,
                                                max(0.0, self.level_m),
                                                self.fluid, self.cd),
            "outflow_total_m3": self._outflow_total,
            "overflow": self.overflow,
        }


def dam_break(nx: int = 64, ny: int = 32, dx: float = 0.05,
              depth: float = 0.2, fluid: str = "water") -> ShallowWater:
    """左侧一半有水、右侧干的确定性算例。"""
    h = np.zeros((ny, nx))
    h[:, : nx // 2] = depth
    return ShallowWater(fl.get(fluid), nx=nx, ny=ny, dx=dx, depth=h,
                        manning=0.02, boundary="closed")


def run_experiment(cfg: dict) -> dict:
    """通用实验配置 → 帧 + 指标；供 CLI/世界仿真调用。

    cfg:
      fluid, nx, ny, dx, depth, terrain|barrier, sources, duration, dt,
      downsample, frames
    """
    fluid = fl.get(cfg.get("fluid", "water"))
    nx, ny = int(cfg.get("nx", 64)), int(cfg.get("ny", 48))
    dx = float(cfg.get("dx", 0.05))
    depth = cfg.get("depth", 0.2)
    if isinstance(depth, list):
        depth = np.array(depth, dtype=float)
    sim = ShallowWater(fluid, nx=nx, ny=ny, dx=dx, depth=depth,
                       manning=float(cfg.get("manning", 0.025)),
                       boundary=cfg.get("boundary", "closed"))
    for s in cfg.get("sources", []):
        sim.sources.append(Source(float(s["x"]), float(s["y"]),
                                  float(s["rate_m3_s"]), float(s.get("radius_m", 0.05)),
                                  s.get("kind", "source")))
    duration = float(cfg.get("duration", 2.0))
    dt = cfg.get("dt")
    frames = []
    every = max(1, int(cfg.get("frame_every", 10)))
    i = 0
    while sim.t < duration:
        sim.step(min(float(dt), sim.cfl_dt()) if dt else None)
        i += 1
        if i % every == 0 or sim.t >= duration:
            frames.append(sim.frame(downsample=int(cfg.get("downsample", 1))))
    return {"fluid": fluid.key, "config": {k: v for k, v in cfg.items()
                                           if k not in ("depth", "terrain")},
            "metrics": sim.metrics(), "frames": frames}


__all__ = ["G", "FluidSimError", "Source", "ShallowWater", "Tank",
           "dam_break", "run_experiment"]
