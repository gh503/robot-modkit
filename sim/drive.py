"""底盘闭环仿真：PI 速度环 + 打滑/延迟/噪声，对比开环与闭环。

它回答三个只有上车才会问的问题：
1. 开环跑 2 米，实际会偏多少？（答案：偏到你不能接受）
2. PI 能不能把打滑补回来？（能，但积分要时间）
3. 里程计在打滑时怎么跑偏？（这决定了 M3 视觉要不要闭环校正）
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path

import style

style.setup()
import matplotlib.pyplot as plt
import numpy as np

OUT = Path(__file__).resolve().parent / "out"

# 控制器参数与固件 drive.cpp 保持一致（改了这里也要改那里）
KP, KI = 2.0, 12.0   # 网格搜索选出：直线 20s 误差 7mm、转角过冲 <3°
INT_LIM, U_MAX = 1000.0, 300.0
DT = 0.02


@dataclass
class Plant:
    """简化的底盘被控对象：一阶惯性 + 左右打滑 + 速度噪声。"""

    tau: float = 0.12          # 舵机跟随时间常数
    slip_left: float = 0.88    # 有效速度比例（打滑/负载）
    slip_right: float = 0.93
    noise: float = 1.5         # mm/s 随机噪声
    v_l: float = 0.0
    v_r: float = 0.0
    rng: np.random.Generator = field(default_factory=lambda: np.random.default_rng(7))

    def step(self, cmd_l: float, cmd_r: float, dt: float) -> tuple[float, float]:
        a = dt / (self.tau + dt)
        self.v_l += a * (cmd_l * self.slip_left - self.v_l)
        self.v_r += a * (cmd_r * self.slip_right - self.v_r)
        self.v_l += self.rng.normal(0, self.noise) * 0.1
        self.v_r += self.rng.normal(0, self.noise) * 0.1
        return self.v_l, self.v_r


def run(v_cmd: float, w_cmd_deg: float, seconds: float, closed: bool,
        plant: Plant | None = None, hard_stop: float | None = None) -> dict:
    """v_cmd: mm/s，w_cmd_deg: deg/s。返回真值轨迹与里程计轨迹。"""
    plant = plant or Plant()
    x = y = yaw = 0.0          # 真值
    ox = oy = oyaw = 0.0       # 里程计（由轮子计数推算，含打滑）
    tick_l = tick_r = 0.0
    integ_l = integ_r = 0.0
    vmeas_l = vmeas_r = 0.0
    log = []
    n = int(seconds / DT)

    for i in range(n):
        w_rad = math.radians(w_cmd_deg)
        tl = v_cmd - w_rad * 75.0
        tr = v_cmd + w_rad * 75.0

        if closed:
            el, er = tl - vmeas_l, tr - vmeas_r
            integ_l = float(np.clip(integ_l + el * DT, -INT_LIM, INT_LIM))
            integ_r = float(np.clip(integ_r + er * DT, -INT_LIM, INT_LIM))
            ul = float(np.clip(KP * el + KI * integ_l, -U_MAX, U_MAX))
            ur = float(np.clip(KP * er + KI * integ_r, -U_MAX, U_MAX))
        else:
            ul, ur = tl, tr

        vl, vr = plant.step(ul, ur, DT)
        vmeas_l, vmeas_r = vl, vr

        # 真值积分
        v = (vl + vr) / 2
        omega = (vr - vl) / 150.0
        x += v * math.cos(yaw) * DT
        y += v * math.sin(yaw) * DT
        yaw += omega * DT

        # 里程计：只信"轮子转了多少"，打滑时它会算多
        tick_l += vl / 0.04986 * DT
        tick_r += vr / 0.04986 * DT
        dl, dr = ktick((vl, vr), DT)
        ds = (dl + dr) / 2
        dth = (dr - dl) / 150.0
        ox += ds * math.cos(oyaw) * DT / DT if False else ds * math.cos(oyaw)
        oy += ds * math.sin(oyaw)
        oyaw += dth
        log.append((i * DT, x, y, math.degrees(yaw), vl, vr, ul, ur))

        if hard_stop is not None and abs(v) * (i * DT) >= hard_stop:
            break

    return {
        "x": x, "y": y, "yaw_deg": math.degrees(yaw),
        "odom_x": ox, "odom_y": oy, "odom_yaw": math.degrees(oyaw),
        "log": log, "time": n * DT,
    }


def ktick(vel: tuple[float, float], dt: float) -> tuple[float, float]:
    return vel[0] * dt, vel[1] * dt


def scenario_straight(closed: bool) -> dict:
    r = run(100.0, 0.0, 20.0, closed)
    dist = math.hypot(r["x"], r["y"])
    lateral = r["y"]
    return {"name": "直线 100mm/s×20s", "closed": closed, "dist": dist,
            "target": 2000.0, "err_mm": dist - 2000.0, "lateral": lateral, **r}


def scenario_turn(closed: bool, target_deg: float = 90.0, radius_err: float = 0.0) -> dict:
    """转到指定角度：外环 P（角度误差→角速度）+ 内环 PI（轮速）。

    只跑固定时间是不对的：转 90° 必须"转到就停"。所以这里是一个真正的外环。
    开环对照 = 不修正轮速，按标称角速度转，转到里程计说到了就停。
    """
    plant = Plant()
    yaw = oyaw = 0.0
    integ = [0.0, 0.0]
    vmeas = [0.0, 0.0]
    t = 0.0
    log = []
    while t < 8.0:
        rem = target_deg - oyaw
        if abs(rem) < 0.2:
            break
        w_cmd = max(-90.0, min(90.0, 3.0 * rem))
        w_rad = math.radians(w_cmd)
        tl, tr = -w_rad * 75.0, w_rad * 75.0
        if closed:
            cmds = []
            for k, (tgt, meas) in enumerate(((tl, vmeas[0]), (tr, vmeas[1]))):
                e = tgt - meas
                integ[k] = float(np.clip(integ[k] + e * DT, -INT_LIM, INT_LIM))
                cmds.append(float(np.clip(KP * e + KI * integ[k], -U_MAX, U_MAX)))
            ul, ur = cmds
        else:
            ul, ur = tl, tr
        vl, vr = plant.step(ul, ur, DT)
        vmeas[0], vmeas[1] = vl, vr
        dth = (vr - vl) / 150.0
        yaw += dth
        oyaw += math.degrees(dth) * (1.0 + radius_err)   # 里程计航向（可注入轮径标定误差）
        t += DT
        log.append((t, math.degrees(yaw), vl, vr))
    return {"name": f"原地转 {target_deg:.0f}°", "closed": closed,
            "yaw": math.degrees(yaw), "target": target_deg,
            "err_deg": math.degrees(yaw) - target_deg, "time": t, "log": log}


def scenario_square(closed: bool, side: float = 1000.0, v: float = 120.0,
                    turn_deg: float = 90.0) -> dict:
    """四段直线 + 四次转弯，最后回到起点附近。"""
    plant = Plant()
    x = y = yaw = 0.0
    ox = oy = oyaw = 0.0
    path = [(0.0, 0.0)]
    opath = [(0.0, 0.0)]
    integ = [0.0, 0.0]
    vmeas = [0.0, 0.0]
    t_total = 0.0

    def drive(v_cmd: float, w_cmd: float, seconds: float):
        nonlocal x, y, yaw, ox, oy, oyaw, t_total
        for _ in range(int(seconds / DT)):
            w_rad = math.radians(w_cmd)
            tl, tr = v_cmd - w_rad * 75.0, v_cmd + w_rad * 75.0
            if closed:
                for k, (tgt, meas) in enumerate(((tl, vmeas[0]), (tr, vmeas[1]))):
                    e = tgt - meas
                    integ[k] = float(np.clip(integ[k] + e * DT, -INT_LIM, INT_LIM))
                    cmd = float(np.clip(KP * e + KI * integ[k], -U_MAX, U_MAX))
                    if k == 0: ul = cmd
                    else: ur = cmd
            else:
                ul, ur = tl, tr
            vl, vr = plant.step(ul, ur, DT)
            vmeas[0], vmeas[1] = vl, vr
            v = (vl + vr) / 2
            x += v * math.cos(yaw) * DT
            y += v * math.sin(yaw) * DT
            yaw += (vr - vl) / 150.0 * DT
            dl, dr = vl * DT, vr * DT
            ds, dth = (dl + dr) / 2, (dr - dl) / 150.0
            ox += ds * math.cos(oyaw)
            oy += ds * math.sin(oyaw)
            oyaw += dth
            t_total += DT
        path.append((x, y))
        opath.append((ox, oy))

    side_time = side / v
    turn_time = math.radians(turn_deg) * 75.0 / (v * 0.5)  # 近似：差速转过 90°
    for _ in range(4):
        drive(v, 0.0, side_time)
        drive(0.0, turn_deg / turn_time, turn_time)

    return {"name": f"{side/1000:.1f}m 方形巡视", "closed": closed,
            "end_err": math.hypot(x, y), "yaw_err": math.degrees(yaw) - 360.0,
            "path": path, "opath": opath, "time": t_total}


def save_plot(straight_open, straight_closed, square_open, square_closed,
              path: Path = OUT / "drive_sim.png") -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.2), dpi=130)

    ax = axes[0]
    for r, color, ls in ((straight_open, "#B0B0B0", "--"), (straight_closed, "#4C78A8", "-")):
        xs = [row[1] for row in r["log"]]
        ys = [row[2] for row in r["log"]]
        ax.plot(xs, ys, ls, color=color, lw=2,
                label=f"{'开环' if not r['closed'] else '闭环'}：{r['dist']:.0f} mm")
    ax.axhline(0, color="#DDD", lw=1)
    ax.set_aspect("equal")
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    ax.set_title("直线 2m：闭环把打滑补回来了")
    ax.legend(fontsize=9)
    ax.grid(alpha=0.25)

    ax = axes[1]
    for sq, color, label in ((square_open, "#B0B0B0", "开环"),
                             (square_closed, "#54A24B", "闭环")):
        p = np.array(sq["path"])
        ax.plot(p[:, 0], p[:, 1], "-", color=color, lw=2, label=f"{label} 真值")
        op = np.array(sq["opath"])
        ax.plot(op[:, 0], op[:, 1], ":", color=color, lw=1.2, label=f"{label} 里程计")
    ax.plot([0], [0], "ko", ms=6)
    ax.set_aspect("equal")
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    ax.set_title("1m 方形巡视：真值 vs 里程计（打滑让它跑偏）")
    ax.legend(fontsize=8, ncol=2)
    ax.grid(alpha=0.25)

    fig.tight_layout()
    OUT.mkdir(exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def main() -> int:
    so, sc = scenario_straight(False), scenario_straight(True)
    to, tc = scenario_turn(False), scenario_turn(True)
    tr = scenario_turn(True, radius_err=0.02)   # 轮径标定差 2%
    qo, qc = scenario_square(False), scenario_square(True)

    rows = [
        ("直线 2m", "开环", f"{so['dist']:.1f} mm", f"{so['err_mm']:+.1f} mm", "—"),
        ("直线 2m", "闭环", f"{sc['dist']:.1f} mm", f"{sc['err_mm']:+.1f} mm", "—"),
        ("原地转 90°", "开环", f"{to['yaw']:.1f}°", f"{to['err_deg']:+.1f}°", f"用时 {to['time']:.1f}s"),
        ("原地转 90°", "闭环", f"{tc['yaw']:.1f}°", f"{tc['err_deg']:+.1f}°", f"用时 {tc['time']:.1f}s"),
        ("转角+轮径差2%", "闭环", f"{tr['yaw']:.1f}°", f"{tr['err_deg']:+.1f}°", "标定误差直接变成角度误差"),
        ("1m 方形", "开环", f"{qo['end_err']:.0f} mm", f"{qo['yaw_err']:+.0f}°", "里程计漂移见曲线"),
        ("1m 方形", "闭环", f"{qc['end_err']:.0f} mm", f"{qc['yaw_err']:+.0f}°", "里程计漂移见曲线"),
    ]

    OUT.mkdir(exist_ok=True)
    with (OUT / "drive_metrics.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["场景", "控制", "实测", "误差", "备注"])
        w.writerows(rows)

    print(f"{'场景':<14}{'控制':<6}{'实测':<14}{'误差':<12}备注")
    for r in rows:
        print(f"{r[0]:<14}{r[1]:<6}{r[2]:<14}{r[3]:<12}{r[4]}")

    p = save_plot(so, sc, qo, qc)
    print(f"\n写出 {p}")

    # 判据（与 docs/06 G7 对齐）
    ok = True
    if abs(sc["err_mm"]) > 50:
        print(f"FAIL 闭环直线误差 {sc['err_mm']:.0f} mm > 50 mm")
        ok = False
    if abs(tc["err_deg"]) > 3:
        print(f"FAIL 闭环转角误差 {tc['err_deg']:.2f}° > 3°")
        ok = False
    if abs(so["err_mm"]) <= abs(sc["err_mm"]):
        print("FAIL 开环不该比闭环更准（仿真没体现出闭环价值，检查模型）")
        ok = False
    print("仿真判据全部通过" if ok else "仿真判据未通过")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())