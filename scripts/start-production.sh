#!/usr/bin/env bash
set -euo pipefail

export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8080}"
export VIDEO_BACKEND_URL="${VIDEO_BACKEND_URL:-http://127.0.0.1:8000}"
export DATABASE_URL="${DATABASE_URL:-sqlite:////data/cookclip.db}"
export LOCAL_STORAGE_ROOT="${LOCAL_STORAGE_ROOT:-/data/storage}"
python_bin="${PYTHON_BIN:-python}"

mkdir -p "$LOCAL_STORAGE_ROOT"

# bgutil POT 提供器（BotGuard token，yt-dlp 插件从 http://127.0.0.1:4416 取）。
# 没有它，机房 IP 上的 mweb 客户端拿不到可下载的媒体流。
pot_pid=""
pot_server="/opt/bgutil-ytdlp-pot-provider-2.0.1/server/build/main.js"
if [ -f "$pot_server" ]; then
  node "$pot_server" &
  pot_pid=$!
fi

"$python_bin" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 &
backend_pid=$!

node frontend/server.cjs &
frontend_pid=$!

cleanup() {
  kill "$backend_pid" "$frontend_pid" ${pot_pid:+"$pot_pid"} 2>/dev/null || true
  wait "$backend_pid" "$frontend_pid" ${pot_pid:+"$pot_pid"} 2>/dev/null || true
}
trap cleanup EXIT INT TERM

while kill -0 "$backend_pid" 2>/dev/null && kill -0 "$frontend_pid" 2>/dev/null; do
  sleep 1
done

status=0
if ! kill -0 "$backend_pid" 2>/dev/null; then
  wait "$backend_pid" || status=$?
else
  wait "$frontend_pid" || status=$?
fi
exit "$status"
