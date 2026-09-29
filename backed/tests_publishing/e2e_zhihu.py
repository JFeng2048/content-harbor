# -*- coding: utf-8 -*-
"""知乎适配器 E2E（API 级冒烟）：mock 登录 → check_auth 复核 → 编辑器 UI 发布 → post_id 落库。

前置：python tests/mocks/mock_zhihu.py &     # :9103
用法：python tests/e2e_zhihu.py
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BASE = "http://127.0.0.1:9103"

# patch 必须在 core.service 导入前（注册的实例共享类属性，改类属性即可）
from service.publishing.adapters.zhihu import ZhihuAdapter  # noqa: E402

ZhihuAdapter.login_url = BASE + "/signin"
ZhihuAdapter.home_url = BASE + "/write"
ZhihuAdapter.new_url = BASE + "/write"
ZhihuAdapter.DOMAIN = "127.0.0.1:9103"   # check_auth 的「是否已在平台域」判定

from service.publishing.service import Hub  # noqa: E402

results = []


def step(name, ok, detail=""):
    results.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}   {detail}", flush=True)


hub = Hub(headless=True)

# 1. 登录（mock 自动扫码，内部开有头浏览器）
ok, msg = hub.login("zhihu", timeout=90)
step("1 知乎登录（mock 扫码 → 登录态保存）", ok, msg[:70])

# 2. check_auth 复核
from service.publishing.adapters.base import ADAPTERS  # noqa: E402
from service.publishing.browser import BuiltinBrowser  # noqa: E402

br = BuiltinBrowser("zhihu", "default", headless=True)
try:
    pg = br.new_page()
    ok = ADAPTERS["zhihu"].check_auth(pg)
    step("2 check_auth 复核（复用 profile）", ok is True)
finally:
    br.close()

# 3. 建文章 + 发布（走 mock 编辑器 UI）
aid = hub.create("知乎模拟发布验证", "# 你好知乎\n\n这是 **Markdown** 正文。\n\n- 甲\n- 乙",
                 source="human")
res = hub.publish(aid, ["zhihu"])
r0 = res[0]
ok = r0.get("ok") and r0.get("post_id") == "zz001234"
step("3 发布到模拟知乎 → post_id=zz001234", ok,
     f"post_url={r0.get('post_url','')[:60]} err={r0.get('error','')[:60]}")

# 4. 数据库复核
conn = sqlite3.connect(ROOT / "data" / "hub.db")
row = conn.execute(
    "SELECT status,post_id FROM publications WHERE article_id=? AND platform='zhihu' "
    "ORDER BY id DESC LIMIT 1", (aid,)).fetchone()
art_status = conn.execute("SELECT status FROM articles WHERE id=?", (aid,)).fetchone()[0]
ok = bool(row) and row[0] == "ok" and row[1] == "zz001234" and art_status == "published"
step("4 发布记录落库 + 文章状态 published", ok, f"pub={row} article.status={art_status}")

npass = sum(1 for _, o in results if o)
print(f"\n合计 {npass}/{len(results)} 通过", flush=True)
sys.exit(0 if npass == len(results) else 1)
