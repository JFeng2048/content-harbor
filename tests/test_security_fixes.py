# -*- coding: utf-8 -*-
"""Option-A 修复回归测试（Behavior Lock）。

覆盖 Behavior Contract R1-R6：XFF 信任边界 / logout 路径穿越 / import 文件面 /
assist URL 与平台收敛 / update+sync 合规门禁 / MCP 可导入。

隔离约束（不依赖外部服务、不开浏览器）：
  1. DEMO=1：演示模式，登录/发布/更新/assist 均不真开浏览器、不调外网；
  2. 导入 server.api 前把 core.db.DB_PATH 指向临时库——避免测试进程的
     TaskManager 偷走真实 data/hub.db 里排队的任务；
  3. 零新增依赖：仅用 unittest + starlette Request 手工构造 scope。
"""

import atexit
import importlib
import os
import shutil
import sys
import tempfile
import unittest
from ipaddress import ip_address
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ["DEMO"] = "1"

import core.db as _db

_TMP = Path(tempfile.mkdtemp(prefix="hub_testdb_"))
_db.DB_PATH = _TMP / "hub_test.db"
atexit.register(lambda: shutil.rmtree(_TMP, ignore_errors=True))

from fastapi import HTTPException
from starlette.requests import Request

import server.api as api
from core.adapters.base import PlatformError
from core.service import Hub

# 高危词取自 core/gate.py DANGEROUS_PATTERNS
DANGEROUS_MD = "开篇正常。此处演示高危内容拦截：毒品制造。\n" + "后面补齐篇幅。" * 30
SAFE_MD = (
    "这是一段用于回归测试的安全正文，讲述如何整理笔记、排期发布与渠道分发，"
    "不涉及任何高危主题，用于通过本地 heuristic 审查。"
) * 4


def make_request(client_ip, xff=None):
    headers = []
    if xff:
        headers.append((b"x-forwarded-for", xff.encode()))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": (client_ip, 40000),
        "server": ("127.0.0.1", 8800),
    }
    return Request(scope)


class TestXffTrust(unittest.TestCase):
    """R1: XFF 仅在直连对端受信时采信。"""

    def setUp(self):
        self._saved = os.environ.get("TRUSTED_NETS")
        os.environ.pop("TRUSTED_NETS", None)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("TRUSTED_NETS", None)
        else:
            os.environ["TRUSTED_NETS"] = self._saved

    def test_untrusted_peer_xff_ignored(self):
        req = make_request("203.0.113.9", xff="127.0.0.1")
        self.assertEqual(api._client_ip(req), ip_address("203.0.113.9"))
        self.assertFalse(api._is_trusted(req))

    def test_loopback_direct_is_trusted(self):
        req = make_request("127.0.0.1")
        self.assertTrue(api._is_trusted(req))

    def test_trusted_proxy_xff_honored(self):
        os.environ["TRUSTED_NETS"] = "198.51.100.0/24"
        req = make_request("198.51.100.7", xff="203.0.113.5")
        self.assertEqual(api._client_ip(req), ip_address("203.0.113.5"))
        self.assertFalse(api._is_trusted(req))


class TestApiFixes(unittest.TestCase):
    """R2/R4 的 API 层表现。"""

    def test_logout_unknown_platform_is_404(self):
        with self.assertRaises(HTTPException) as cm:
            api.logout("../..")
        self.assertEqual(cm.exception.status_code, 404)

    def test_assist_rejects_link_local_url(self):
        with mock.patch.object(api.hub.tasks, "submit", return_value="t-fake") as sub:
            with self.assertRaises(HTTPException) as cm:
                api.assist_open(
                    "juejin",
                    api.AssistIn(url="http://169.254.169.254/latest/meta-data"),
                )
            self.assertEqual(cm.exception.status_code, 422)
            sub.assert_not_called()

    def test_assist_rejects_file_scheme(self):
        with mock.patch.object(api.hub.tasks, "submit", return_value="t-fake") as sub:
            with self.assertRaises(HTTPException) as cm:
                api.assist_open("juejin", api.AssistIn(url="file:///etc/passwd"))
            self.assertEqual(cm.exception.status_code, 422)
            sub.assert_not_called()

    def test_assist_rejects_localhost(self):
        with mock.patch.object(api.hub.tasks, "submit", return_value="t-fake") as sub:
            with self.assertRaises(HTTPException) as cm:
                api.assist_open("juejin", api.AssistIn(url="http://localhost:8800/x"))
            self.assertEqual(cm.exception.status_code, 422)
            sub.assert_not_called()

    def test_assist_unknown_platform_is_404(self):
        with mock.patch.object(api.hub.tasks, "submit", return_value="t-fake") as sub:
            with self.assertRaises(HTTPException) as cm:
                api.assist_open("../evil", api.AssistIn(url="https://example.com/p"))
            self.assertEqual(cm.exception.status_code, 404)
            sub.assert_not_called()


class ServiceFixtures(unittest.TestCase):
    """共享演示模式 Hub（连临时库）。"""

    @classmethod
    def setUpClass(cls):
        os.environ["DEMO"] = "1"
        cls.hub = Hub(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.hub.tasks.close()


class TestLogoutService(ServiceFixtures):
    """R2 的 service 层表现。"""

    def test_service_logout_rejects_path_separators(self):
        for bad in ("../../evil", "..\\..\\evil", "a/b"):
            with self.subTest(platform=bad):
                with self.assertRaises(ValueError):
                    self.hub.logout(bad)


class TestImportRestriction(ServiceFixtures):
    """R3: import_md 文件面收敛。"""

    def test_reject_config_json(self):
        with self.assertRaises(ValueError):
            self.hub.import_md(str(ROOT / "config.json"))

    def test_reject_outside_root(self):
        outside = _TMP / "outside.md"
        outside.write_text("任意机器文件", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.hub.import_md(str(outside))

    def test_accept_md_inside_root(self):
        target = ROOT / "tests" / "_tmp_import_lock.md"
        target.write_text(
            "# 临时导入测试\n\n合法的 Markdown 内容。\n", encoding="utf-8"
        )
        try:
            aid = self.hub.import_md(str(target))
            self.assertIsInstance(aid, int)
        finally:
            target.unlink(missing_ok=True)


class TestAssistService(ServiceFixtures):
    """R4 的 service 层表现（worker 路径兜底）。"""

    def test_service_rejects_unknown_platform(self):
        with self.assertRaises(PlatformError):
            self.hub.assist_open("evil", "https://example.com/p")


class TestGateUpdate(ServiceFixtures):
    """R5: update / sync_pending 强制合规门禁。"""

    def _mk_article(self, content, status, pub_status):
        aid = self.hub.create("门禁回归测试", content, source="human")
        _db.upsert_publication(
            self.hub.conn,
            aid,
            "juejin",
            "default",
            status=pub_status,
            post_id=f"art-{aid}",
            content_hash="deadbeef",
            draft_only=0,
        )
        return aid

    def test_update_rejects_dangerous_content(self):
        aid = self._mk_article(DANGEROUS_MD, "ok", "ok")
        with self.assertRaises(HTTPException) as cm:
            self.hub.update(aid)
        self.assertEqual(cm.exception.status_code, 422)
        self.assertIn("合规门禁", str(cm.exception.detail))

    def test_update_allows_safe_content(self):
        aid = self._mk_article(SAFE_MD, "ok", "ok")
        rows = self.hub.update(aid)
        self.assertIsInstance(rows, list)
        self.assertTrue(rows and rows[0].get("ok"))

    def test_sync_isolates_gated_article(self):
        bad = self._mk_article(DANGEROUS_MD, "pending", "pending")
        good = self._mk_article(SAFE_MD, "pending", "pending")
        out = {e["article_id"]: e for e in self.hub.sync_pending()}
        self.assertIn("合规门禁", out[bad].get("error", ""))
        self.assertNotIn("error", out[good])
        self.assertTrue(out[good].get("result"))


class TestMcpImport(unittest.TestCase):
    """R6: server.mcp_server 可导入。"""

    def test_mcp_server_importable(self):
        mod = importlib.import_module("server.mcp_server")
        self.assertTrue(hasattr(mod, "mcp"))


if __name__ == "__main__":
    unittest.main()
