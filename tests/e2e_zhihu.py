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
from core.adapters.zhihu import ZhihuAdapter  # noqa: E402

ZhihuAdapter.login_url = BASE + "/signin"
ZhihuAdapter.home_url = BASE + "/write"
ZhihuAdapter.new_url = BASE + "/write"
ZhihuAdapter.me_api = BASE + "/api/v4/me"
ZhihuAdapter.DOMAIN = "127.0.0.1:9103"  # check_auth 的「是否已在平台域」判定

from core.service import Hub  # noqa: E402

results = []


def step(name, ok, detail=""):
    results.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}   {detail}", flush=True)


hub = Hub(headless=True)

# 1. 登录（mock 自动扫码，内部开有头浏览器）
ok, msg = hub.login("zhihu", timeout=90)
step("1 知乎登录（mock 扫码 → 登录态保存）", ok, msg[:70])

# 2. check_auth 复核
from core.adapters.base import ADAPTERS  # noqa: E402
from core.browser import BuiltinBrowser, browser_thread_run  # noqa: E402


def _recheck():
    br = BuiltinBrowser("zhihu", "default", headless=True)
    try:
        pg = br.new_page()
        pg.goto(BASE + "/write", timeout=30000, wait_until="domcontentloaded")
        return ADAPTERS["zhihu"].check_auth(pg)
    finally:
        br.close()


try:
    ok = browser_thread_run(_recheck)
    step("2 check_auth 复核（复用 profile）", ok is True)
# aqg: top-level boundary（测试步骤隔离：复核失败不中断后续步骤）
except Exception as e:
    step("2 check_auth 复核（复用 profile）", False, str(e)[:70])

# 3. 建文章 + 发布（走 mock 编辑器 UI；正文 ≥200 字过本地内容审查门禁）
aid = hub.create(
    "知乎模拟发布验证",
    "# 知乎模拟发布验证\n\n这是端到端验证文章，正文使用 Markdown 书写，"
    "包含标题、段落与列表，用来确认知乎适配器的登录、编辑器注入与发布链路"
    "均能正常工作，并且发布记录会真实写入数据库。\n\n"
    "- 第一项：登录状态复用\n- 第二项：编辑器内容注入\n- 第三项：发布结果落库\n\n"
    "完成发布后，数据库中应当能查到平台返回的文章编号与成功状态，"
    "任务记录与发布实例都会留下本次操作的痕迹，方便复核与后续的"
    "原地更新；若发布失败，失败原因也会写进任务记录里。",
    source="human",
)
res = hub.publish(aid, ["zhihu"])
r0 = res[0]
ok = r0.get("ok") and r0.get("post_id") == "zz001234"
step(
    "3 发布到模拟知乎 → post_id=zz001234",
    ok,
    f"post_url={r0.get('post_url', '')[:60]} err={r0.get('error', '')[:60]}",
)

# 4. 数据库复核
conn = sqlite3.connect(ROOT / "data" / "hub.db")
row = conn.execute(
    "SELECT status,post_id FROM publications WHERE article_id=? AND platform='zhihu' "
    "ORDER BY id DESC LIMIT 1",
    (aid,),
).fetchone()
art_status = conn.execute("SELECT status FROM articles WHERE id=?", (aid,)).fetchone()[
    0
]
ok = bool(row) and row[0] == "ok" and row[1] == "zz001234" and art_status == "published"
step(
    "4 发布记录落库 + 文章状态 published", ok, f"pub={row} article.status={art_status}"
)

npass = sum(1 for _, o in results if o)
print(f"\n合计 {npass}/{len(results)} 通过", flush=True)
sys.exit(0 if npass == len(results) else 1)
