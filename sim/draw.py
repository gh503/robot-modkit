"""把 Scene 画出来：整机多视图、带尺寸的侧视图、工作空间热力图。

为什么用 matplotlib 而不是渲染 STL：这里要验证的是**角度→位姿**的正确性，
骨架模型能保证这一点；真实外形请配合 cad/out 里的 STL / STEP。
"""

from __future__ import annotations

import math
from pathlib import Path

import style

style.setup()
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, FancyArrowPatch, Rectangle
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

import model as M
import params as P
from modkit import kinematics as kin

OUT = Path(__file__).resolve().parent / "out"

STEEL = "#4C78A8"
DARK = "#2F3B45"
ACCENT = "#E45756"
GREEN = "#54A24B"
WOOD = "#C9A227"


# ------------------------------------------------------------------ 3D 基元
def _box(ax, cx, cy, cz, sx, sy, sz, color, alpha=1.0, edge=DARK):
    x, y, z = cx - sx / 2, cy - sy / 2, cz - sz / 2
    v = np.array(
        [
            [x, y, z], [x + sx, y, z], [x + sx, y + sy, z], [x, y + sy, z],
            [x, y, z + sz], [x + sx, y, z + sz], [x + sx, y + sy, z + sz], [x, y + sy, z + sz],
        ]
    )
    f = [[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    pc = Poly3DCollection(v[f], facecolor=color, edgecolor=edge, linewidths=0.5, alpha=alpha)
    ax.add_collection3d(pc)


def _cyl(ax, p0, p1, r, color, alpha=1.0, n=16):
    """两点之间的圆柱（用于连杆、轮子）。"""
    p0, p1 = np.array(p0, float), np.array(p1, float)
    axis = p1 - p0
    length = np.linalg.norm(axis)
    if length < 1e-9:
        return
    axis /= length
    tmp = np.array([0, 0, 1.0]) if abs(axis[2]) < 0.9 else np.array([1.0, 0, 0])
    u = np.cross(axis, tmp)
    u /= np.linalg.norm(u)
    v = np.cross(axis, u)
    t = np.linspace(0, 2 * np.pi, n)
    circle = np.outer(np.cos(t), u) + np.outer(np.sin(t), v)
    verts, faces = [], []
    for i in range(n):
        verts.append(p0 + r * circle[i])
        verts.append(p1 + r * circle[i])
    for i in range(n):
        j = (i + 1) % n
        faces.append([2 * i, 2 * i + 1, 2 * j + 1, 2 * j])
    faces.append(list(range(0, 2 * n, 2))[::-1])
    faces.append(list(range(1, 2 * n, 2)))
    pc = Poly3DCollection([np.array(verts)[f] for f in faces], facecolor=color,
                          edgecolor="none", alpha=alpha)
    ax.add_collection3d(pc)


def _sphere(ax, p, r, color):
    u, v = np.mgrid[0:2 * np.pi:12j, 0:np.pi:8j]
    x = p[0] + r * np.cos(u) * np.sin(v)
    y = p[1] + r * np.sin(u) * np.sin(v)
    z = p[2] + r * np.cos(v)
    ax.plot_surface(x, y, z, color=color, linewidth=0, shade=True, alpha=0.95)


# ------------------------------------------------------------------ 整机
def draw_robot(ax, st: M.RobotState) -> None:
    # 地面
    g = M.GROUND
    xs, ys = np.meshgrid([-160, 200], [-140, 140])
    ax.plot_surface(xs, ys, np.full_like(xs, g), color="#EDEDED", alpha=0.55, linewidth=0)

    # 底盘三块（简化为一块板 + 接缝线）
    _box(ax, 0, 0, -P.CHASSIS_T / 2, P.CHASSIS_X, P.CHASSIS_Y, P.CHASSIS_T, "#D8DEE9")
    ax.plot([0, 0], [-P.CHASSIS_Y / 2, P.CHASSIS_Y / 2], [0, 0], color=DARK, lw=0.8)

    # 驱动轮（轴线沿 Y，在 y=±WHEEL_Y）
    for sy in (-1, 1):
        y = sy * P.WHEEL_Y
        _cyl(ax, (0, y - 13, P.SERVO_Z), (0, y + 13, P.SERVO_Z), P.WHEEL_R, "#3A3A3A", 0.95)
        _cyl(ax, (0, y - 13.5, P.SERVO_Z), (0, y + 13.5, P.SERVO_Z), P.WHEEL_R * 0.35, STEEL)
        _box(ax, 0, sy * P.DRIVE_Y, P.SERVO_Z, 46, 26, 36, "#8C8C8C", 0.75)  # 舵机
        _box(ax, 0, sy * P.DRIVE_Y, -2.5, 60, 44, 5, ACCENT, 0.45)            # 支架

    # 相机
    _box(ax, -70, 60, 12, 30, 30, 20, "#B279A2", 0.9)

    pts = M.joint_points(st)
    base, sh, el, wr = pts["base"], pts["shoulder"], pts["elbow"], pts["wrist"]

    # 立柱
    _cyl(ax, (M.ARM_X, 0, 0), (M.ARM_X, 0, sh[2] - 14), 11, STEEL, 0.9)
    _sphere(ax, base, 17, DARK)

    # 上臂 / 前臂
    _cyl(ax, sh, el, 9, STEEL)
    _cyl(ax, el, wr, 8, STEEL)
    for p in (sh, el):
        _sphere(ax, p, 14, DARK)

    # 腕 + 夹爪（两只爪指，按 jaw 开合）
    gap = M.gap_mm(st.jaw) / 2
    d = np.array(wr) - np.array(el)
    d /= np.linalg.norm(d)
    side = np.array([0.0, 1.0, 0.0])
    for s in (-1, 1):
        a = np.array(wr) + side * s * (gap + 3)
        b = a + d * 30 + np.array([0, 0, -30])
        _box(ax, (a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2, 26, 6, 52, GREEN, 0.95)
    _box(ax, wr[0], wr[1], wr[2], 34, 44, 12, "#F58518", 0.95)


def set_view(ax, elev=22, azim=-58, span=300):
    ax.view_init(elev=elev, azim=azim)
    ax.set_box_aspect((1.3, 1.0, 1.15))
    ax.set_xlim(-span * 0.35, span * 0.95)
    ax.set_ylim(-span * 0.45, span * 0.45)
    ax.set_zlim(M.GROUND - 8, span * 0.62)
    ax.set_xlabel("x 前 (mm)")
    ax.set_ylabel("y 左 (mm)")
    ax.set_zlabel("z 上 (mm)")
    ax.grid(alpha=0.25)


def save_views(path: Path = OUT / "robot_views.png") -> Path:
    st = M.RobotState(shoulder=35, elbow=-55, jaw=1.0)
    fig = plt.figure(figsize=(13, 10), dpi=130)
    views = [(24, -58, "轴测"), (0, -90, "正视"), (0, 0, "侧视"), (78, -90, "俯视")]
    for i, (elev, azim, name) in enumerate(views, 1):
        ax = fig.add_subplot(2, 2, i, projection="3d")
        draw_robot(ax, st)
        set_view(ax, elev, azim)
        ax.set_title(f"{name}  elev={elev}° azim={azim}°", fontsize=10)
    fig.suptitle("modkit M1 整机（运动学模型；肩 35° 肘 -55°）", fontsize=13)
    fig.tight_layout()
    OUT.mkdir(exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


# ------------------------------------------------------------------ 2D 尺寸图
def save_dimensions(path: Path = OUT / "robot_dimensions.png") -> Path:
    st = M.RobotState(shoulder=35, elbow=-55, jaw=1.0)
    pts = M.joint_points(st)
    g = M.GROUND
    fig, ax = plt.subplots(figsize=(12, 8), dpi=130)

    # 地面 & 底盘 & 轮
    ax.axhline(g, color="#999999", lw=1.2)
    ax.add_patch(Rectangle((-P.CHASSIS_X / 2, -P.CHASSIS_T), P.CHASSIS_X, P.CHASSIS_T,
                           facecolor="#D8DEE9", edgecolor=DARK))
    for y in (-P.WHEEL_Y, P.WHEEL_Y):
        ax.add_patch(Circle((0, P.SERVO_Z), P.WHEEL_R, facecolor="#3A3A3A", edgecolor=DARK))
    ax.text(0, P.SERVO_Z, f"Ø{2*P.WHEEL_R:.0f} 轮", color="white", ha="center", va="center", fontsize=8)

    # 立柱 / 臂
    ax.plot([M.ARM_X, M.ARM_X], [0, pts["shoulder"][2]], color=STEEL, lw=14, solid_capstyle="round")
    ax.plot([pts["shoulder"][0], pts["elbow"][0]], [pts["shoulder"][2], pts["elbow"][2]],
            color=STEEL, lw=10, solid_capstyle="round")
    ax.plot([pts["elbow"][0], pts["wrist"][0]], [pts["elbow"][2], pts["wrist"][2]],
            color=STEEL, lw=8, solid_capstyle="round")
    ax.plot([pts["wrist"][0], pts["tip"][0]], [pts["wrist"][2], pts["tip"][2]],
            color=GREEN, lw=8, solid_capstyle="round")

    # 尺寸标注
    def dim(p0, p1, text, off=0):
        ax.annotate("", xy=p0, xytext=p1,
                    arrowprops=dict(arrowstyle="<->", color=ACCENT, lw=1.2))
        ax.text((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2 + off, text,
                color=ACCENT, fontsize=9, ha="center",
                bbox=dict(fc="white", ec="none", alpha=0.8, pad=1))

    dim((M.ARM_X + 40, 0), (M.ARM_X + 40, pts["shoulder"][2]), f"立柱 {pts['shoulder'][2]:.0f}")
    dim((pts["shoulder"][0] - 10, pts["shoulder"][2] + 6),
        (pts["elbow"][0], pts["elbow"][2]), "上臂 120", 6)
    dim((pts["elbow"][0], pts["elbow"][2] - 8), (pts["wrist"][0], pts["wrist"][2]), "前臂 110", -10)
    dim((-P.WHEEL_Y, g - 18), (P.WHEEL_Y, g - 18), f"轮距 {2*P.WHEEL_Y:.0f}", -6)

    # 总高
    tip_z = max(pts["tip"][2], pts["wrist"][2])
    ax.annotate("", xy=(-120, g), xytext=(-120, tip_z),
                arrowprops=dict(arrowstyle="<->", color=DARK, lw=1))
    ax.text(-125, (g + tip_z) / 2, f"高 {tip_z - g:.0f} mm", rotation=90,
            va="center", ha="right", color=DARK)

    ax.set_aspect("equal")
    ax.set_xlim(-170, 330)
    ax.set_ylim(g - 35, 300)
    ax.set_xlabel("x 前 (mm)")
    ax.set_ylabel("z 上 (mm)")
    ax.set_title("整机侧视尺寸（肩 35°，肘 -55°）")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


# ------------------------------------------------------------------ 工作空间
def save_workspace(path: Path = OUT / "arm_workspace.png") -> Path:
    g = M.arm_geometry()
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.6), dpi=130)
    ax = axes[0]
    reach = np.zeros((120, 160))
    for i, x in enumerate(np.linspace(-40, 260, 160)):
        for j, z in enumerate(np.linspace(0, 260, 120)):
            try:
                kin.inverse(g, kin.Pose(x, 0, z))
                reach[j, i] = 1
            except kin.UnreachableError:
                reach[j, i] = 0
    ax.imshow(reach, origin="lower", extent=[-40, 260, 0, 260], aspect="equal",
              cmap="Blues", alpha=0.55)
    ax.contour(np.linspace(-40, 260, 160), np.linspace(0, 260, 120), reach, levels=[0.5],
               colors=[ACCENT], linewidths=1.5)
    ax.plot([M.ARM_X], [g.base_h], "o", color=DARK, ms=10, label="肩关节")
    ax.set_xlabel("x 前 (mm)")
    ax.set_ylabel("z 上 (mm)")
    ax.set_title("可达工作空间（含关节限位）")
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(alpha=0.2)

    # 同一目标的两组解
    ax2 = axes[1]
    target = kin.Pose(150, 0, 150)
    for up, color, label in ((False, "#4C78A8", "肘下"), (True, "#E45756", "肘上")):
        try:
            y, s, e = kin.inverse(g, target, elbow_up=up)
        except kin.UnreachableError as exc:
            # 真实约束：肘关节限位 [-150°, 5°] → "肘上"解在这儿是超限的。
            # 这不是画图失败，而是设计事实：本机只有一个可用肘解支。
            ax2.plot([], [], color=color, label=f"{label}：不可用（{exc}）")
            continue
        st = M.RobotState(yaw=y, shoulder=s, elbow=e)
        pts = M.joint_points(st)
        ax2.plot([M.ARM_X, pts["elbow"][0], pts["wrist"][0]],
                 [pts["shoulder"][2], pts["elbow"][2], pts["wrist"][2]],
                 "-o", color=color, lw=6, ms=6, label=f"{label}（肩{s:.0f}° 肘{e:.0f}°）")
    ax2.plot([target.x], [target.z], "*", color=GREEN, ms=18, label="目标 (150,150)")
    ax2.set_aspect("equal")
    ax2.set_xlim(-20, 300)
    ax2.set_ylim(0, 280)
    ax2.set_xlabel("x 前 (mm)")
    ax2.set_ylabel("z 上 (mm)")
    ax2.set_title("同一目标的两组逆解（肘上 / 肘下）")
    ax2.legend(fontsize=9)
    ax2.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for fn in (save_views, save_dimensions, save_workspace):
        p = fn()
        print(f"写出 {p}  ({p.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()