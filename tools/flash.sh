#!/usr/bin/env bash
# 烧录一台：编译 → 上传 → 记录版本到记录文件
# 用法：tools/flash.sh [端口] [记录文件]
set -euo pipefail
PORT="${1:-/dev/ttyACM0}"
REC="${2:-}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ACLI="$ROOT/tools/arduino-cli"
FQBN="esp32:esp32:esp32s3"
SKETCH="$ROOT/firmware/esp32/modkit_esp32"

VER="$(git -C "$ROOT" describe --tags --always --dirty 2>/dev/null || echo unknown)"
echo "固件版本：$VER"

"$ACLI" compile --fqbn "$FQBN" "$SKETCH"
"$ACLI" upload --fqbn "$FQBN" -p "$PORT" "$SKETCH"

if [[ -n "$REC" && -f "$REC" ]]; then
  python3 - "$REC" "$VER" <<'PY'
import json, sys
path, ver = sys.argv[1], sys.argv[2]
d = json.load(open(path, encoding="utf-8"))
d["firmware_version"] = ver
json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"已把固件版本写入 {path}")
PY
fi
echo "烧录完成。下一步：modkit --port ... scan，确认 6 个 ID 都在。"
