# 本地启动后端（无语言依赖，仅依赖 uv）
Set-Location "$PSScriptRoot/backed"
uv run uvicorn start:app --host 0.0.0.0 --port 8000 --reload
