"""把场景 trace 画成调试图：俯视轨迹 + 关节角 + 电压/温度。"""

from __future__ import annotations

from pathlib import Path


def plot(result: dict, out: str | Path) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["Noto Sans CJK SC", "Noto Sans CJK JP",
                                       "WenQuanYi Zen Hei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    tr = result.get("trace") or []
    if not tr:
        raise ValueError("trace 为空：场景没有任何时间步进")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 6),
                                   gridspec_kw={"width_ratios": [1.1, 1]})
    ax1.plot([p["x"] for p in tr], [p["y"] for p in tr], lw=2, color="#1f6feb")
    ax1.scatter([tr[0]["x"]], [tr[0]["y"]], marker="o", color="#2ea043", label="起点")
    ax1.scatter([tr[-1]["x"]], [tr[-1]["y"]], marker="x", color="#d1242f", label="终点")
    ax1.set_aspect("equal")
    ax1.set_xlabel("x (mm)")
    ax1.set_ylabel("y (mm)")
    ax1.set_title("俯视轨迹")
    ax1.grid(alpha=0.3)
    ax1.legend(loc="best", fontsize=8)

    t = [p["t"] for p in tr]
    for k, c in (("j1", "#8250df"), ("j2", "#1f6feb"), ("j3", "#bf8700")):
        ax2.plot(t, [p[k] for p in tr], label=k.upper(), color=c, lw=1.4)
    ax2.set_xlabel("t (s)")
    ax2.set_ylabel("关节角 (°)")
    ax2.set_title("关节 / 电压")
    ax2.grid(alpha=0.3)
    ax2.legend(loc="upper left", fontsize=8)

    ax3 = ax2.twinx()
    ax3.plot(t, [p["v"] for p in tr], color="#d1242f", lw=1.2, ls="--", label="电压")
    ax3.set_ylabel("电压 (V)", color="#d1242f")
    ax3.tick_params(axis="y", labelcolor="#d1242f")
    ax3.legend(loc="upper right", fontsize=8)
    ax1.set_title(f"俯视轨迹（{len(tr)} 帧，{tr[-1]['t']:.1f}s）")
    fig.tight_layout()
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out
