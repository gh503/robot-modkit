#!/usr/bin/env bash
# 启动临时静态服务器 + 无头 Chrome，跑 tools/web-smoke.mjs。
# 用法：bash tools/web-smoke.sh
set -euo pipefail
cd "$(dirname "$0")/.."

WEB_PORT="${MODKIT_WEB_PORT:-8777}"
CDP_PORT="${MODKIT_CDP_PORT:-9222}"
CHROME_BIN="${CHROME_BIN:-$(command -v google-chrome || command -v chromium || command -v chromium-browser || true)}"
if [ -z "$CHROME_BIN" ]; then echo "找不到 Chrome/Chromium；设置 CHROME_BIN" >&2; exit 2; fi
if ! command -v node >/dev/null; then echo "找不到 node" >&2; exit 2; fi

TMP="$(mktemp -d)"
LOG="$TMP/web.log"
CHROME_LOG="$TMP/chrome.log"
SRV_PID=""
CHROME_PID=""
cleanup() {
  [ -n "$SRV_PID" ] && kill "$SRV_PID" 2>/dev/null || true
  [ -n "$CHROME_PID" ] && kill "$CHROME_PID" 2>/dev/null || true
  [ -n "$CHROME_PID" ] && wait "$CHROME_PID" 2>/dev/null || true
  [ -n "$SRV_PID" ] && wait "$SRV_PID" 2>/dev/null || true
  # Chrome 退出时可能还在写 profile；清理失败不能改变测试结果。
  rm -rf "$TMP" 2>/dev/null || true
  return 0
}
trap cleanup EXIT

python3 -m http.server "$WEB_PORT" --bind 127.0.0.1 --directory web >"$LOG" 2>&1 &
SRV_PID=$!
"$CHROME_BIN" --headless=new --no-sandbox --disable-dev-shm-usage \
  --no-first-run --no-default-browser-check \
  --user-data-dir="$TMP/chrome" --remote-debugging-port="$CDP_PORT" \
  --use-angle=swiftshader --enable-unsafe-swiftshader \
  --window-size=1280,900 about:blank >"$CHROME_LOG" 2>&1 &
CHROME_PID=$!

for _ in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:$CDP_PORT/json/version" >/dev/null; then break; fi
  sleep 0.5
done
if ! curl -sf "http://127.0.0.1:$CDP_PORT/json/version" >/dev/null; then
  echo "Chrome CDP 未启动：" >&2
  tail -40 "$CHROME_LOG" >&2 || true
  exit 1
fi

MODKIT_WEB_BASE="http://127.0.0.1:$WEB_PORT" MODKIT_CDP_PORT="$CDP_PORT" node tools/web-smoke.mjs
