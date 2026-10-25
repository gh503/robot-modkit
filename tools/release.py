#!/usr/bin/env python3
"""打 vX.Y.Z 发布包：production / cad / web / render + SHA256SUMS。

只做文件收集与压缩，不创建 git tag、不调 GitHub API；发版仍由人确认。
用法：
    python tools/release.py --version 1.2.0 --out dist
    python tools/release.py --check --out dist
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import shutil
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
LEGACY_PLATES = {"plate_A.stl", "plate_B.stl", "plate_C.stl"}


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_zip(target: pathlib.Path, files: list[pathlib.Path], prefix: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for src in sorted(files):
            arc = pathlib.Path(prefix) / src.relative_to(ROOT)
            z.write(src, arc.as_posix())


def collect() -> dict[str, list[pathlib.Path]]:
    prod = [ROOT / n for n in ("README.md", "CHANGELOG.md", "CITATION.cff",
                               "LICENSE", "Makefile")]
    prod += sorted((ROOT / "docs").rglob("*.md"))
    prod += sorted((ROOT / "docs" / "drawings").glob("*.pdf"))
    prod += sorted((ROOT / "docs" / "images").glob("*.png"))
    prod += sorted((ROOT / "hardware").glob("*.json"))
    prod += sorted((ROOT / "tools").glob("*.py"))

    cad_dir = ROOT / "cad" / "out"
    cad = [p for p in sorted(cad_dir.glob("*"))
           if p.suffix in (".step", ".stl") and p.name not in LEGACY_PLATES]
    cad += [cad_dir / "plan.json", cad_dir / "manufacturing.json"]
    cad = [p for p in cad if p.exists()]

    web = [p for p in sorted((ROOT / "web").rglob("*")) if p.is_file()]
    render = [p for p in sorted((ROOT / "sim" / "out").glob("*"))
              if p.suffix in (".png", ".gif")]
    return {"production": prod, "cad": cad, "web": web, "render": render}


def build(version: str, out: pathlib.Path) -> list[pathlib.Path]:
    out.mkdir(parents=True, exist_ok=True)
    zips = []
    for name, files in collect().items():
        if not files:
            print(f"  ! {name} 没有文件，跳过", file=sys.stderr)
            continue
        target = out / f"modkit-v{version}-{name}.zip"
        write_zip(target, files, name)
        zips.append(target)
        print(f"  {target.name}: {len(files)} files, {target.stat().st_size / 1e6:.1f} MB")
    sums = out / "SHA256SUMS"
    sums.write_text("".join(f"{sha256(p)}  {p.name}\n" for p in zips), encoding="utf-8")
    print(f"  {sums.name}")
    return zips


def check(out: pathlib.Path) -> int:
    sums = out / "SHA256SUMS"
    if not sums.exists():
        print(f"没有 {sums}", file=sys.stderr)
        return 1
    bad = 0
    for line in sums.read_text(encoding="utf-8").splitlines():
        want, name = line.split("  ", 1)
        p = out / name
        got = sha256(p) if p.exists() else ""
        if got != want:
            print(f"FAIL {name}")
            bad += 1
        else:
            print(f"OK   {name}")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", help="如 1.2.0")
    ap.add_argument("--out", default="dist")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    if a.check:
        return check(out)
    if not a.version:
        ap.error("--version 必填（除非 --check）")
    print(f"打 modkit v{a.version} → {out}")
    build(a.version, out)
    print("完成；下一步人工确认后 git tag / gh release create。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
