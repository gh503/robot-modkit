#!/usr/bin/env python
"""把 STL 渲染成多视角 PNG（给图纸评审用，不参与几何断言）。

    cd cad && ../.venv/bin/python render.py

输出：out/render_<part>.png（等轴测 + 正视 + 俯视三联），
      out/render_assembly.png（整个关节模块装配体，含舵机参考体）。
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import trimesh
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

OUT = Path(__file__).parent / "out"

COLORS = {
    "joint_base": "#4C78A8",
    "joint_lid": "#72B7B2",
    "output_disc": "#F58518",
    "link_bar": "#54A24B",
    "wheel_hub": "#B279A2",
    "servo_reference": "#8C8C8C",
    "chassis_right": "#4C78A8",
    "chassis_left": "#4C78A8",
    "chassis_joiner": "#72B7B2",
    "drive_bracket": "#E45756",
    "jaw_fixed": "#54A24B",
    "jaw_moving": "#F58518",
    "camera_mount": "#B279A2",
}

VIEWS = {
    "iso": (28, -50),
    "front": (0, -90),
    "top": (90, -90),
}


def load_mesh(path: Path) -> trimesh.Trimesh:
    m = trimesh.load(path, force="mesh")
    return m


def draw(ax, mesh: trimesh.Trimesh, color: str, elev: float, azim: float):
    tri = mesh.vertices[mesh.faces]
    n = mesh.face_normals
    light = np.array([0.4, -0.7, 0.8])
    light = light / np.linalg.norm(light)
    lam = np.clip(n @ light, 0.0, 1.0) * 0.7 + 0.3
    base = np.array(matplotlib.colors.to_rgb(color))
    rgba = np.clip(base[None, :] * lam[:, None], 0, 1)
    pc = Poly3DCollection(tri, facecolors=rgba, edgecolors="none", linewidths=0)
    ax.add_collection3d(pc)
    ax.view_init(elev=elev, azim=azim)


def finish(ax, meshes, title: str):
    pts = np.vstack([m.vertices for m in meshes])
    lo, hi = pts.min(0), pts.max(0)
    ctr = (lo + hi) / 2
    span = float(np.max(hi - lo)) * 0.62
    ax.set_xlim(ctr[0] - span, ctr[0] + span)
    ax.set_ylim(ctr[1] - span, ctr[1] + span)
    ax.set_zlim(ctr[2] - span, ctr[2] + span)
    ax.set_box_aspect((1, 1, 1))
    ax.set_axis_off()
    ax.set_title(title, fontsize=9, pad=0)


def render_part(name: str):
    mesh = load_mesh(OUT / f"{name}.stl")
    fig = plt.figure(figsize=(10, 3.4), dpi=150)
    for i, (view, (elev, azim)) in enumerate(VIEWS.items(), 1):
        ax = fig.add_subplot(1, 3, i, projection="3d")
        draw(ax, mesh, COLORS.get(name, "#888888"), elev, azim)
        finish(ax, [mesh], f"{name} · {view}  (mm)")
    fig.tight_layout()
    path = OUT / f"render_{name}.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def render_assembly():
    stack = ["joint_base", "servo_reference", "joint_lid", "output_disc"]
    meshes = [(n, load_mesh(OUT / f"{n}.stl")) for n in stack]
    fig = plt.figure(figsize=(10, 3.4), dpi=150)
    for i, (view, (elev, azim)) in enumerate(VIEWS.items(), 1):
        ax = fig.add_subplot(1, 3, i, projection="3d")
        for n, m in meshes:
            draw(ax, m, COLORS.get(n, "#888888"), elev, azim)
        finish(ax, [m for _, m in meshes], f"assembly · {view}")
    fig.tight_layout()
    path = OUT / "render_assembly.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def main():
    made = [render_assembly()]
    for name in COLORS:
        if name == "servo_reference":
            continue
        if (OUT / f"{name}.stl").exists():
            made.append(render_part(name))
    # 防止"渲染出白图"这种静默失败
    for p in made:
        img = plt.imread(p)
        spread = float(np.nanstd(img))
        print(f"  {p.name:28s} {img.shape[1]}×{img.shape[0]} 像素标准差 {spread:.3f}"
              f"{'  <-- 可能是空图!' if spread < 0.01 else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())