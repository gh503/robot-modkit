"""硬件在环仿真：不是"位置立刻跟随"的假舵机，而是带物理约束的数字孪生。

和 bus.SimLink 的区别：
  · 舵机有转速/扭矩上限、死区、回差、温升；
  · 关节受重力力矩，扛不住会下垂（不是命令 35° 就真到 35°）；
  · 电池有内阻，多个舵机同时动会掉压，低压会保护；
  · 轮子有加速限制与打滑，编码器按 4096 量化；
  · 时间可以显式步进（确定性，CI 可跑），不依赖真实 sleep。

协议层完全一致：Robot/CLI 不需要改，把 link 换成 HardwareSim 即可。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from . import kinematics as kin
from . import protocol as p


@dataclass
class ServoSpec:
    rated_torque: float = 2.94      # N·m
    no_load_speed: float = 4.8      # rad/s ≈ 275°/s
    kp: float = 20.0                # N·m/rad
    kd: float = 1.2                 # N·m·s/rad
    inertia: float = 0.02           # kg·m²（折算到关节）
    friction: float = 0.06          # N·m
    deadband_deg: float = 0.15
    backlash_deg: float = 0.20
    kt: float = 0.95                # N·m/A
    resistance: float = 3.0         # Ω
    thermal_c: float = 18.0         # J/K
    cooling: float = 0.06           # 1/s
    ambient_c: float = 25.0
    max_temp_c: float = 70.0


@dataclass
class BatterySpec:
    ocv: float = 12.2               # V（3S 中段）
    resistance: float = 0.12        # Ω
    idle_a: float = 0.12            # 控制板+待机
    low_v: float = 10.8
    cut_v: float = 9.9


@dataclass
class Servo:
    sid: int
    spec: ServoSpec = field(default_factory=ServoSpec)
    pos_deg: float = 180.0
    vel_deg_s: float = 0.0
    target_deg: float = 180.0
    target_speed_lsb: float = 0.0
    mode: int = 0                    # 0 位置，1 恒速
    torque_on: bool = True
    temp_c: float = 25.0
    current_a: float = 0.0
    last_dir: int = 1
    status: int = 0

    @property
    def ticks(self) -> int:
        return int(round(self.pos_deg / 360.0 * 4096)) & 0xFFF

    def apply(self, addr: int, data: bytes) -> None:
        if addr == p.REG_MODE and data:
            self.mode = data[0]
        elif addr == p.REG_TORQUE_ENABLE and data:
            self.torque_on = data[0] == 1
        elif addr == p.REG_GOAL_POS and len(data) >= 2:
            t = p.u16(data[0], data[1])
            self.target_deg = t / 4096.0 * 360.0
        elif addr == p.REG_GOAL_SPEED and len(data) >= 2:
            v = p.u16(data[0], data[1])
            mag = v & 0x7FFF
            self.target_speed_lsb = -mag if v & 0x8000 else mag

    def step(self, dt: float, gravity_torque: float = 0.0) -> None:
        spec = self.spec
        if not self.torque_on:
            # 卸力：臂在重力下自由下落，轮子只做阻尼
            if abs(gravity_torque) > spec.friction:
                net = gravity_torque - math.copysign(spec.friction, gravity_torque)
                self.vel_deg_s += math.degrees(net / spec.inertia) * dt
            else:
                self.vel_deg_s *= max(0.0, 1.0 - 8.0 * dt)
            self.pos_deg += self.vel_deg_s * dt
            self.current_a = 0.0
            return

        if self.mode == 1:
            target_rad = math.radians(self.target_speed_lsb)   # 1 LSB = 1°/s（标定前）
            tau = (target_rad - math.radians(self.vel_deg_s)) * 0.4
            tau = max(-spec.rated_torque, min(spec.rated_torque, tau))
        else:
            err = math.radians(self.target_deg - self.pos_deg)
            if abs(math.degrees(err)) < spec.deadband_deg and abs(self.vel_deg_s) < 2.0:
                # 死区内：只抵抗重力，不动
                self.vel_deg_s = 0.0
                self.current_a = abs(gravity_torque) / spec.kt
                self._thermal(dt)
                return
            tau = spec.kp * err - spec.kd * math.radians(self.vel_deg_s)

        if abs(tau) > 0:
            self.last_dir = 1 if tau > 0 else -1
        tau = max(-spec.rated_torque, min(spec.rated_torque, tau))
        net = tau + gravity_torque
        # 库仑摩擦
        if abs(net) > spec.friction:
            net -= math.copysign(spec.friction, net)
        else:
            net = 0.0
        accel = net / spec.inertia
        self.vel_deg_s += math.degrees(accel) * dt
        vmax = math.degrees(spec.no_load_speed)
        self.vel_deg_s = max(-vmax, min(vmax, self.vel_deg_s))
        self.pos_deg += self.vel_deg_s * dt
        self.current_a = min(4.5, abs(tau) / spec.kt + abs(self.vel_deg_s) / vmax * 0.3)
        self._thermal(dt)
        self.status = 0
        if abs(tau) >= spec.rated_torque * 0.98:
            self.status |= 0x20          # 负载异常
        if self.temp_c >= spec.max_temp_c:
            self.status |= 0x04          # 温度异常
            self.torque_on = False

    def _thermal(self, dt: float) -> None:
        s = self.spec
        heat = self.current_a ** 2 * s.resistance
        self.temp_c += (heat - (self.temp_c - s.ambient_c) * s.cooling) / s.thermal_c * dt

    def output_deg(self) -> float:
        """回差：换向后输出滞后半个间隙。"""
        return self.pos_deg - self.last_dir * self.spec.backlash_deg / 2.0


@dataclass
class Chassis:
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0
    wheel_r: float = 32.5
    track: float = 150.0
    ticks_per_rev: int = 4096
    wheel_deg: dict[int, float] = field(default_factory=lambda: {5: 0.0, 6: 0.0})
    slip: float = 0.0               # 0=不打滑，1=完全打滑（轮转车不走）

    def step(self, dt: float, left_deg_s: float, right_deg_s: float) -> None:
        vl = math.radians(left_deg_s) * self.wheel_r
        vr = math.radians(right_deg_s) * self.wheel_r
        v = (vl + vr) / 2.0 * (1.0 - self.slip)
        w = math.degrees((vr - vl) / self.track) * (1.0 - self.slip)
        mid = math.radians(self.yaw + w * dt / 2.0)
        self.x += v * math.cos(mid) * dt
        self.y += v * math.sin(mid) * dt
        self.yaw = (self.yaw + w * dt + 180.0) % 360.0 - 180.0
        for sid, ws in ((5, left_deg_s), (6, right_deg_s)):
            self.wheel_deg[sid] += ws * dt


class HardwareSim:
    """实现和 SerialLink/SimLink 一样的 transact() 接口。"""

    def __init__(self, ids: list[int] | None = None,
                 spec: ServoSpec | None = None,
                 battery: BatterySpec | None = None,
                 seed: int = 0, bus_latency: float = 0.0,
                 drop_rate: float = 0.0, payload_kg: float = 0.0):
        ids = ids or [1, 2, 3, 4, 5, 6]
        self.servos = {sid: Servo(sid, spec or ServoSpec()) for sid in ids}
        for sid in (5, 6):
            s = self.servos[sid]
            s.mode = 1
            s.pos_deg = s.target_deg = 0.0
            s.vel_deg_s = 0.0
        self.battery = battery or BatterySpec()
        self.chassis = Chassis()
        self.time = 0.0
        self.rng = random.Random(seed)
        self.bus_latency = bus_latency
        self.drop_rate = drop_rate
        self.voltage = self.battery.ocv
        self.cutoff = False
        self.payload_kg = payload_kg
        self.command_log: list[tuple[float, bytes]] = []

    # ------------------------------------------------------------ 物理
    def step(self, dt: float, substep: float = 0.001) -> None:
        n = max(1, int(math.ceil(dt / substep)))
        h = dt / n
        for _ in range(n):
            self._step_once(h)
            self.time += h

    def _step_once(self, h: float) -> None:
        total_i = self.battery.idle_a
        for s in self.servos.values():
            g = self._gravity(s.sid)
            s.step(h, g)
            total_i += s.current_a
        self.voltage = max(0.0, self.battery.ocv - total_i * self.battery.resistance)
        if self.voltage <= self.battery.cut_v and not self.cutoff:
            self.cutoff = True
            for s in self.servos.values():
                s.torque_on = False
                s.status |= 0x01          # 电压异常
        l = self.servos[5]
        r = self.servos[6]
        self.chassis.step(h, l.vel_deg_s, r.vel_deg_s)

    def _gravity(self, sid: int) -> float:
        """关节重力力矩（N·m），把连杆质量按集中质量估。"""
        if sid not in (2, 3):
            return 0.0
        sh = math.radians(self.servos[2].output_deg() - 180.0)
        el = math.radians(self.servos[3].output_deg() - 180.0)
        m2, m3 = 0.09, 0.07 + self.payload_kg
        L1, L2, g = 0.12, 0.11, 9.81
        if sid == 2:
            return -g * ((m2 * L1 / 2 + m3 * L1) * math.cos(sh)
                         + m3 * L2 / 2 * math.cos(sh + el))
        return -g * m3 * L2 / 2 * math.cos(sh + el)

    # ------------------------------------------------------------ 协议
    def transact(self, frame: bytes, expect_id: int, timeout: float = 0.05) -> p.Frame:
        if frame[:2] != b"\xff\xff" or len(frame) < 6:
            raise RuntimeError("仿真链路收到畸形帧")
        sid, plen, instr = frame[2], frame[3], frame[4]
        params = frame[5:3 + plen]
        self.command_log.append((self.time, frame))
        if self.drop_rate and self.rng.random() < self.drop_rate:
            raise RuntimeError(f"丢帧：{sid} 号舵机无应答")
        if self.bus_latency:
            self.step(self.bus_latency)

        if instr == p.PING:
            if sid in self.servos:
                return p.Frame(id=sid, error=0)
            raise RuntimeError(f"超时：{sid} 号舵机无应答")

        if instr == p.WRITE:
            s = self.servos.get(sid)
            if s is None:
                raise RuntimeError(f"超时：{sid} 号舵机无应答")
            s.apply(params[0], params[1:])
            return p.Frame(id=sid, error=0)

        if instr == p.SYNC_WRITE:
            addr, pl = params[0], params[1]
            body = params[2:]
            for i in range(0, len(body), pl + 1):
                s = self.servos.get(body[i])
                if s:
                    s.apply(addr, body[i + 1:i + 1 + pl])
            return p.Frame(id=p.BROADCAST_ID, error=0)

        if instr == p.READ:
            s = self.servos.get(sid)
            if s is None:
                raise RuntimeError(f"超时：{sid} 号舵机无应答")
            addr, n = params[0], params[1]
            data = self._read(s, addr, n)
            return p.Frame(id=sid, error=0, params=data)
        raise RuntimeError(f"未实现的指令 0x{instr:02X}")

    def _read(self, s: Servo, addr: int, n: int) -> bytes:
        if addr == p.REG_PRESENT_POS:
            t = s.ticks
            spd = int(max(-2048, min(2047, s.vel_deg_s / 360.0 * 4096)))
            load = int(max(-1000, min(1000, s.current_a / 4.5 * 1000)))
            temp = int(max(0, min(100, s.temp_c)))
            vals = [t & 0xFF, t >> 8, spd & 0xFF, (spd >> 8) & 0xFF,
                    load & 0xFF, (load >> 8) & 0xFF,
                    int(self.voltage * 10), temp]
        elif addr == p.REG_STATUS:
            vals = [s.status & 0xFF]
        else:
            vals = [0] * n
        return bytes(vals[:n])

    # ------------------------------------------------------------ 便捷访问
    def pose(self) -> tuple[float, float, float]:
        return self.chassis.x, self.chassis.y, self.chassis.yaw

    def joint_deg(self, sid: int) -> float:
        return self.servos[sid].output_deg()
