"""抓取动作仿真：给定起止位姿，用逆解算出关节轨迹，逐帧渲染成 GIF。

这是"没有硬件也能调动作"的核心工具：
  改目标点 → 立刻能看到臂会不会撞桌子、够不够得着、姿态顺不顺。
它不替代真机（没有碰撞动力学、没有舵机延迟），但能把 80% 的"明显不对"提前暴露。
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

import model as M
import draw as R
import sequence
from modkit import kinematics as kin

OUT = Path(__file__).resolve().parent / "out"


def build_sequence():
    """从 sequence.keyframes() 取姿态，转成 (状态, 帧数, 字幕)。"""
    ks = sequence.keyframes()
    durs = [10, 18, 16, 10, 18, 22, 16, 10, 20]
    out = []
    for k, d in zip(ks, durs):
        out.append((M.RobotState(k["yaw"], k["shoulder"], k["elbow"], k["jaw"]), d, k["label"]))
    return out


def frames() -> list[tuple[M.RobotState, str]]:
    seq = build_sequence()
    out: list[tuple[M.RobotState, str]] = []
    for i in range(len(seq) - 1):
        a, n, label = seq[i]
        b = seq[i + 1][0]
        for k in range(n):
            out.append((lerp_state(a, b, k / n, a.jaw + (b.jaw - a.jaw) * k / n), label))
    out.append((seq[-1][0], seq[-1][2]))
    return out


def draw_frame(st: M.RobotState, label: str, block_held: bool, block_xy: tuple[float, float]):
    fig = plt.figure(figsize=(8, 6.4), dpi=110)
    ax = fig.add_subplot(111, projection="3d")
    R.draw_robot(ax, st)
    if not block_held:
        R._box(ax, block_xy[0], block_xy[1], M.GROUND + 20, 40, 40, 40, "#E45756")
    else:
        pts = M.joint_points(st)
        tip = pts["tip"]
        R._box(ax, tip[0], tip[1], tip[2] - 20, 40, 40, 40, "#E45756")
    R.set_view(ax, 20, -62, span=320)
    ax.set_title(f"modkit M1 · 抓取仿真   {label}\n"
                 f"偏航 {st.yaw:+.0f}°  肩 {st.shoulder:+.0f}°  肘 {st.elbow:+.0f}°  "
                 f"夹爪 {M.gap_mm(st.jaw):.0f}mm", fontsize=10)
    fig.tight_layout()
    fig.canvas.draw()
    img = np.asarray(fig.canvas.buffer_rgba())[:, :, :3].copy()
    plt.close(fig)
    return img


def main() -> None:
    OUT.mkdir(exist_ok=True)
    seq = frames()
    imgs = []
    block_xy = (200.0, 0.0)
    for i, (st, label) in enumerate(seq):
        imgs.append(Image.fromarray(draw_frame(st, label, block_held=st.jaw < 0.5, block_xy=block_xy)))
        if i % 10 == 0:
            print(f"  帧 {i}/{len(seq)}")

    gif = OUT / "arm_grasp.gif"
    imgs[0].save(gif, save_all=True, append_images=imgs[1:], duration=90, loop=0, optimize=True)
    print(f"写出 {gif}  ({len(imgs)} 帧, {gif.stat().st_size // 1024} KB)")

    # 关键帧拼图，方便一眼看全流程
    picks = [0, 28, 44, 54, 72, 94, 110, 120, 140]
    picks = [p for p in picks if p < len(imgs)][:9]
    cols, rows = 3, (len(picks) + 2) // 3
    w, h = imgs[0].size
    sheet = Image.new("RGB", (cols * w // 2, rows * h // 2), "white")
    for i, p in enumerate(picks):
        sheet.paste(imgs[p].resize((w // 2, h // 2)), ((i % cols) * w // 2, (i // cols) * h // 2))
    sheet.save(OUT / "arm_grasp_sheet.png")
    print(f"写出 {OUT / 'arm_grasp_sheet.png'}")


if __name__ == "__main__":
    main()