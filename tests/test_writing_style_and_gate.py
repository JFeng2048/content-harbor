# -*- coding: utf-8 -*-
"""写作风格档案 + AI 直发门禁开关 的回归测试（Behavior Lock）。

覆盖 Behavior Contract R1-R3：
  R1 风格档案注入  —— docs/writing-style.md 的内容必须进入每次写稿/改写/润色的
                      system 提示，调用方传的 style 追加在其后（不覆盖档案）
  R2 篇幅兜底      —— AI 返回正文明显短于要求字数时，自动续写一轮
  R3 直发开关      —— AI_DIRECT_PUBLISH 显式开启才允许 AI 稿正式发；
                      安全扫描与二审在任何开关状态下都仍然拒发高危内容

隔离约束：零外网（patch core.ai.chat）、零浏览器、零新增依赖，仅 unittest。
"""

import atexit
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import ai as ai_mod
from core import gate as gate_mod

SHORT_BODY = "太短了，不够一篇完整文章。" * 12
LONG_BODY = "这是一段足够长的正文内容，用来验证篇幅兜底逻辑不会被误触发。" * 40


def _fake_chat(recorder, body_queue):
    """按提示词分派的假 chat：写稿/续写/摘要/标签各走各的分支。"""
    def _chat(messages, model=None, temperature=0.7, max_tokens=4096):
        user = ""
        for m in messages:
            if m.get("role") == "user":
                user += m.get("content") or ""
        recorder.append(messages)
        if "只输出逗号分隔的标签" in user:
            return "标签甲,标签乙"
        if "50-150 字的摘要" in user:
            return "一段摘要"
        if "继续扩写" in user:
            return body_queue.pop(0) if body_queue else ""
        if "写主题为" in user:
            return body_queue.pop(0) if body_queue else ""
        return ""
    return _chat


class StyleProfileTests(unittest.TestCase):
    """R1 风格档案注入 + R2 篇幅兜底。"""

    def setUp(self):
        self.recorder = []

    def test_style_file_exists_and_loads(self):
        style = ai_mod.load_style()
        self.assertTrue(style.strip(), "docs/writing-style.md 应存在且非空")
        self.assertGreater(len(style), 80, "风格档案内容过短，达不到对齐目的")

    def test_style_is_injected_into_write_prompt(self):
        queue = ["标题：测试文章\n\n" + LONG_BODY]
        with mock.patch.object(ai_mod, "chat", _fake_chat(self.recorder, queue)):
            ai_mod.write_article("测试主题", words=2000)
        system = ""
        for m in self.recorder[0]:
            if m.get("role") == "system":
                system += m.get("content") or ""
        head = ai_mod.load_style().strip()[:30]
        self.assertIn(head, system, "风格档案内容未注入 system 提示")
        self.assertIn("【写作风格档案】", system)

    def test_call_style_argument_is_appended_not_replacing(self):
        queue = ["标题：测试文章\n\n" + LONG_BODY]
        with mock.patch.object(ai_mod, "chat", _fake_chat(self.recorder, queue)):
            ai_mod.write_article("测试主题", style="本次追加要求：多用表格", words=2000)
        system = ""
        for m in self.recorder[0]:
            if m.get("role") == "system":
                system += m.get("content") or ""
        self.assertIn("【写作风格档案】", system)
        self.assertIn("多用表格", system, "调用方 style 未追加到 system 提示")

    def test_missing_style_file_degrades_gracefully(self):
        with mock.patch.dict("os.environ",
                             {"WRITING_STYLE_FILE": str(ROOT / "no_such_style.md")}):
            self.assertEqual(ai_mod.load_style().strip(), "")
            self.assertIn("你是资深技术作者", ai_mod.system_write())

    def test_short_article_triggers_one_expansion_pass(self):
        queue = ["标题：短稿\n\n" + SHORT_BODY, LONG_BODY]
        with mock.patch.object(ai_mod, "chat", _fake_chat(self.recorder, queue)):
            art = ai_mod.write_article("测试主题", words=2000)
        expand_calls = [c for c in self.recorder
                        if any("继续扩写" in (m.get("content") or "")
                               for m in c)]
        self.assertEqual(len(expand_calls), 1, "篇幅不足时应恰好续写一轮")
        self.assertGreaterEqual(len(art["content_md"]),
                                int(2000 * ai_mod.MIN_COMPLETENESS_RATIO))

    def test_long_enough_article_is_not_expanded(self):
        queue = ["标题：长稿\n\n" + LONG_BODY]
        with mock.patch.object(ai_mod, "chat", _fake_chat(self.recorder, queue)):
            art = ai_mod.write_article("测试主题", words=2000)
        expand_calls = [c for c in self.recorder
                        if any("继续扩写" in (m.get("content") or "")
                               for m in c)]
        self.assertEqual(len(expand_calls), 0, "篇幅达标时不该多余调用一次 AI")
        self.assertIn("style_source", art)


class GateDirectPublishTests(unittest.TestCase):
    """R3 直发开关。"""

    ARTICLE = {"title": "标题", "content_md": "正文" * 200, "source": "ai",
               "ai_model": "agnes-3.0-flash"}
    DANGER = {"title": "标题",
              "content_md": "正常开头。" + "补充内容。" * 100 + "毒品制造",
              "source": "ai", "ai_model": "agnes-3.0-flash"}

    def _cfg(self, values):
        return lambda key, default=None: values.get(key, default)

    def test_switch_off_by_default_blocks_ai_direct_publish(self):
        with mock.patch.object(gate_mod, "_cfg", self._cfg({})):
            self.assertFalse(gate_mod.ai_direct_publish_allowed())
            r = gate_mod.gate_publish(dict(self.ARTICLE), draft_only=False)
        self.assertFalse(r["approved"])
        self.assertTrue(any("草稿" in i for i in r["issues"]))

    def test_switch_on_allows_ai_direct_publish(self):
        with mock.patch.object(gate_mod, "_cfg",
                               self._cfg({"AI_DIRECT_PUBLISH": True})):
            self.assertTrue(gate_mod.ai_direct_publish_allowed())
            r = gate_mod.gate_publish(dict(self.ARTICLE), draft_only=False)
        self.assertTrue(r["approved"], r["issues"])
        self.assertTrue(r["aigc_labeled"], "直开也不得跳过 AIGC 标识")

    def test_safety_scan_still_rejects_when_switch_on(self):
        with mock.patch.object(gate_mod, "_cfg",
                               self._cfg({"AI_DIRECT_PUBLISH": "true"})):
            r = gate_mod.gate_publish(dict(self.DANGER), draft_only=False)
        self.assertFalse(r["approved"], "开关放开也不得放过高危内容")
        self.assertEqual(r["review"]["reviewer"], "safety-scan")

    def test_human_article_behaviour_unchanged(self):
        art = dict(self.ARTICLE)
        art["source"] = "human"
        with mock.patch.object(gate_mod, "_cfg", self._cfg({})):
            r = gate_mod.gate_publish(art, draft_only=False)
        self.assertTrue(r["approved"], r["issues"])

    def test_switch_value_parsing(self):
        for v in ("true", "TRUE", "1", "yes", "on", True):
            with mock.patch.object(gate_mod, "_cfg", self._cfg(
                    {"AI_DIRECT_PUBLISH": v})):
                self.assertTrue(gate_mod.ai_direct_publish_allowed(), repr(v))
        for v in ("false", "0", "no", "", None, False):
            with mock.patch.object(gate_mod, "_cfg", self._cfg(
                    {"AI_DIRECT_PUBLISH": v})):
                self.assertFalse(gate_mod.ai_direct_publish_allowed(), repr(v))


    def test_review_prompt_is_time_grounded_and_context_aware(self):
        """R5 二审提示必须带当天日期与判定纪律（防误杀合规声明/误判时间线）。"""
        captured = {}

        def fake_chat(messages, model=None, temperature=0.0, max_tokens=500):
            captured["prompt"] = messages[0]["content"]
            return '{"verdict":"pass","issues":[]}'

        cfg = self._cfg({"REVIEW_MODEL": "agnes-2.5-flash"})
        with mock.patch.object(gate_mod, "_cfg", cfg), \
                mock.patch("core.ai.chat", fake_chat):
            r = gate_mod.dual_model_review({"title": "t", "content_md": "正文" * 200})
        prompt = captured["prompt"]
        self.assertIn(time.strftime("%Y-%m-%d"), prompt,
                      "二审提示缺少当天日期基准")
        self.assertIn("禁止性表述", prompt,
                      "二审提示缺少禁止性表述的判定纪律")
        self.assertIn("提供了", prompt,
                      "二审提示没有区分『声明不做』与『提供做法』")
        self.assertEqual(r["verdict"], "pass")


class AigcLabelSurvivesRewriteTests(unittest.TestCase):
    """R4 改写/润色整篇覆盖正文后，AIGC 显式标识不得丢失。"""

    def test_label_is_idempotent_and_reattachable(self):
        art = {"title": "t", "content_md": "正文" * 200, "source": "ai",
               "ai_model": "agnes-3.0-flash", "ext": "{}"}
        once = gate_mod.add_aigc_label(dict(art), "agnes-3.0-flash")
        twice = gate_mod.add_aigc_label(dict(once), "agnes-3.0-flash")
        self.assertIn("本文由 AI 辅助生成", once["content_md"])
        self.assertEqual(once["content_md"].count("本文由 AI 辅助生成"), 1)
        self.assertEqual(once["content_md"], twice["content_md"],
                         "重复打标必须幂等，不能叠加声明")

    def test_service_rewrite_restores_label(self):
        # 走真实 service 路径：改写返回的正文没有声明，service 必须补回
        import core.db as _db

        tmp = Path(tempfile.mkdtemp(prefix="hub_style_testdb_"))
        orig_db_path = _db.DB_PATH
        _db.DB_PATH = tmp / "hub_test.db"
        atexit.register(lambda: shutil.rmtree(tmp, ignore_errors=True))
        try:
            from core.service import Hub

            hub = Hub()
            hub.conn.execute(
                "INSERT INTO articles (title, content_md, source, ai_model, ext,"
                " status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                ("T", "原始正文" * 100, "ai", "agnes-3.0-flash", "{}", "draft",
                 time.time(), time.time()))
            hub.conn.commit()
            aid = hub.conn.execute(
                "SELECT id FROM articles ORDER BY id DESC LIMIT 1").fetchone()[0]
            with mock.patch.object(ai_mod, "rewrite",
                                   return_value="被改写的新正文" * 40):
                hub.ai_rewrite(aid, "改写")
            after = hub.get(aid)["content_md"]
            self.assertIn("被改写的新正文", after)
            self.assertIn("本文由 AI 辅助生成", after,
                          "改写后 AIGC 标识丢了")
        finally:
            _db.DB_PATH = orig_db_path
            os.environ.pop("DEMO", None)


if __name__ == "__main__":
    unittest.main()
