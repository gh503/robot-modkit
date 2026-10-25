"""环境自检：装完依赖先跑这个，避免"到第 5 步才发现缺东西"。"""

from __future__ import annotations

import glob
import importlib
import json
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
REQUIRED = ["numpy", "PIL"]
OPTIONAL = ["matplotlib", "serial"]
BINS = ["git", "node", "google-chrome", "arduino-cli"]


def run() -> dict:
    checks = []

    def add(name, ok, detail="", critical=False):
        checks.append({"name": name, "ok": ok, "detail": detail,
                       "critical": critical})

    add("Python ≥3.10", sys.version_info >= (3, 10),
        sys.version.split()[0], True)
    add("虚拟环境", sys.prefix != getattr(sys, "base_prefix", sys.prefix),
        sys.prefix)
    add("仓库根目录", (ROOT / "software" / "modkit").is_dir(), str(ROOT), True)
    for m in REQUIRED:
        try:
            importlib.import_module(m)
            add(f"依赖 {m}", True)
        except Exception as e:
            add(f"依赖 {m}", False, str(e), True)
    for m in OPTIONAL:
        try:
            importlib.import_module(m)
            add(f"可选 {m}", True)
        except Exception:
            add(f"可选 {m}", False, "未装（画图/串口会跳过）")
    for b in BINS:
        found = shutil.which(b)
        if b == "arduino-cli" and not found:
            local = ROOT / "tools" / "arduino-cli"
            found = str(local) if local.exists() else None
        add(f"命令 {b}", found is not None, found or "未找到（可选）")
    ports = sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))
    add("串口设备", bool(ports), ", ".join(ports) or "未发现（没接硬件时可忽略）")
    return {"ok": all(c["ok"] for c in checks if c["critical"]),
            "checks": checks}


def main(as_json: bool = False) -> int:
    r = run()
    if as_json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        for c in r["checks"]:
            mark = "OK  " if c["ok"] else ("FAIL" if c["critical"] else "WARN")
            print(f"[{mark}] {c['name']}  {c['detail']}")
        print("\n结论：" + ("可以开始" if r["ok"] else "先修 FAIL 项"))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main("--json" in sys.argv))
