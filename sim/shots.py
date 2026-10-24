"""用无头 Chrome + three.js 出一套高质量图（比 matplotlib 好看得多）。

    cd sim && ../.venv/bin/python shots.py

产物（同时写 sim/out 与 docs/images）：
    hero.png            首页主图
    robot_views.png     四视图拼图（轴测/正视/侧视/俯视）
    exploded.png        爆炸图（每个零件沿装配方向拉开）
    arm_grasp.gif       抓取动画（41 帧）
    arm_grasp_sheet.png 关键帧拼图

依赖：本机装了 Chrome/Chromium；没有就退回 matplotlib 的 draw.py（CI 用那条路）。
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
WEB = ROOT / "web"
OUT = HERE / "out"
DOCS = ROOT / "docs" / "images"
OUT.mkdir(exist_ok=True)
DOCS.mkdir(exist_ok=True)

CHROME = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
if not CHROME:
    sys.exit("没找到 Chrome/Chromium：改用 `python draw.py`（matplotlib 版）")

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]


def font(size: int):
    for f in FONT_CANDIDATES:
        if pathlib.Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def shot(view: str, out: pathlib.Path, w: int = 1500, h: int = 1125, **kw) -> pathlib.Path:
    params = f"view={view}&w={w}&h={h}"
    for k, v in kw.items():
        params += f"&{k}={v}"
    url = f"file://{WEB}/poster.html?{params}"
    with tempfile.TemporaryDirectory() as td:
        profile = pathlib.Path(td) / "p"
        cmd = [
            CHROME, "--headless=new", "--disable-gpu", "--enable-unsafe-swiftshader",
            "--use-gl=swiftshader", "--no-sandbox", "--hide-scrollbars",
            f"--user-data-dir={profile}",
            f"--window-size={w},{h}", "--virtual-time-budget=4000",
            f"--screenshot={out}", url,
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=120)
        if r.returncode != 0 or not out.exists():
            raise RuntimeError(f"渲染失败 {view}: {r.stderr.decode()[-300:]}")
    im = Image.open(out).convert("RGB")
    if im.size != (w, h):
        raise RuntimeError(f"{out.name} 尺寸 {im.size} ≠ 期望 {(w, h)}")
    return out


def label_strip(im: Image.Image, title: str, height: int = 54) -> Image.Image:
    canvas = Image.new("RGB", (im.width, im.height + height), "white")
    canvas.paste(im, (0, height))
    d = ImageDraw.Draw(canvas)
    d.text((18, 14), title, fill="#1f2933", font=font(24))
    return canvas


def sheet(files: list[tuple[pathlib.Path, str]], cols: int, out: pathlib.Path,
          title: str, pad: int = 10, tile_w: int = 480) -> pathlib.Path:
    tiles = []
    for f, t in files:
        im = Image.open(f).convert("RGB")
        if im.width > tile_w:
            im = im.resize((tile_w, round(im.height * tile_w / im.width)), Image.LANCZOS)
        tiles.append(label_strip(im, t))
    tw, th = tiles[0].size
    rows = (len(tiles) + cols - 1) // cols
    head = 58
    canvas = Image.new("RGB", (cols * tw + (cols + 1) * pad, head + rows * th + (rows + 1) * pad), "white")
    d = ImageDraw.Draw(canvas)
    d.text((pad + 6, 16), title, fill="#1f2933", font=font(28))
    for i, t in enumerate(tiles):
        x = pad + (i % cols) * (tw + pad)
        y = head + pad + (i // cols) * (th + pad)
        canvas.paste(t, (x, y))
    canvas.save(out)
    return out


def render_stills():
    print("· 主图")
    hero = shot("hero", OUT / "hero.png", 1600, 1200, bg="studio")
    Image.open(hero).save(DOCS / "hero.png")

    print("· 四视图")
    files = []
    for v, name in [("iso", "轴测"), ("front", "正视"), ("side", "侧视"), ("top", "俯视")]:
        p = shot(v, OUT / f"view_{v}.png", 1000, 750, bg="studio", grid="1")
        files.append((p, name))
    v = sheet(files, 2, OUT / "robot_views.png",
              "modkit M1 · 整机四视图（尺寸来自 cad/params.py）")
    Image.open(v).save(DOCS / "robot_views.png")

    print("· 爆炸图")
    e = shot("explode", OUT / "exploded.png", 1600, 1300, explode="1", bg="studio", grid="1")
    Image.open(e).save(DOCS / "exploded.png")


def render_gif():
    print("· 抓取动画（30 帧）")
    frames = []
    n, t_end = 30, 10.4
    for i in range(n):
        t = t_end * i / (n - 1)
        p = shot("hero", OUT / f"f{i:03d}.png", 720, 540, t=f"{t:.2f}", bg="studio", grid="1")
        frames.append(Image.open(p).convert("RGB").quantize(colors=96, method=Image.MEDIANCUT))
        print(f"\r  帧 {i+1}/{n}", end="", flush=True)
    print()

    gif = OUT / "arm_grasp.gif"
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=95,
                   loop=0, optimize=True, disposal=2)
    print(f"  {gif.name}  {n} 帧  {gif.stat().st_size/1024:.0f} KB")

    print("· 关键帧拼图")
    picks = [0, 4, 8, 12, 16, 20, 24, 29]
    kv = [(OUT / f"f{i:03d}.png", f"t={t_end * i / (n - 1):.1f}s")
          for i in picks if (OUT / f"f{i:03d}.png").exists()]
    if kv:
        s = sheet(kv, 4, OUT / "arm_grasp_sheet.png", "抓取流程关键帧", tile_w=420)
        Image.open(s).save(DOCS / "arm_grasp_sheet.png")

    for p in OUT.glob("f[0-9][0-9][0-9].png"):
        p.unlink()


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else "all"
    if only in ("all", "stills"):
        render_stills()
    if only in ("all", "gif"):
        render_gif()

    print("\n写出：")
    for f in sorted(OUT.glob("*.png")) + sorted(OUT.glob("*.gif")):
        print(f"  {f.name:24s} {f.stat().st_size/1024:6.0f} KB")


if __name__ == "__main__":
    main()
