# -*- coding: utf-8 -*-
"""把掘金适配器指向本机模拟平台，再启动 Web 服务（8800）。

patch 必须发生在 server.api 导入之前（api.py → hub → service → adapters）。
用法：python tests/run_patched_server.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BASE = "http://127.0.0.1:9102"

import service.publishing.adapters.juejin as jj  # noqa: E402

jj.API = BASE + "/api"  # 模块级常量，check_auth/publish 都引用它

from service.publishing.adapters.juejin import JuejinAdapter  # noqa: E402

JuejinAdapter.login_url = BASE + "/login"
JuejinAdapter.home_url = BASE + "/creator/home"
JuejinAdapter.list_url = BASE + "/creator/content/article"
JuejinAdapter.new_url = BASE + "/editor/drafts/new"
JuejinAdapter.editor_url = BASE + "/editor/drafts/{draft_id}"

print(f"[patched] juejin 适配器 -> {BASE}", flush=True)

import uvicorn  # noqa: E402
from api.hub import app  # noqa: E402

uvicorn.run(app, host="127.0.0.1", port=8800, log_level="warning")
