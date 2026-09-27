# -*- coding: utf-8 -*-
"""发布链路两个真实故障的回归测试（Behavior Lock）。

覆盖 Behavior Contract R1-R3：
  R1 api_post 判定  —— 2xx（201/202）且带业务 id 的响应必须算成功；
                       只有非 2xx 或 err_no 非 0 才算失败
  R2 浏览器通道      —— HUB_BROWSER_CHANNEL=msedge 时必须解析到系统 Edge 可执行
                       文件；未设置时保持原行为（不覆盖既有 executable_path 逻辑）
  R3 知乎发布判定    —— 点完发布后停在 /p/<id>/edit 或通用 /write 都必须判失败
                       （假 page 驱动真实分支，不做源码字符串断言）

隔离约束：零外网（api_post 用假 page.evaluate）、零浏览器启动（只测纯解析函数）。
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.adapters.base import PlatformAdapter, PlatformError
from core import browser as browser_mod


class _Resp:
    def __init__(self, status, text):
        self.status = status
        self.text = text


class _FakePage:
    """只实现 api_post 用到的 page.evaluate(js, arg)。"""

    def __init__(self, status, text):
        self._status = status
        self._text = text

    def evaluate(self, js, arg=None):
        return {"status": self._status, "text": self._text}


class ApiPostStatusTests(unittest.TestCase):
    def test_201_with_id_is_success(self):
        """R1 思否建草稿返回 201 + id，旧实现按 200 判定误报失败。"""
        a = PlatformAdapter()
        page = _FakePage(201, '{"id":1220000048319538,"object_id":0}')
        data = a.api_post(page, "https://x/gateway/draft", {"a": 1})
        self.assertEqual(str(data["id"]), "1220000048319538")

    def test_202_empty_body_is_success(self):
        a = PlatformAdapter()
        page = _FakePage(202, "{}")
        self.assertEqual(a.api_post(page, "https://x/publish", {}), {})

    def test_200_with_err_no_is_still_failure(self):
        a = PlatformAdapter()
        page = _FakePage(200, '{"err_no":1024,"err_msg":"参数错误"}')
        with self.assertRaises(PlatformError) as cm:
            a.api_post(page, "https://x/gateway/draft", {})
        self.assertIn("参数错误", str(cm.exception))

    def test_500_is_still_failure(self):
        a = PlatformAdapter()
        page = _FakePage(500, '{"err_no":0,"id":1}')
        with self.assertRaises(PlatformError):
            a.api_post(page, "https://x/gateway/draft", {})

    def test_non_json_is_still_failure(self):
        a = PlatformAdapter()
        page = _FakePage(200, "<html>login</html>")
        with self.assertRaises(PlatformError) as cm:
            a.api_post(page, "https://x/gateway/draft", {})
        self.assertIn("不是 JSON", str(cm.exception))


class BrowserChannelTests(unittest.TestCase):
    """R2 浏览器通道解析。"""

    def test_no_channel_returns_none(self):
        with mock.patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("HUB_BROWSER_CHANNEL", None)
        self.assertIsNone(browser_mod.resolve_channel_executable(""))

    def test_unknown_channel_returns_none(self):
        """未知通道不猜路径——回落到默认 chromium，绝不静默换浏览器。"""
        self.assertIsNone(browser_mod.resolve_channel_executable("safari"))

    def test_edge_channel_resolves_existing_binary(self):
        # 用真实存在的文件（当前解释器）代替 Edge 路径，避开"路径不存在"分支
        with mock.patch.dict(browser_mod.CHANNEL_BINARIES,
                             {"msedge": [sys.executable]}, clear=False):
            p = browser_mod.resolve_channel_executable("msedge")
        self.assertEqual(p, sys.executable)

    def test_missing_binary_falls_back_to_none(self):
        with mock.patch.dict(browser_mod.CHANNEL_BINARIES,
                             {"msedge": [r"C:\不存在\msedge.exe"]}, clear=False):
            self.assertIsNone(browser_mod.resolve_channel_executable("msedge"))


class ZhihuUrlVerdictTests(unittest.TestCase):
    """知乎发布成功判定：编辑器 URL /p/<id>/edit 不算已发布。

    这三条走真实分支（假 page 驱动 publish + wait_for_url_change），
    不断言源码里有没有某串字符，也不对硬编码 URL 做 `in` 断言。
    """

    ARTICLE = {"title": "发布链路回归正文", "content_md": "正文第一段。\n\n正文第二段。\n"}
    RENDERED = "正文第一段。\n\n正文第二段。\n"
    POST_URL = "https://zhuanlan.zhihu.com/p/2087370000076220077"

    def _run_publish(self, url_after_click):
        from core.adapters import zhihu as zhihu_mod

        ad = zhihu_mod.ZhihuAdapter()
        page = _PublishFakePage(url="https://zhuanlan.zhihu.com/write",
                                editor_text=self.RENDERED,
                                title_text=self.ARTICLE["title"])
        page.on_navigate = lambda p: setattr(p, "url", url_after_click)
        with mock.patch.object(ad, "_import_md_file", return_value=True), \
                mock.patch.object(ad, "save_debug", return_value="dump.html"), \
                mock.patch.object(ad, "PUBLISH_VERIFY_TIMEOUT", 0.05), \
                mock.patch.object(ad, "PUBLISH_VERIFY_POLL", 0.01), \
                mock.patch.object(zhihu_mod.time, "sleep"):
            return ad, page, ad.publish(page, dict(self.ARTICLE))

    def test_editor_url_after_click_is_not_published(self):
        """点完还停在 /p/<id>/edit → 必须抛错（编辑器 URL 不等于已发布）。"""
        with self.assertRaises(PlatformError) as cm:
            self._run_publish("https://zhuanlan.zhihu.com/p/2087370000076220077/edit")
        self.assertIn("没跳到预期地址", str(cm.exception))

    def test_write_url_after_click_is_not_published(self):
        """点完还停在通用 /write（新文章未分配 id）→ 必须抛错。"""
        with self.assertRaises(PlatformError):
            self._run_publish("https://zhuanlan.zhihu.com/write")

    def test_article_url_after_click_is_published(self):
        _ad, page, r = self._run_publish(self.POST_URL)
        self.assertFalse(r["draft_only"])
        self.assertEqual(r["post_id"], "2087370000076220077")
        self.assertEqual(r["post_url"], self.POST_URL)
        self.assertTrue(
            any("发布" in c for c in page.clicks),
            "正文回读通过后必须真的点过发布按钮")


class _PublishFakePage:
    """只实现知乎 publish 用到的口子：goto / fill / locator / evaluate。"""

    def __init__(self, url, editor_text, title_text):
        self.url = url
        self.editor_text = editor_text
        self.title_text = title_text
        self.clicks = []
        self.on_navigate = None

    def goto(self, url, **_kw):
        self.url = url

    def wait_for_selector(self, *_a, **_kw):
        return None

    def wait_for_load_state(self, *_a, **_kw):
        return None

    def fill(self, sel, value, **_kw):
        if "标题" in sel:
            self.title_text = value

    def locator(self, sel):
        return _PublishFakeLocator(self, sel)

    def evaluate(self, js, arg=None):
        if "hub:read-state" in js:
            return {"body": self.editor_text, "title": self.title_text}
        if "insertText" in js:
            return True
        return None


class _PublishFakeLocator:
    def __init__(self, page, sel):
        self._p = page
        self._sel = sel

    @property
    def first(self):
        return self

    def click(self, timeout=None):
        self._p.clicks.append(self._sel)
        if self._p.on_navigate and "发布" in self._sel:
            self._p.on_navigate(self._p)


if __name__ == "__main__":
    unittest.main()
