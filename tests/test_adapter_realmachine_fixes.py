# -*- coding: utf-8 -*-
"""2026-09-27 真机定位到的四个平台缺陷的回归测试。

被锁住的行为契约：
  Z1 编辑器入口确定性 —— 进知乎编辑器只能走拼出来的 /p/<id>/edit。
        文章页上 button:has-text("编辑") 命中的是页头/搜索区的另一个按钮，
        点完跳到 www.zhihu.com/search?...（URL 带 search_preset），于是报
        「页面回读到空内容（编辑器没渲染出来，或页面已跳走）」。
  Z2 清空必须走真实键盘 —— execCommand('selectAll' + 'delete') 只清 DOM，
        Draft.js 的 editorState 原封不动：实测清空后立刻「导入文档」，
        编辑器拿旧 state 重新渲染，正文从 1 字长回 15977 字（导入后 21318）。
  Z3 提交按钮按精确文本点 —— 编辑页上同时有「更新」与「发布设置」，
        has-text("发布") 命中的是「发布设置」（点开设置浮层，提交根本没点）。
  C1 CSDN 分类专栏必须用 input.click() —— 老实现点 closest('label')，
        点完 checked 仍 false、隐藏 input[name=categories] 仍为空；而
        「分类专栏没勾」时 CSDN 跑完 userstatus / risk/check 就不发发布请求，
        弹窗一直挂着（旧 update 报「30s 内发布弹窗未关闭」）。
  C2 CSDN 更新成功判据是「重开编辑页读到目标正文」—— 该编辑页发出的
        saveArticle 不带 articleId 且 is_new=1，CSDN 会**新建**一篇；
        弹窗关闭恰恰是新建成功的信号，绝不能当更新成功。
  C3 落地到了别的 articleId 必须判失败并说清新建了哪一篇。
  R1 渲染归一化 —— 有序列表序号是 CSS 计数器画的、编辑器把直引号换成弯引号，
        回读比对不能因此把「内容其实正确」判成未生效。

隔离约束：零外网、零浏览器、零新增依赖。page / locator / keyboard 全是假对象。
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.adapters import base as base_mod
from core.adapters.base import PlatformError
from core.adapters.csdn import CSDNAdapter
from core.adapters.zhihu import ZhihuAdapter

ARTICLE_URL = "https://zhuanlan.zhihu.com/p/2087370000076220077"
ARTICLE_ID = "2087370000076220077"
EDIT_URL = ARTICLE_URL + "/edit"
TITLE = "回读验证回归测试正文"

MD = (
    "## 问题与动机\n\n"
    "我需要一个能把同一篇文章批量发到 10 个技术平台的工具，这是回归测试的正文。\n\n"
    "1.  **适配器层**：每个平台一个适配器，声明 needs_browser 与四个动作。\n"
    "2.  **浏览器层**：patchright 驱动持久化 profile 目录，登录一次长期复用。\n"
    "3.  **门禁层**：高危词安全扫描与 AIGC 显式标识注入，最后是发布闸门。\n"
)

# 编辑器渲染后的形态：ATX 标题记号被吃掉、有序列表序号是 CSS 计数器画的
# （<ol> 的 list-style 是 none，innerText 里一个数字都没有）、直引号被换成弯引号。
RENDERED = (
    "问题与动机\n\n"
    "我需要一个能把同一篇文章批量发到 10 个技术平台的工具，这是回归测试的正文。\n\n"
    "适配器层：每个平台一个适配器，声明 needs_browser 与四个动作。\n"
    "浏览器层：patchright 驱动持久化 profile 目录，登录一次长期复用。\n"
    "门禁层：高危词安全扫描与 AIGC 显式标识注入，最后是发布闸门。\n"
)

# 带弯引号的渲染形态（Draft.js 会把 "x" 渲染成 “x”）
MD_QUOTED = (
    "## 排查\n\n"
    "我曾把页面标签词 \"MetaWeblog\" 误当成登录名写进配置，排查方法是直接调接口。\n"
)
RENDERED_QUOTED = (
    "排查\n\n"
    "我曾把页面标签词 “MetaWeblog” 误当成登录名写进配置，排查方法是直接调接口。\n"
)

CSDN_ID = "166698802"
CSDN_EDIT = "https://editor.csdn.net/md/?articleId=166698802"


# --------------------------------------------------------------------------
# 假对象
# --------------------------------------------------------------------------
class _Keyboard:
    def __init__(self, page):
        self._p = page

    def press(self, key, **_kw):
        self._p.keys.append(key)
        if key == "Control+A":
            self._p.selected_all = True
        elif key in ("Delete", "Backspace") and self._p.selected_all:
            if self._p.focus == "title":
                self._p.title_text = ""
            else:
                self._p.editor_text = ""
            self._p.selected_all = False

    def insert_text(self, text, **_kw):
        if self._p.focus == "title":
            self._p.title_text = text
            self._p.selected_all = False
            return
        if self._p.selected_all:
            self._p.editor_text = text
            self._p.selected_all = False
        else:
            self._p.editor_text = (self._p.editor_text or "") + text

    def type(self, text, delay=None):
        self.insert_text(text)


class _Locator:
    def __init__(self, page, sel):
        self._p = page
        self._sel = sel

    @property
    def first(self):
        return self

    def nth(self, i):
        return self

    def count(self):
        return self._p.counts.get(self._sel, 0)

    def is_visible(self):
        return True

    def click(self, timeout=None):
        # 跟 Playwright 一致：选择器没命中元素时 click 必须失败，
        # 否则「精确匹配没命中→退回子串匹配」这条降级路在测试里永远走不到。
        if self.count() <= 0:
            raise TimeoutError("locator.click: Timeout %sms exceeded" % (timeout or 0))
        self._p.clicks.append(self._sel)
        self._p.on_click(self._sel)

    def set_input_files(self, path):
        self._p.imported = path


class _Page:
    """假 page：按选择器查、按哨兵回读，够跑适配器的注入与回读链路。"""

    def __init__(self, editor_text="", title_text="", persisted=None,
                 url="about:blank", counts=None):
        self.editor_text = editor_text
        self.title_text = title_text
        self.persisted = persisted
        self.url = url
        self.gotos = []
        self.clicks = []
        self.fills = []
        self.keys = []
        self.selected_all = False
        self.focus = "editor"
        self.imported = None
        self.counts = dict(counts or {})
        self.keyboard = _Keyboard(self)
        self.on_click = lambda sel: None
        # 发布弹窗状态：分类专栏勾选后写进隐藏 input[name=categories]
        self.all_categories = ()
        self.checked_categories = []
        self.modal_open = True
        self.summary = None

    def on_submit(self):
        self.modal_open = False

    # --- 导航 ---
    def goto(self, url, **_kw):
        self.gotos.append(url)
        self.url = url

    def wait_for_selector(self, *_a, **_kw):
        return None

    def wait_for_load_state(self, *_a, **_kw):
        return None

    # --- 元素 ---
    def locator(self, sel):
        return _Locator(self, sel)

    def query_selector(self, sel):
        if sel in self.counts:
            return _Locator(self, sel) if self.counts[sel] else None
        return _Locator(self, sel)

    def fill(self, sel, value, **_kw):
        self.fills.append((sel, value))
        self.title_text = value

    def click(self, sel, timeout=None):
        self.on_click(sel)

    # --- 脚本 ---
    def evaluate(self, js, arg=None):
        if "hub:focus-editor" in js:
            self.focus = "editor"
            return True
        if "hub:editor-len" in js:
            body = self._visible_body()
            return len(body or "") if body is not None else -1
        if "hub:read-state" in js:
            return {"body": self._visible_body() or "", "title": self.title_text}
        if "hub:read-text" in js:
            return self.body_text
        if "input.tag__option-chk" in js and "categories" in js:
            return {"picked": list(self.checked_categories),
                    "hidden": ",".join(self.checked_categories)}
        if "input.tag__option-chk" in js:
            n = 0
            for c in getattr(self, "all_categories", []):
                if c == arg and c not in self.checked_categories:
                    self.checked_categories.append(c)
                    n += 1
            return n
        if "el-textarea__inner" in js:
            self.summary = arg
            return None
        if "btn-b-red" in js:
            self.on_submit()
            return None
        if "!document.querySelector(sel)" in js:
            # 适配器问的是「发布弹窗还在不在」，选择器走参数传进来
            return not self.modal_open
        return None

    def _visible_body(self):
        body = self.editor_text
        if len(self.gotos) > 1 and self.persisted is not None:
            body = self.persisted
        return body

    @property
    def body_text(self):
        return ""


# --------------------------------------------------------------------------
# R1 渲染归一化（base.content_evidence）
# --------------------------------------------------------------------------
class RenderNormalizationTests(unittest.TestCase):
    """R1：编辑器渲染差异不能被误判成「正文没生效」。"""

    def test_flatten_folds_curly_quotes_to_ascii(self):
        self.assertEqual(base_mod._flatten("标签词 “MetaWeblog” 误当"),
                         base_mod._flatten('标签词 "MetaWeblog" 误当'))

    def test_ordered_list_marker_is_css_generated_so_marker_free_matches(self):
        """知乎把 2. xxx 渲染成 <ol><li>，序号是伪元素，innerText 里没有。"""
        ok, detail = base_mod.content_evidence(MD, RENDERED)
        self.assertTrue(ok, "有序列表渲染后必须判为已生效 :: %s" % detail)

    def test_curly_quote_body_accepted(self):
        ok, detail = base_mod.content_evidence(MD_QUOTED, RENDERED_QUOTED)
        self.assertTrue(ok, "弯引号渲染后必须判为已生效 :: %s" % detail)

    def test_still_rejects_genuinely_stale_body(self):
        """归一化不能把「旧正文还在」也放过。"""
        stale = "问题与动机\n\n这一段是完全不同的旧正文，跟新版没有任何重合片段的内容。\n"
        ok, _detail = base_mod.content_evidence(MD, stale)
        self.assertFalse(ok)

    def test_marker_free_tolerance_does_not_accept_another_article(self):
        other = RENDERED.replace("适配器层", "计费服务")
        ok, _detail = base_mod.content_evidence(MD, other)
        self.assertFalse(ok)


# --------------------------------------------------------------------------
# Z1/Z2/Z3 知乎
# --------------------------------------------------------------------------
class ZhihuEditorEntryTests(unittest.TestCase):
    """Z1：进编辑器只能走 /p/<id>/edit，不许靠文章页的「编辑」按钮。"""

    PUB = {"post_id": ARTICLE_ID, "post_url": ARTICLE_URL, "edit_url": EDIT_URL}

    def test_candidates_prefer_deterministic_edit_url(self):
        ad = ZhihuAdapter()
        self.assertEqual(ad._editor_candidates(self.PUB)[0], EDIT_URL)

    def test_racy_blank_write_url_is_rejected(self):
        ad = ZhihuAdapter()
        cands = ad._editor_candidates(
            {"post_url": ARTICLE_URL, "edit_url": "https://zhuanlan.zhihu.com/write"})
        self.assertNotIn("https://zhuanlan.zhihu.com/write", cands)
        self.assertEqual(cands, [EDIT_URL])

    def test_derives_edit_url_from_post_id_when_edit_url_missing(self):
        ad = ZhihuAdapter()
        cands = ad._editor_candidates({"post_id": ARTICLE_ID, "post_url": ARTICLE_URL})
        self.assertIn(EDIT_URL, cands)

    def test_open_editor_raises_when_no_candidate_renders_text(self):
        """所有候选都打不开编辑器（老实现的「点了编辑跳搜索页」就落在这个分支）。"""
        ad = ZhihuAdapter()
        page = _Page(editor_text="", title_text=TITLE)
        with mock.patch("core.adapters.zhihu.time.sleep"), \
                mock.patch.object(ad, "_wait_editor", return_value=0):
            with self.assertRaises(PlatformError) as cm:
                ad._open_editor(page, dict(self.PUB), "更新·打开编辑器")
        self.assertIn("编辑器地址", str(cm.exception))

    def test_open_editor_never_navigates_to_the_article_page(self):
        ad = ZhihuAdapter()
        page = _Page(editor_text=RENDERED, title_text=TITLE)
        with mock.patch("core.adapters.zhihu.time.sleep"):
            got = ad._open_editor(page, dict(self.PUB), "更新·打开编辑器")
        self.assertEqual(got, EDIT_URL)
        self.assertNotIn(ARTICLE_URL, page.gotos)


class ZhihuClearEditorTests(unittest.TestCase):
    """Z2：清空必须走真实键盘事件，execCommand 只清 DOM 不动 editorState。"""

    def test_clear_uses_keyboard_and_reports_empty(self):
        ad = ZhihuAdapter()
        page = _Page(editor_text="旧正文" * 40, title_text=TITLE)
        with mock.patch("core.adapters.zhihu.time.sleep"):
            left = ad._clear_editor(page)
        self.assertEqual(left, 0)
        self.assertEqual(page.editor_text, "")
        self.assertIn("Control+A", page.keys)
        self.assertIn("Delete", page.keys)

    def test_inject_editor_aborts_when_clear_did_not_take(self):
        """清空没生效还继续注入 = 把新正文追加在旧正文后面，必须中止。"""
        ad = ZhihuAdapter()
        page = _Page(editor_text="旧正文" * 40, title_text=TITLE)
        page.selected_all = False      # 模拟 Delete 没把选区删掉
        with mock.patch("core.adapters.zhihu.time.sleep"), \
                mock.patch.object(ad, "_wait_editor", return_value=120):
            with self.assertRaises(PlatformError) as cm:
                ad._inject_editor(page, MD)
        self.assertIn("清空失败", str(cm.exception))

    def test_import_returns_false_when_clear_did_not_take(self):
        ad = ZhihuAdapter()
        page = _Page(editor_text="旧正文" * 40, title_text=TITLE)
        with mock.patch("core.adapters.zhihu.time.sleep"), \
                mock.patch.object(ad, "_clear_editor", return_value=99):
            self.assertFalse(ad._import_md_file(page, MD))


class ZhihuSubmitButtonTests(unittest.TestCase):
    """Z3：编辑页的提交按钮叫「更新」，「发布设置」不是它。"""

    def test_update_clicks_exact_update_button(self):
        from core.adapters import zhihu as zh_mod

        ad = zh_mod.ZhihuAdapter()
        page = _Page(editor_text=RENDERED, title_text=TITLE,
                     persisted=RENDERED, url=EDIT_URL,
                     counts={'button:text-is("更新")': 1,
                             'button:has-text("发布")': 1})
        with mock.patch.object(ad, "_import_md_file", return_value=True), \
                mock.patch.object(ad, "save_debug", return_value="dump.html"), \
                mock.patch("core.adapters.zhihu.time.sleep"):
            self.assertTrue(ad.update(
                page,
                {"post_id": ARTICLE_ID, "post_url": ARTICLE_URL, "edit_url": EDIT_URL},
                {"title": TITLE, "content_md": MD}))
        self.assertIn('button:text-is("更新")', page.clicks)
        self.assertNotIn('button:has-text("发布")', page.clicks,
                         "has-text(发布) 会命中「发布设置」，点开的是设置浮层")

    def test_update_raises_when_no_update_button(self):
        from core.adapters import zhihu as zh_mod

        ad = zh_mod.ZhihuAdapter()
        page = _Page(editor_text=RENDERED, title_text=TITLE,
                     persisted=RENDERED, url=EDIT_URL, counts={})
        with mock.patch.object(ad, "_import_md_file", return_value=True), \
                mock.patch.object(ad, "save_debug", return_value="dump.html"), \
                mock.patch("core.adapters.zhihu.time.sleep"):
            with self.assertRaises(PlatformError) as cm:
                ad.update(
                    page,
                    {"post_id": ARTICLE_ID, "post_url": ARTICLE_URL,
                     "edit_url": EDIT_URL},
                    {"title": TITLE, "content_md": MD})
        self.assertIn("更新", str(cm.exception))


# --------------------------------------------------------------------------
# C1/C2/C3 CSDN
# --------------------------------------------------------------------------
class CSDNCategoryTests(unittest.TestCase):
    """C1：分类专栏必须用 input.click()，label 转发勾不上。"""

    def test_select_category_clicks_input_and_confirms_hidden_value(self):
        ad = CSDNAdapter()
        page = _Page(editor_text=MD, title_text=TITLE)
        page.all_categories = ["后端与架构设计", "前端与全栈工程"]
        with mock.patch("core.adapters.csdn.time.sleep"):
            ok = ad._select_category(page, "后端与架构设计")
        self.assertTrue(ok)
        self.assertIn("后端与架构设计", page.checked_categories)

    def test_select_category_reports_false_when_nothing_gets_checked(self):
        ad = CSDNAdapter()
        page = _Page(editor_text=MD, title_text=TITLE)
        page.all_categories = ["前端与全栈工程"]
        with mock.patch("core.adapters.csdn.time.sleep"):
            self.assertFalse(ad._select_category(page, "后端与架构设计"))


class CSDNUpdateVerificationTests(unittest.TestCase):
    """C2/C3：更新成功判据是「重开编辑页读到目标正文」，不是弹窗关闭。"""

    PUB = {"post_id": CSDN_ID, "edit_url": CSDN_EDIT,
           "post_url": "https://blog.csdn.net/u/article/details/%s" % CSDN_ID}
    ARTICLE = {"title": TITLE, "content_md": MD}

    def _page(self, persisted, landed_url=None):
        page = _Page(editor_text=MD, title_text=TITLE, persisted=persisted,
                     url=CSDN_EDIT,
                     counts={'input[type=file][accept*=".md"], '
                             '#import-markdown-file-input': 1})
        page.all_categories = ["后端与架构设计"]
        page.modal_open = True
        if landed_url is not None:
            def _submit():
                page.modal_open = False
                page.url = landed_url
            page.on_submit = _submit
        return page

    def _run(self, page):
        ad = CSDNAdapter()
        with mock.patch.object(ad, "_import_md_file", return_value=True), \
                mock.patch.object(ad, "_set_title", return_value=True), \
                mock.patch.object(ad, "_select_tag", return_value=True), \
                mock.patch.object(ad, "save_debug", return_value="dump.html"), \
                mock.patch("core.adapters.csdn.time.sleep"), \
                mock.patch("core.adapters.csdn.CaptchaPolicy.detect", return_value=None):
            return ad.update(page, dict(self.PUB), dict(self.ARTICLE))

    def test_update_succeeds_when_reopened_editor_has_target_content(self):
        self.assertTrue(self._run(self._page(persisted=MD)))

    def test_update_fails_when_reopened_editor_still_has_old_body(self):
        """弹窗关了（=新建成功）但目标文章没变 —— 必须判失败。"""
        stale = "## 问题与动机\n\n这段是完全不同的旧正文，跟新版没有任何重合片段。\n"
        with self.assertRaises(PlatformError) as cm:
            self._run(self._page(persisted=stale,
                                 landed_url="https://mp.csdn.net/mp_blog/creation/success/1"))
        self.assertIn("回读", str(cm.exception))

    def test_update_fails_and_names_the_duplicate_when_landed_on_another_id(self):
        page = self._page(persisted=MD,
                          landed_url="https://mp.csdn.net/mp_blog/creation/success/166737625")
        with self.assertRaises(PlatformError) as cm:
            self._run(page)
        msg = str(cm.exception)
        self.assertIn("166737625", msg)
        self.assertIn(CSDN_ID, msg)
        self.assertIn("新建", msg)

    def test_landed_article_id_parsed_only_from_success_url(self):
        ad = CSDNAdapter()
        self.assertEqual(
            ad._landed_article_id("https://mp.csdn.net/mp_blog/creation/success/166737625"),
            "166737625")
        self.assertEqual(ad._landed_article_id(CSDN_EDIT), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
