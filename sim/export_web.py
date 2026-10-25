"""把参数与轨迹导出成网页能读的 scene.js（避免网页里再抄一份尺寸）。

产物：web/scene.js  →  window.MODKIT_SCENE = {...}
"""

from __future__ import annotations

import json
import math
import pathlib

import model as M
import params as P
import sequence

WEB = pathlib.Path(__file__).resolve().parent.parent / "web"

jaw_closed = P.JAW_GAP_OPEN / 2 * (1 + math.cos(math.radians(P.JAW_SWING)))

scene = {
    "meta": {
        "note": "由 sim/export_web.py 自动生成，请勿手改；改尺寸请改 cad/params.py",
        "version": "M1",
    },
    "params": {
        "chassisX": P.CHASSIS_X, "chassisY": P.CHASSIS_Y, "chassisT": P.CHASSIS_T,
        "wheelR": P.WHEEL_R, "wheelY": P.WHEEL_Y, "wheelW": 26,
        "servoZ": P.SERVO_Z, "driveY": P.DRIVE_Y,
        "armX": P.ARM_ORIGIN_X, "baseH": 90.0, "l1": 120.0, "l2": 110.0,
        "jawOpen": P.JAW_GAP_OPEN, "jawClosed": round(jaw_closed, 2),
        "linkW": 26.0, "linkT": 14.0, "columnR": 11.0,
        "gripperLen": 60.0, "gripperW": P.JAW_W, "jawT": P.JAW_T,
        "camX": -70.0, "camY": 60.0,
    },
    "limits": {
        "yaw": [-M.arm_geometry().yaw_limit, M.arm_geometry().yaw_limit],
        "shoulder": [-25.0, 100.0],
        "elbow": [-150.0, 5.0],
    },
    "ids": {"yaw": 1, "shoulder": 2, "elbow": 3, "gripper": 4, "left": 5, "right": 6},
    # 与 software/modkit/safety.py 的默认策略逐项对齐；网页用它做 fail-closed 预检。
    "safety": {
        "source": "design",
        "limits": {
            "yaw": [-M.arm_geometry().yaw_limit, M.arm_geometry().yaw_limit],
            "shoulder": [-25.0, 100.0],
            "elbow": [-150.0, 5.0],
            "gripper": [0.0, 1.0],
        },
        "max_step": {"yaw": 45.0, "shoulder": 45.0, "elbow": 60.0, "gripper": 0.5},
        "temp_warn_c": 45, "temp_max_c": 55,
        "voltage_warn_v": 10.8, "voltage_min_v": 10.2,
        "torque_limit": 600, "current_limit": 384,
        "acc": 30, "speed": 300,
    },
    "keyframes": sequence.keyframes(),
}

WEB.mkdir(exist_ok=True)
out = WEB / "scene.js"
out.write_text("window.MODKIT_SCENE = " + json.dumps(scene, ensure_ascii=False, indent=1) + ";\n",
               encoding="utf-8")
print(f"写出 {out} ({out.stat().st_size} B)")
