"""统一绘图风格：中文字体 + 字号。缺字体会把中文画成方框，这里显式指定。"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

CJK = ["Noto Sans CJK JP", "Noto Sans CJK SC", "WenQuanYi Zen Hei", "DejaVu Sans"]


def setup() -> None:
    plt.rcParams["font.sans-serif"] = CJK
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.facecolor"] = "white"
    plt.rcParams["axes.grid"] = True
    plt.rcParams["grid.alpha"] = 0.25
