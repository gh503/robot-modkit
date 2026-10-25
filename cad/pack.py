"""按数量真实排板：把 N 套零件按包围盒装进 220×220，导出可打印 STL。

和 plate.py 的区别：plate.py 的 A/B/C 是旧版"一套"固定手排（只有 13 个唯一件）；
这里按 manufacturing.json 的 qty 展开全部件，按套数重排并断言件数/重叠。

用法：
  cd cad && ../.venv/bin/python pack.py --copies 3
产物：
  cad/out/batch/3/plate_01.stl ...
  cad/out/batch/3/plan.json
"""

from __future__ import annotations

import json
import math
import pathlib

import params as P
import trimesh

OUT = pathlib.Path(__file__).parent / "out"
GAP = 4.0
MARGIN = 5.0


def _pieces(copies: int):
    mfg = json.loads((OUT / "manufacturing.json").read_text(encoding="utf-8"))
    out = []
    for name, m in mfg.items():
        if m.get("tooling"):
            continue
        for i in range(m["qty"] * copies):
            out.append((name, float(m["bbox"][0]), float(m["bbox"][1]), i))
    # 大件先放，减少碎片
    out.sort(key=lambda p: max(p[1], p[2]), reverse=True)
    return out


def _split_free(free, px, py, pw, ph):
    """从空闲矩形里扣掉已放件，返回不与它重叠的剩余矩形。"""
    out = []
    for x, y, w, h in free:
        if px >= x + w or px + pw <= x or py >= y + h or py + ph <= y:
            out.append((x, y, w, h))
            continue
        # 左右两条通高，中间上下两块，互不重叠
        if px > x:
            out.append((x, y, px - x, h))
        if px + pw < x + w:
            out.append((px + pw, y, x + w - (px + pw), h))
        if py > y:
            out.append((px, y, pw, py - y))
        if py + ph < y + h:
            out.append((px, py + ph, pw, y + h - (py + ph)))
    # 去掉被包含的碎片
    keep = []
    for a in out:
        ax, ay, aw, ah = a
        if aw < 1 or ah < 1:
            continue
        contained = False
        for b in out:
            if a is b:
                continue
            bx, by, bw, bh = b
            if (ax >= bx - 1e-9 and ay >= by - 1e-9 and
                    ax + aw <= bx + bw + 1e-9 and ay + ah <= by + bh + 1e-9):
                if (aw * ah < bw * bh) or (a > b and aw * ah == bw * bh):
                    contained = True
                    break
        if not contained:
            keep.append(a)
    return keep


def _pack_order(pieces, bed_x, bed_y):
    beds: list[dict] = []
    for name, w0, h0, idx in pieces:
        best = None
        for bi, bed in enumerate(beds):
            for rot in (0, 90):
                w, h = (w0, h0) if rot == 0 else (h0, w0)
                need_w, need_h = w + GAP, h + GAP
                for fx, fy, fw, fh in bed["free"]:
                    if need_w <= fw + 1e-9 and need_h <= fh + 1e-9:
                        score = (fw - need_w) * (fh - need_h)
                        if best is None or score < best[0]:
                            best = (score, bi, rot, w, h, fx, fy)
        if best is None:
            beds.append({"free": [(MARGIN, MARGIN, bed_x - 2 * MARGIN,
                                   bed_y - 2 * MARGIN)], "items": []})
            bi = len(beds) - 1
            rot = 0
            w, h = w0, h0
            if w + GAP > bed_x - 2 * MARGIN or h + GAP > bed_y - 2 * MARGIN:
                rot = 90
                w, h = h0, w0
            if w + GAP > bed_x - 2 * MARGIN or h + GAP > bed_y - 2 * MARGIN:
                return None
            fx, fy = MARGIN, MARGIN
        else:
            _, bi, rot, w, h, fx, fy = best
        bed = beds[bi]
        bed["free"] = _split_free(bed["free"], fx, fy, w + GAP, h + GAP)
        bed["items"].append({"part": name, "copy": idx, "x": fx, "y": fy,
                             "w": w, "h": h, "rot": rot})
    return beds


def build_plan(copies: int) -> dict:
    import random
    bed_x, bed_y, _ = P.PRINTER_BED
    pieces = _pieces(copies)
    orders = [
        sorted(pieces, key=lambda p: p[1] * p[2], reverse=True),
        sorted(pieces, key=lambda p: max(p[1], p[2]), reverse=True),
        sorted(pieces, key=lambda p: p[2], reverse=True),
        sorted(pieces, key=lambda p: p[1], reverse=True),
    ]
    rng = random.Random(0)
    for _ in range(12):
        q = pieces[:]
        rng.shuffle(q)
        orders.append(q)

    best_beds, best_key = None, None
    for order in orders:
        beds = _pack_order(order, bed_x, bed_y)
        if beds is None:
            continue
        area = sum(i["w"] * i["h"] for b in beds for i in b["items"])
        key = (len(beds), -area)
        if best_key is None or key < best_key:
            best_beds, best_key = beds, key
    if best_beds is None:
        raise SystemExit("排不下：检查零件包围盒")

    for b in best_beds:
        b.pop("free", None)
        for it in b["items"]:
            assert it["x"] >= MARGIN - 1e-9 and it["y"] >= MARGIN - 1e-9
            assert it["x"] + it["w"] <= bed_x - MARGIN + 1e-9
            assert it["y"] + it["h"] <= bed_y - MARGIN + 1e-9
        for i, a in enumerate(b["items"]):
            for c in b["items"][i + 1:]:
                assert not (a["x"] < c["x"] + c["w"] and c["x"] < a["x"] + a["w"] and
                            a["y"] < c["y"] + c["h"] and c["y"] < a["y"] + a["h"]), \
                    f"{a['part']} 与 {c['part']} 重叠"

    area = sum(i["w"] * i["h"] for b in best_beds for i in b["items"])
    bed_area = bed_x * bed_y
    return {"copies": copies, "plates": len(best_beds), "bed_mm": [bed_x, bed_y],
            "gap_mm": GAP, "area_cm2": round(area / 100, 1),
            "utilization": round(area / (max(1, len(best_beds)) * bed_area) * 100, 1),
            "beds": best_beds, "strategy": "maxrects"}


def export(plan: dict, outdir: pathlib.Path) -> list[pathlib.Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    paths = []
    for n, bed in enumerate(plan["beds"], 1):
        scene = []
        for it in bed["items"]:
            src = OUT / f"{it['part']}.stl"
            mesh = trimesh.load(src)
            if it["rot"]:
                mesh.apply_transform(trimesh.transformations.rotation_matrix(
                    math.pi / 2, [0, 0, 1]))
            lo = mesh.bounds[0]
            mesh.apply_translation([it["x"] - lo[0], it["y"] - lo[1], -lo[2]])
            scene.append(mesh)
        merged = trimesh.util.concatenate(scene)
        path = outdir / f"plate_{n:02d}.stl"
        merged.export(path)
        paths.append(path)
    (outdir / "plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return paths


def main(copies: int = 1, outdir: pathlib.Path | None = None) -> int:
    plan = build_plan(copies)
    total = sum(len(b['items']) for b in plan['beds'])
    mfg = json.loads((OUT / "manufacturing.json").read_text(encoding="utf-8"))
    expected = sum(m["qty"] for m in mfg.values() if not m.get("tooling")) * copies
    assert total == expected, f"排板件数 {total} != 应有 {expected}"
    outdir = outdir or (OUT / "batch" / str(copies))
    paths = export(plan, outdir)
    print(f"{copies} 套：{total} 件 → {plan['plates']} 张板"
          f"（{plan.get('strategy','?')}），利用率 {plan['utilization']}%")
    for p in paths:
        print(f"  {p}")
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--copies", type=int, default=1)
    ap.add_argument("--out")
    a = ap.parse_args()
    raise SystemExit(main(a.copies, pathlib.Path(a.out) if a.out else None))
