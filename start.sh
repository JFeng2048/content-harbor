#!/usr/bin/env bash
# 本地启动后端（无语言依赖，仅依赖 uv）
set -e
cd "$(dirname "$0")/backed"
exec uv run uvicorn start:app --host 0.0.0.0 --port 8000 --reload
