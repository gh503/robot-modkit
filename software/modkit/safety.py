"""运动安全包络：把"物理约束"变成下发前会拒绝的代码。

设计原则：
1. **fail-closed**：读不到反馈、状态未知、越界、跳变过大，一律拒绝，不"试一下"。
2. **单位在关节空间**：yaw/肩/肘是度，夹爪是 0–1 开度；换算到舵机 tick 只在这里做。
3. **默认值保守**：没有标定文件时用设计限位 + 更小的单步；标定后可用实测限位替换。
4. **不碰运动学逆解**：只回答"这个目标能不能发"，不替调用方规划轨迹。

这不是功能安全认证，也不能替代物理急停。它只是把常见误操作挡在上位机。
"""

from __future__ import annotations

import json
import math
import pathlib
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from . import kinematics as kin
from . import protocol as p

# 设计名义限位：与 cad/params.py、web/scene.js 同源；没有标定时用这套。
DEFAULT_JOINTS: dict[str, dict[str, Any]] = {
    "yaw":      {"servo_id": 1, "min": -120.0, "max": 120.0, "unit": "deg",
                 "zero_ticks": 2048, "dir": 1,  "ticks_per_unit": 1.0 / p.DEG_PER_TICK,
                 "max_step": 45.0},
    "shoulder": {"servo_id": 2, "min": -25.0,  "max": 100.0, "unit": "deg",
                 "zero_ticks": 2048, "dir": 1,  "ticks_per_unit": 1.0 / p.DEG_PER_TICK,
                 "max_step": 45.0},
    "elbow":    {"servo_id": 3, "min": -150.0, "max": 5.0,   "unit": "deg",
                 "zero_ticks": 2048, "dir": -1, "ticks_per_unit": 1.0 / p.DEG_PER_TICK,
                 "max_step": 60.0},
    "gripper":  {"servo_id": 4, "min": 0.0,    "max": 1.0,   "unit": "ratio",
                 "zero_ticks": p.deg_to_ticks(120.0), "dir": 1,
                 "ticks_per_unit": 60.0 / p.DEG_PER_TICK, "max_step": 0.5},
}


def _finite(v: Any, name: str) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{name} 必须是数字") from e
    if not math.isfinite(f):
        raise ValueError(f"{name} 必须是有限数")
    return f


@dataclass(frozen=True)
class JointLimit:
    name: str
    servo_id: int
    min_value: float
    max_value: float
    unit: str = "deg"
    zero_ticks: int = 2048
    direction: int = 1
    ticks_per_unit: float = 1.0 / p.DEG_PER_TICK
    max_step: float = 25.0

    def __post_init__(self) -> None:
        if self.direction not in (-1, 1):
            raise ValueError(f"{self.name}: direction 只能是 ±1")
        if self.min_value >= self.max_value:
            raise ValueError(f"{self.name}: min 必须小于 max")
        if not 0 <= self.zero_ticks <= p.TICKS_PER_REV - 1:
            raise ValueError(f"{self.name}: zero_ticks 越界")
        if self.ticks_per_unit <= 0:
            raise ValueError(f"{self.name}: ticks_per_unit 必须为正")
        if self.max_step <= 0:
            raise ValueError(f"{self.name}: max_step 必须为正")
        _finite(self.min_value, self.name)
        _finite(self.max_value, self.name)

    def contains(self, value: float) -> bool:
        return self.min_value - 1e-9 <= value <= self.max_value + 1e-9

    def to_servo_deg(self, value: float) -> float:
        """关节量 → 舵机绝对角度（度）。"""
        ticks = self.zero_ticks + self.direction * value * self.ticks_per_unit
        return p.ticks_to_deg(max(0.0, min(float(p.TICKS_PER_REV - 1), ticks)))

    def from_servo_deg(self, deg: float) -> float:
        """舵机绝对角度 → 关节量。"""
        ticks = deg / p.DEG_PER_TICK
        return self.direction * (ticks - self.zero_ticks) / self.ticks_per_unit

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "JointLimit":
        return cls(
            name=d["name"], servo_id=int(d["servo_id"]),
            min_value=float(d.get("min_value", d.get("min", 0.0))),
            max_value=float(d.get("max_value", d.get("max", 1.0))),
            unit=d.get("unit", "deg"), zero_ticks=int(d.get("zero_ticks", 2048)),
            direction=int(d.get("direction", d.get("dir", 1))),
            ticks_per_unit=float(d.get("ticks_per_unit", 1.0 / p.DEG_PER_TICK)),
            max_step=float(d.get("max_step", 25.0)),
        )


@dataclass
class Health:
    servo_id: int
    name: str = ""
    seen: bool = False
    position_deg: float | None = None
    voltage: float | None = None
    temp_c: int | None = None
    status: int = 0
    error: str = ""
    sampled_at: float | None = None

    @property
    def faults(self) -> list[str]:
        return p.status_bits(self.status)


@dataclass
class Decision:
    ok: bool
    code: str = ""
    message: str = ""
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class PreflightReport:
    ok: bool = False
    calibrated: bool = False
    health: list[Health] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    limits: dict[str, JointLimit] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "ok": self.ok, "calibrated": self.calibrated,
            "health": [asdict(h) | {"faults": h.faults} for h in self.health],
            "issues": self.issues, "warnings": self.warnings,
            "limits": {k: v.as_dict() for k, v in self.limits.items()},
        }


class SafetyPolicy:
    """一套可序列化的安全策略；默认值来自设计，标定后可覆盖。"""

    def __init__(self, joints: dict[str, JointLimit] | None = None, *,
                 robot: str = "modkit-m1", calibrated: bool = False,
                 temp_warn_c: float = 45.0, temp_max_c: float = 55.0,
                 voltage_warn_v: float = 10.8, voltage_min_v: float = 10.2,
                 torque_limit: int = 600, current_limit: int = 384,
                 acc: int = 30, speed: int = 300,
                 feedback_max_age_s: float = 1.5,
                 calibrated_joints: set[str] | None = None):
        self.joints = joints or {
            k: JointLimit(name=k, min_value=v["min"], max_value=v["max"],
                          servo_id=v["servo_id"], unit=v["unit"],
                          zero_ticks=v["zero_ticks"], direction=v["dir"],
                          ticks_per_unit=v["ticks_per_unit"], max_step=v["max_step"])
            for k, v in DEFAULT_JOINTS.items()
        }
        self.robot = robot
        self.calibrated = calibrated
        self.calibrated_joints = set(calibrated_joints or ())
        self.temp_warn_c = float(temp_warn_c)
        self.temp_max_c = float(temp_max_c)
        self.voltage_warn_v = float(voltage_warn_v)
        self.voltage_min_v = float(voltage_min_v)
        self.torque_limit = int(torque_limit)
        self.current_limit = int(current_limit)
        self.acc = int(acc)
        self.speed = int(speed)
        self.feedback_max_age_s = float(feedback_max_age_s)

    # ---------------------------------------------------------- 构造/序列化
    @classmethod
    def defaults(cls) -> "SafetyPolicy":
        return cls()

    @classmethod
    def from_calibration(cls, path: str | pathlib.Path,
                         base: "SafetyPolicy | None" = None) -> "SafetyPolicy":
        """用标定文件覆盖同名关节的零位/方向/限位；未标定的轴保留设计值。"""
        from . import calibrate as cal

        c = cal.Calibration.load(path)
        policy = base or cls()
        for name, j in c.joints.items():
            if name not in policy.joints:
                continue
            old = policy.joints[name]
            policy.joints[name] = JointLimit(
                name=name, servo_id=j.servo_id,
                min_value=j.min_deg, max_value=j.max_deg,
                unit="deg", zero_ticks=j.zero_ticks, direction=j.dir,
                ticks_per_unit=1.0 / p.DEG_PER_TICK,
                max_step=old.max_step,
            )
        policy.calibrated_joints |= set(c.joints) & set(policy.joints)
        policy.calibrated = bool(policy.calibrated_joints)
        policy.robot = c.robot
        return policy

    def copy(self) -> "SafetyPolicy":
        return SafetyPolicy(
            {k: JointLimit(**v.as_dict()) for k, v in self.joints.items()},
            robot=self.robot, calibrated=self.calibrated,
            temp_warn_c=self.temp_warn_c, temp_max_c=self.temp_max_c,
            voltage_warn_v=self.voltage_warn_v, voltage_min_v=self.voltage_min_v,
            torque_limit=self.torque_limit, current_limit=self.current_limit,
            acc=self.acc, speed=self.speed,
            feedback_max_age_s=self.feedback_max_age_s,
            calibrated_joints=self.calibrated_joints,
        )

    def to_dict(self) -> dict:
        return {
            "robot": self.robot, "calibrated": self.calibrated,
            "temp_warn_c": self.temp_warn_c, "temp_max_c": self.temp_max_c,
            "voltage_warn_v": self.voltage_warn_v, "voltage_min_v": self.voltage_min_v,
            "torque_limit": self.torque_limit, "current_limit": self.current_limit,
            "acc": self.acc, "speed": self.speed,
            "feedback_max_age_s": self.feedback_max_age_s,
            "calibrated_joints": sorted(self.calibrated_joints),
            "joints": {k: v.as_dict() for k, v in self.joints.items()},
        }

    def save(self, path: str | pathlib.Path) -> pathlib.Path:
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: str | pathlib.Path) -> "SafetyPolicy":
        d = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        joints = {k: JointLimit.from_dict({**v, "name": k}) for k, v in d.get("joints", {}).items()}
        return cls(
            joints or None, robot=d.get("robot", "modkit-m1"),
            calibrated=bool(d.get("calibrated", False)),
            temp_warn_c=d.get("temp_warn_c", 45.0), temp_max_c=d.get("temp_max_c", 55.0),
            voltage_warn_v=d.get("voltage_warn_v", 10.8),
            voltage_min_v=d.get("voltage_min_v", 10.2),
            torque_limit=d.get("torque_limit", 600), current_limit=d.get("current_limit", 384),
            acc=d.get("acc", 30), speed=d.get("speed", 300),
            feedback_max_age_s=d.get("feedback_max_age_s", 1.5),
            calibrated_joints=set(d.get("calibrated_joints", joints if d.get("calibrated") else [])),
        )

    # ---------------------------------------------------------- 单点检查
    def joint(self, name: str) -> JointLimit:
        if name not in self.joints:
            raise KeyError(f"未知关节 {name}；可用：{', '.join(self.joints)}")
        return self.joints[name]

    def check_target(self, name: str, value: float,
                     current: float | None = None) -> Decision:
        if name not in self.joints:
            return Decision(False, "unknown", f"未知关节 {name}")
        try:
            v = _finite(value, name)
        except ValueError as e:
            return Decision(False, "nan", str(e))
        j = self.joints[name]
        if not j.contains(v):
            unit = "°" if j.unit == "deg" else ""
            return Decision(False, "limit",
                            f"{name} 目标 {v:g}{unit} 超出 [{j.min_value:g}, {j.max_value:g}]")
        if current is not None:
            try:
                delta = abs(v - _finite(current, f"{name}.current"))
            except ValueError as e:
                return Decision(False, "current", str(e))
            if delta > j.max_step + 1e-9:
                return Decision(False, "step",
                                f"{name} 单步跳变 {delta:.1f} 超过 {j.max_step:g}；请分步下发")
        return Decision(True)

    def check_health(self, h: Health) -> Decision:
        if not h.seen:
            return Decision(False, "missing", f"{h.name or h.servo_id} 无反馈")
        if h.sampled_at is not None and time.monotonic() - h.sampled_at > self.feedback_max_age_s:
            return Decision(False, "stale",
                            f"{h.name or h.servo_id} 反馈超过 {self.feedback_max_age_s:g}s 未更新")
        warnings: list[str] = []
        if h.status:
            return Decision(False, "fault", f"ID{h.servo_id} 故障位：{', '.join(h.faults) or hex(h.status)}")
        if h.temp_c is not None:
            if h.temp_c >= self.temp_max_c:
                return Decision(False, "temp", f"ID{h.servo_id} 温度 {h.temp_c}℃ ≥ {self.temp_max_c:g}℃")
            if h.temp_c >= self.temp_warn_c:
                warnings.append(f"ID{h.servo_id} 温度 {h.temp_c}℃ 偏高")
        if h.voltage is not None:
            if h.voltage <= self.voltage_min_v:
                return Decision(False, "voltage",
                                f"ID{h.servo_id} 电压 {h.voltage:.1f}V ≤ {self.voltage_min_v:g}V")
            if h.voltage <= self.voltage_warn_v:
                warnings.append(f"ID{h.servo_id} 电压 {h.voltage:.1f}V 偏低")
        return Decision(True, warnings=warnings)

    # ---------------------------------------------------------- 预检
    def preflight(self, robot, expected_ids: list[int] | None = None,
                  scan: bool = False) -> PreflightReport:
        rep = PreflightReport(calibrated=self.calibrated, limits=dict(self.joints))
        ids = expected_ids or sorted({j.servo_id for j in self.joints.values()})
        if scan:
            try:
                found = set(robot.scan(lo=0, hi=20))
            except Exception as e:
                rep.issues.append(f"扫描失败：{e}")
                return rep
            missing = [i for i in ids if i not in found]
            if missing:
                rep.issues.append(f"扫描不到 ID：{missing}")
        for sid in ids:
            h = Health(servo_id=sid, name=next(
                (k for k, j in self.joints.items() if j.servo_id == sid), ""))
            try:
                fb = robot.feedback(sid)
                h.seen = True
                h.position_deg = round(fb.position_deg, 2)
                h.voltage = round(fb.voltage, 2)
                h.temp_c = int(fb.temp_c)
                h.status = int(robot.status(sid))
                h.sampled_at = time.monotonic()
            except Exception as e:
                h.error = str(e)
            rep.health.append(h)
            d = self.check_health(h)
            if not d.ok:
                rep.issues.append(d.message)
            rep.warnings.extend(d.warnings)

        # 标定覆盖：只对已标定轴宣称“实测限位”，其余轴明确标注仍用设计值。
        if self.calibrated:
            missing = [k for k in ("yaw", "shoulder", "elbow")
                       if k not in self.calibrated_joints]
            if missing:
                rep.warnings.append(f"标定未覆盖 {missing}；这些轴仍用设计限位")

        rep.ok = not rep.issues
        return rep

    # ---------------------------------------------------------- 运动前联锁
    def guard_motion(self, robot, targets: dict[str, float],
                     expected_ids: list[int] | None = None) -> Decision:
        """对所有目标做一次 fail-closed 校验；返回第一个/全部问题。"""
        if not targets:
            return Decision(False, "empty", "没有目标")
        rep = self.preflight(robot, expected_ids=expected_ids)
        if not rep.ok:
            return Decision(False, "preflight", "；".join(rep.issues), rep.warnings)
        by_id = {h.servo_id: h for h in rep.health}
        for name, value in targets.items():
            if name not in self.joints:
                return Decision(False, "unknown", f"未知关节 {name}", rep.warnings)
            j = self.joints[name]
            h = by_id.get(j.servo_id)
            if h is None or not h.seen or h.position_deg is None:
                return Decision(False, "missing", f"{name} 无反馈", rep.warnings)
            current = j.from_servo_deg(h.position_deg)
            d = self.check_target(name, value, current)
            if not d.ok:
                return Decision(False, d.code, d.message, rep.warnings + d.warnings)
        return Decision(True, warnings=rep.warnings)

    def apply_limits(self, robot, ids: list[int] | None = None) -> None:
        """写转矩/电流/加速度限制；上电后、使能前调用。"""
        ids = ids or sorted({j.servo_id for j in self.joints.values()})
        for sid in ids:
            robot.set_register(sid, p.REG_TORQUE_LIMIT, self.torque_limit.to_bytes(2, "little"))
            robot.set_register(sid, p.REG_CURRENT_LIMIT, self.current_limit.to_bytes(2, "little"))
            robot.set_register(sid, p.REG_ACC, bytes([self.acc & 0xFF]))

    def targets_to_servo(self, targets: dict[str, float]) -> dict[int, float]:
        out: dict[int, float] = {}
        for name, value in targets.items():
            j = self.joint(name)
            out[j.servo_id] = j.to_servo_deg(value)
        return out
