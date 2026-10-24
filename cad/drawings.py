"""带尺寸的 2D 工程图（A4 横版，多页 PDF）。

为什么要有：3D 模型解决"长什么样"，工程图解决"做多大、公差多少"。
车间/打印店只认图纸上的数字，不认 STEP。

每个零件一页：
    · 俯视 / 正视 / 侧视 三个正投影（等比例，取 1:1 / 1:2 / 1:2.5 …）
    · 总体尺寸标注（从几何实测，不是抄参数）
    · 孔标注：按半径分组，"4×Ø3.4"这种
    · 标题栏：名称、材料、数量、比例、版本、单位
    · 技术要求：打印方向、填充、公差、去毛刺

用法：cd cad && ../.venv/bin/python drawings.py
产物：docs/drawings/modkit-m1-drawings.pdf
      docs/images/drawing_<part>.png
"""

from __future__ import annotations

import datetime as _dt
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

# 中文字体：不设会把"俯视/正视"画成方框
for _f in ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
           "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
           "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"):
    if pathlib.Path(_f).exists():
        fm.fontManager.addfont(_f)
plt.rcParams["font.sans-serif"] = ["Noto Sans CJK JP", "Noto Sans CJK SC",
                                   "WenQuanYi Zen Hei", "DejaVu Sans"]
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["axes.unicode_minus"] = False
from matplotlib.patches import Rectangle

import params as P
import parts as K
import parts_m1 as M1
import tools as T

DOCS = pathlib.Path(__file__).parent.parent / "docs"
OUT_PDF = DOCS / "drawings" / "modkit-m1-drawings.pdf"
IMG_DIR = DOCS / "images"

PAGE = (297.0, 210.0)          # A4 横版，单位 mm
INK = "#111111"
GREY = "#6b7280"
REV = "M1 / v0.5"

PARTS = [
    ("chassis_right", "底盘右半", 1, "PETG", "3:30"),
    ("chassis_left", "底盘左半", 1, "PETG", "3:30"),
    ("chassis_joiner", "底盘连接板", 1, "PETG", "1:30"),
    ("joint_base", "关节底座", 4, "PETG", "2:10"),
    ("joint_lid", "关节压盖", 4, "PETG", "1:40"),
    ("link_bar", "连杆", 4, "PETG", "1:20"),
    ("output_disc", "输出盘", 4, "PETG", "0:50"),
    ("drive_bracket", "驱动舵机支架", 2, "PETG", "1:10"),
    ("jaw_fixed", "夹爪定爪", 1, "PETG", "1:20"),
    ("jaw_moving", "夹爪动爪", 1, "PETG", "1:20"),
    ("camera_mount", "相机支架", 1, "PETG", "1:00"),
    ("wheel_hub", "轮毂", 2, "PETG", "1:50"),
]


def polylines(part, plane: str, tol: float = 1.0) -> list[list[tuple[float, float]]]:
    """把每条边采样成 2D 折线。plane: xy / xz / yz。"""
    out = []
    for e in part.edges():
        n = max(2, min(64, int(e.length / tol) + 2))
        pts = [e @ (i / (n - 1)) for i in range(n)]
        if plane == "xy":
            out.append([(p.X, p.Y) for p in pts])
        elif plane == "xz":
            out.append([(p.X, p.Z) for p in pts])
        else:
            out.append([(p.Y, p.Z) for p in pts])
    return out


def bounds(lines):
    xs = [p[0] for l in lines for p in l]
    ys = [p[1] for l in lines for p in l]
    return min(xs), max(xs), min(ys), max(ys)


def pick_scale(width: float, height: float, box_w: float, box_h: float) -> float:
    """返回比例分母：1 表示 1:1。"""
    for d in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if width / d <= box_w and height / d <= box_h:
            return d
    return 12


def draw_view(ax, lines, title: str, scale: float, box_w: float, box_h: float):
    # 横放能占满画面时自动转 90°（底盘这类长条零件横着放，字才看得清）
    x0, x1, y0, y1 = bounds(lines)
    if (y1 - y0) > (x1 - x0) * 1.15 and box_w > box_h:
        lines = [[(p[1], p[0]) for p in l] for l in lines]
        x0, x1, y0, y1 = bounds(lines)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    for l in lines:
        ax.plot([(p[0] - cx) / scale for p in l], [(p[1] - cy) / scale for p in l],
                color=INK, lw=0.55, solid_capstyle="round")
    ax.set_xlim(-box_w / 2, box_w / 2)
    ax.set_ylim(-box_h / 2, box_h / 2)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"{title}   1:{scale:g}", fontsize=7, color=GREY, pad=2)
    return x0, x1, y0, y1, cx, cy


def hdim(ax, x1, x2, y, text):
    ax.annotate("", xy=(x1, y), xytext=(x2, y),
                arrowprops=dict(arrowstyle="<->", lw=0.5, color=INK, shrinkA=0, shrinkB=0))
    ax.text((x1 + x2) / 2, y + 1.2, text, ha="center", va="bottom", fontsize=6, color=INK)


def vdim(ax, x, y1, y2, text):
    ax.annotate("", xy=(x, y1), xytext=(x, y2),
                arrowprops=dict(arrowstyle="<->", lw=0.5, color=INK, shrinkA=0, shrinkB=0))
    ax.text(x - 0.8, (y1 + y2) / 2, text, ha="right", va="center", fontsize=6, rotation=90, color=INK)


def holes(part) -> dict[float, int]:
    """圆柱面按半径分组计数（只统计通孔/沉孔，不含圆角）。"""
    out: dict[float, int] = {}
    for f in part.faces():
        if f.geom_type.name != "CYLINDER":
            continue
        try:
            r = round(float(f.radius), 2)
        except (TypeError, ValueError):
            continue
        if r < 0.8 or r > 20:
            continue
        out[r] = out.get(r, 0) + 1
    return out


def _panel(fig, x: float, y: float, w: float, h: float):
    """在页面坐标（mm，左下原点）放一个不画边框的文本面板，并设好数据坐标。"""
    ax = fig.add_axes([x / PAGE[0], y / PAGE[1], w / PAGE[0], h / PAGE[1]])
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.axis("off")
    return ax


def title_block(fig, name: str, cn: str, qty: int, material: str, minutes: str, scale: float):
    x, y, w, h = 190.0, 8.0, 99.0, 34.0
    ax = _panel(fig, x, y, w, h)
    ax.add_patch(Rectangle((0, 0), w, h, fill=False, lw=0.9, color=INK))
    for yy in (10, 20, 28):
        ax.plot([0, w], [yy, yy], color=INK, lw=0.5)
    ax.plot([60, 60], [0, 28], color=INK, lw=0.5)
    rows = [
        (3, 24, "modkit M1 · 移动操作臂", 8, "bold"),
        (3, 15, f"零件：{cn}（{name}）", 7, "normal"),
        (3, 5, f"材料 {material} · 数量 {qty} · 打印 {minutes}", 6, "normal"),
        (63, 24, f"比例 1:{scale:g}", 6, "normal"),
        (63, 15, f"版本 {REV}", 6, "normal"),
        (63, 5, f"单位 mm · {_dt.date.today().isoformat()}", 6, "normal"),
    ]
    for xx, yy, t, fs, wt in rows:
        ax.text(xx, yy, t, fontsize=fs, color=INK, weight=wt, va="bottom")


def notes(fig):
    ax = _panel(fig, 124.0, 152.0, 165.0, 46.0)
    lines = [
        "技术要求",
        "1. FDM/PETG，层高 0.2，4 壁，15% 填充；圆孔不要加支撑。",
        "2. 尺寸公差 ±0.2；配合面 ±0.1；孔径按校准件实测修正。",
        "3. 去毛刺；热熔铜螺母压入后与表面齐平（±0.3）。",
        "4. 未注圆角 R1；未注倒角 0.5×45°。",
        "5. 装配顺序与扭矩见 docs/05-装配手册.md。",
    ]
    for i, t in enumerate(lines):
        ax.text(0, 40 - i * 7, t, fontsize=6.5 if i else 7.5,
                color=INK if i == 0 else GREY, weight="bold" if i == 0 else "normal", va="top")


def hole_panel(fig, part):
    ax = _panel(fig, 194.0, 46.0, 95.0, 100.0)
    hs = holes(part)
    ax.text(0, 94, "孔 / 圆柱面（按直径分组）", fontsize=7.5, weight="bold", color=INK)
    if not hs:
        ax.text(0, 84, "无圆柱孔", fontsize=6.5, color=GREY)
        return
    ytxt = 84
    for r, n in sorted(hs.items(), key=lambda kv: -kv[0])[:8]:
        ax.text(0, ytxt, f"{n} × Ø{r * 2:.1f}   (R{r:.1f})", fontsize=6.5, color=INK)
        ytxt -= 9


def key_dims(fig):
    """关键接口尺寸：这些数字改了整机就装不上，每张图都印。"""
    ax = _panel(fig, 14.0, 8.0, 100.0, 30.0)
    rows = [
        ("关键接口尺寸", ""),
        ("孔网格", f"{P.GRID:g} mm"),
        ("M3 通孔", f"Ø{P.M3_CLR:g}"),
        ("M3 热熔孔", f"Ø{P.M3_INSERT_D:g}×{P.M3_INSERT_H:g}"),
        ("板厚/盖厚", f"{P.PLATE_T:g}/{P.LID_T:g}"),
        ("舵机腔间隙", f"{P.FIT_CLR:g} mm"),
        ("舵机外形", f"{P.SERVO_L:g}×{P.SERVO_W:g}"),
        ("最小壁厚", f"{P.MIN_WALL:g} mm"),
        ("打印床", f"{P.PRINTER_BED[0]:g}×{P.PRINTER_BED[1]:g}"),
    ]
    for i, (k, v) in enumerate(rows):
        col, row = divmod(i, 5)
        x = col * 50.0
        y = 24 - row * 5.6
        ax.text(x, y, k, fontsize=6, color=INK if i == 0 else GREY,
                weight="bold" if i == 0 else "normal")
        if v:
            ax.text(x + 46, y, v, fontsize=6, color=INK, ha="right")


def one_page(pdf, name: str, cn: str, qty: int, material: str, minutes: str):
    part = (K.ALL_PARTS.get(name) or M1.ALL_PARTS_M1.get(name) or T.TOOLS[name])()
    fig = plt.figure(figsize=(PAGE[0] / 25.4, PAGE[1] / 25.4))
    fig.patch.set_facecolor("white")
    fig.text(0.02, 0.975, f"{cn} / {name}", fontsize=9, weight="bold", color=INK)
    fig.text(0.98, 0.975, "modkit · M1 工程图", fontsize=7, ha="right", color=GREY)

    # 版面：左上俯视、左下正视、中下侧视、右上技术要求、右中孔表、右下标题栏
    views = [("xy", "俯视", 14, 116, 102, 82), ("xz", "正视", 14, 40, 102, 74),
             ("yz", "侧视", 124, 40, 62, 74)]
    xy = polylines(part, "xy")
    xz = polylines(part, "xz")
    yz = polylines(part, "yz")
    data = {"xy": xy, "xz": xz, "yz": yz}

    for plane, label, px, py, bw, bh in views:
        lines = data[plane]
        x0, x1, y0, y1 = bounds(lines)
        if (y1 - y0) > (x1 - x0) * 1.15 and bw > bh:
            x0, x1, y0, y1 = y0, y1, x0, x1
        scale = pick_scale(x1 - x0, y1 - y0, bw - 14, bh - 14)
        ax = fig.add_axes([px / PAGE[0], py / PAGE[1], bw / PAGE[0], bh / PAGE[1]])
        xx0, xx1, yy0, yy1, cx, cy = draw_view(ax, lines, label, scale, bw - 8, bh - 8)
        w, h = (xx1 - xx0) / scale, (yy1 - yy0) / scale
        hdim(ax, -w / 2, w / 2, -h / 2 - 4, f"{xx1 - xx0:.1f}")
        vdim(ax, -w / 2 - 4, -h / 2, h / 2, f"{yy1 - yy0:.1f}")

    hole_panel(fig, part)
    title_block(fig, name, cn, qty, material, minutes, scale)
    key_dims(fig)
    notes(fig)
    pdf.savefig(fig)
    if name in ("chassis_right", "joint_base", "camera_mount"):
        fig.savefig(IMG_DIR / f"drawing_{name}.png", dpi=170)
    plt.close(fig)


def cover(pdf):
    fig = plt.figure(figsize=(PAGE[0] / 25.4, PAGE[1] / 25.4))
    fig.patch.set_facecolor("white")
    fig.text(0.06, 0.86, "modkit M1", fontsize=28, weight="bold", color=INK)
    fig.text(0.06, 0.80, "移动操作臂 · 零件工程图", fontsize=15, color=GREY)
    fig.text(0.06, 0.72, f"版本 {REV} · {_dt.date.today().isoformat()} · 单位 mm", fontsize=9, color=GREY)
    body = [
        "这份图纸是给「照着做」用的，不是效果图：",
        "",
        "· 每个零件一页，俯视/正视/侧视三个正投影，等比例",
        "· 总体尺寸从几何实测打印（不是手抄参数）",
        "· 孔按直径分组计数，方便一次买齐钻头/螺丝",
        "· 标题栏给出材料、数量、打印时长、比例",
        "· 技术要求写明层高、壁数、填充与公差",
        "",
        "配合关系与装配顺序见 docs/05-装配手册.md；",
        "尺寸的唯一真源是 cad/params.py，本 PDF 由 cad/drawings.py 自动生成。",
    ]
    for i, t in enumerate(body):
        fig.text(0.06, 0.62 - i * 0.045, t, fontsize=9, color=INK if i % 2 == 0 else GREY)
    fig.text(0.06, 0.06, "github.com/gh503/robot-modkit · MIT", fontsize=8, color=GREY)
    pdf.savefig(fig)
    plt.close(fig)


def main() -> int:
    OUT_PDF.parent.mkdir(parents=True, exist_ok=True)
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    with PdfPages(OUT_PDF) as pdf:
        cover(pdf)
        for name, cn, qty, mat, mins in PARTS:
            one_page(pdf, name, cn, qty, mat, mins)
            print(f"  页 {name}")
        d = pdf.infodict()
        d["Title"] = "modkit M1 零件工程图"
        d["Author"] = "robot-modkit"
        d["Subject"] = "M1 机械件加工图"

    size = OUT_PDF.stat().st_size / 1024
    print(f"\n写出 {OUT_PDF.relative_to(OUT_PDF.parents[2])}  {len(PARTS)+1} 页  {size:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())