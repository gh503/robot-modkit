"""把 M1 机械臂导出成 quench3d 场景（动力学仿真用，可选）。

为什么另做一份：
  · 现在的网页/three.js 是**运动学**：角度对，但没有质量、没有接触、没有力矩；
  · quench3d 有刚体 + 铰链位置伺服 + 接触摩擦 + 断裂力矩，可以回答
    "这个姿态电机扛得住吗""夹爪碰到方块会怎样"；
  · 但 quench3d 用米、Y 轴朝上、场景是静态 JSON，所以需要这层转换。
  · 试验性：0.1.0 里内置位置伺服在 3 自由度串链上还不稳（见 docs/12 §2.6），
    当前用途是"把模型摆进引擎 + 接触/力矩实验"，不是可直接上线的整机仿真。

坐标：modkit 是 mm、Z 朝上 → quench3d 是 m、Y 朝上。
      (x, y, z)_mm → (x/1000, z/1000, -y/1000)_m

产物：sim/out/modkit_arm.scene.json
用法：
    cd sim && ../.venv/bin/python quench_scene.py
    ../.venv/bin/python quench_scene.py --shoulder 20 --elbow -85 --run
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.append(str(_ROOT / "cad"))
import params as P  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent / "out" / "modkit_arm.scene.json"

# 结构尺寸（mm）—— 与 export_web.py 同源
BASE_H = 90.0
L1 = 120.0
L2 = 110.0
COLUMN = 40.0          # 立柱截面
HUB = 50.0             # 偏航块
LINK_W = 20.0
LINK_T = 30.0

# 质量（kg）—— 按零件清单估算，整机 360g 里臂部约 0.3kg
M_HUB, M_L1, M_L2, M_CUBE = 0.08, 0.09, 0.07, 0.05

RATED_TORQUE = 30 * 0.0980665   # 30 kg·cm → N·m（≈2.94）


def build(yaw: float, shoulder: float, elbow: float,
          cube: tuple[float, float] | None) -> dict:
    yaw_r, sh_r, el_r = (math.radians(v) for v in (yaw, shoulder, elbow))
    scene = {
        "format": "quench3d.scene", "version": 2,
        "name": f"modkit M1 · yaw {yaw}° shoulder {shoulder}° elbow {elbow}°",
        "gravity": [0, -9.81, 0],
        "ground": {"size": 4, "material": "floor"},
        "materials": {
            "floor": {"color": [0.55, 0.58, 0.62], "roughness": 0.9},
            "steel": {"color": [0.55, 0.58, 0.62], "metallic": 0.8, "roughness": 0.3},
            "orange": {"color": [0.95, 0.52, 0.09], "roughness": 0.5},
            "joint": {"color": [0.18, 0.22, 0.25], "roughness": 0.6},
        },
        "objects": [
            {"name": "chassis", "shape": {"type": "box", "size": [0.24, 0.005, 0.20]},
             "position": [0, 0.0025, 0], "material": "steel", "body": "static"},
            {"name": "column", "shape": {"type": "box", "size": [0.04, 0.09, 0.04]},
             "position": [0, 0.05, 0], "material": "joint", "body": "static"},
            # 偏航块：绕 Y 转，肩关节装在它的 +X 侧
            {"name": "yaw", "shape": {"type": "box", "size": [HUB / 1000, 0.03, HUB / 1000]},
             "position": [HUB / 2000, 0.105, 0], "material": "orange",
             "body": "dynamic", "mass": M_HUB},
            {"name": "link1", "shape": {"type": "box", "size": [L1 / 1000, LINK_W / 1000, LINK_T / 1000]},
             "position": [(HUB + L1) / 2000, 0.12, 0], "material": "orange",
             "body": "dynamic", "mass": M_L1, "friction": 0.6},
            {"name": "link2", "shape": {"type": "box", "size": [L2 / 1000, LINK_W / 1000, LINK_T / 1000]},
             "position": [(HUB + L1 + L2 / 2) / 1000, 0.12, 0], "material": "orange",
             "body": "dynamic", "mass": M_L2, "friction": 0.6},
        ],
        "joints": [
            # 偏航：立柱 ↔ 偏航块，轴竖直
            {"type": "hinge", "a": "column", "b": "yaw", "axis": [0, 1, 0],
             "anchor_a": [0, 0.045, 0], "anchor_b": [-HUB / 2000, 0, 0],
             "limits": [-2.09, 2.09], "motor_target_deg": yaw,
             "motor_stiffness": 8.0, "motor_damping": 10.0, "motor_max_impulse": 2.0},
            # 肩：偏航块 ↔ 大臂，轴朝 Z（抬起 +X）
            {"type": "hinge", "a": "yaw", "b": "link1", "axis": [0, 0, 1],
             "anchor_a": [HUB / 2000, 0, 0], "anchor_b": [-L1 / 2000, 0, 0],
             "limits": [math.radians(-25), math.radians(100)],
             "motor_target_deg": shoulder,
             "motor_stiffness": 20.0, "motor_damping": 10.0,
             "motor_max_impulse": 2.0, "break_torque": RATED_TORQUE},
            # 肘：大臂 ↔ 小臂
            {"type": "hinge", "a": "link1", "b": "link2", "axis": [0, 0, 1],
             "anchor_a": [L1 / 2000, 0, 0], "anchor_b": [-L2 / 2000, 0, 0],
             "limits": [math.radians(-150), math.radians(5)],
             "motor_target_deg": elbow,
             "motor_stiffness": 50.0, "motor_damping": 10.0,
             "motor_max_impulse": 2.0, "break_torque": RATED_TORQUE},
        ],
        "camera": {"position": [0.55, 0.35, 0.55], "look_at": [0.12, 0.12, 0],
                   "fov_deg": 45},
        "simulate": {"steps": 6000, "dt": 0.002},   # 12s：伺服要时间收敛
    }
    if cube is not None:
        cx, cz = cube
        scene["objects"].append({
            "name": "cube", "shape": {"type": "box", "size": [0.04, 0.04, 0.04]},
            "position": [cx, 0.02, cz], "material": "floor", "body": "dynamic",
            "mass": M_CUBE, "friction": 0.8})
    return scene


def zang(q: list[float]) -> float:
    """绕 Z 的转角（度）；只对 yaw=0 的姿态有效，够用于断言。"""
    return 2 * math.degrees(math.atan2(q[2], q[3]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yaw", type=float, default=0.0)
    ap.add_argument("--shoulder", type=float, default=35.0)
    ap.add_argument("--elbow", type=float, default=-55.0)
    ap.add_argument("--cube", default="", help="x,z（米），如 0.21,0.02")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()

    cube = None
    if a.cube:
        cx, cz = (float(v) for v in a.cube.split(","))
        cube = (cx, cz)

    scene = build(a.yaw, a.shoulder, a.elbow, cube)
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(scene, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写出 {out}（{len(scene['objects'])} 个物体 / {len(scene['joints'])} 个关节）")
    print("下一步：quench3d validate <文件>；quench3d simulate <文件> --json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
