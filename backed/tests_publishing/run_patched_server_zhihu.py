# -*- coding: utf-8 -*-
"""把知乎适配器指向本机模拟平台，再启动 Web 服务（8800）。

知乎适配器走 UI 发布（编辑器注入 + 点发布），mock 提供 /signin + /write 编辑器
（标题 textarea + Draft.js data-contents）+ /mock/publish → 跳 /p/zz001234。

patch 必须发生在 server.api 导入之前。用法：python tests/run_patched_server_zhihu.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BASE = "http://127.0.0.1:9103"

from service.publishing.adapters.zhihu import ZhihuAdapter  # noqa: E402

ZhihuAdapter.login_url = BASE + "/signin"
ZhihuAdapter.home_url = BASE + "/write"
ZhihuAdapter.new_url = BASE + "/write"
ZhihuAdapter.me_api = BASE + "/api/v4/me"
ZhihuAdapter.DOMAIN = "127.0.0.1:9103"  # check_auth 的「是否已在平台域」判定

print(f"[patched] zhihu 适配器 -> {BASE}", flush=True)

import uvicorn  # noqa: E402
from api.hub import app  # noqa: E402

uvicorn.run(app, host="127.0.0.1", port=8800, log_level="warning")
