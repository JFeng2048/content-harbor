@echo off
rem 本地启动后端（无语言依赖，仅依赖 uv）
cd /d "%~dp0backed"
uv run uvicorn start:app --host 0.0.0.0 --port 8000 --reload
