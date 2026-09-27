# -*- coding: utf-8 -*-
"""「假成功」回归测试（verify-after-act，Behavior Lock）。

被锁住的行为契约：
  V1 回读原语     —— core/adapters/base.py 的回读工具在证据不足时一律判失败：
                    content_evidence / title_evidence / wait_for_url_change /
                    verify_text_present 都不允许给出"看起来成功"的返回值
  V2 知乎原地更新 —— 正文没注入进去、或保存后重新打开还是旧正文，
                    必须抛 PlatformError（旧实现两条路都没写进去也 return True）
  V3 掘金发布     —— 点完「确定并发布」但已发布列表里查不到这篇文章，必须抛
                    PlatformError（2026-09 平台只发 article_draft/update，不发
                    article/publish）；只有列表接口出现 status=2 才允许返回成功
  V4 思否发布     —— 提交按钮 disabled（草稿建了但根本没发）必须抛
                    PlatformError，并与"发布成功"明确区分
  V5 证据强度     —— 强证据（URL 里的 article_id）不被弱证据（同标题）覆盖；
                    短文/短标题的判定不许 fail-open；成功文案只认 toast 容器
  V6 台账不撒谎   —— 适配器抛 PlatformError 时 publications.status 必须是 failed

隔离约束：零外网、零浏览器、零新增依赖。page / locator 全是假对象。
新增的 base 原语走 module 属性访问（base_mod.xxx），RED 阶段表现为
AttributeError 而非模块级 ImportError，保证每个用例独立报红。
"""

import sys
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.adapters import base as base_mod
from core.adapters.base import PlatformAdapter, PlatformError

# 目标正文：各段之间刻意不重叠，模拟"换了一整篇"
NEW_MD = (
    "# 回读验证回归测试正文\n\n"
    "第一段：新版正文的核心断言，用来确认编辑器里确实是这一篇而不是旧稿。\n\n"
    "## 小节标题\n\n"
    "- 要点一：回读验证必须以页面可观测证据为准，不能只看有没有点下去。\n"
    "- 要点二：证不出来就抛错，绝不把未生效的动作记成成功。\n\n"
    "```python\nprint('verify after act')\n```\n\n"
    "最后一段：专门用来验证末行片段也被比对，标记 END-OF-NEW-BODY。\n"
)

# 旧正文：与新版没有任何重合片段
OLD_MD = (
    "# 历史遗留标题\n\n"
    "这是一段完全不同的旧正文，属于上一轮发布留下的内容，与新版无任何重合片段。\n"
)

# 编辑器吃掉 markdown 记号后的富文本形态（知乎 Draft.js / 掘金 CodeMirror 都会这样）
RENDERED_NEW = (
    "回读验证回归测试正文\n\n"
    "第一段：新版正文的核心断言，用来确认编辑器里确实是这一篇而不是旧稿。\n\n"
    "小节标题\n\n"
    "要点一：回读验证必须以页面可观测证据为准，不能只看有没有点下去。\n"
    "要点二：证不出来就抛错，绝不把未生效的动作记成成功。\n\n"
    "print('verify after act')\n\n"
    "最后一段：专门用来验证末行片段也被比对，标记 END-OF-NEW-BODY。\n"
)

TITLE = "回读验证回归测试正文"
ZHIHU_PUB = {
    "post_url": "https://zhuanlan.zhihu.com/p/2087370000076220077",
    "edit_url": "https://zhuanlan.zhihu.com/p/2087370000076220077/edit",
}

# ---- M1：正文含外链与图片（技术文的常态）--------------------------------
# 目标侧是带 markdown 链接/图片的源文；页面侧是编辑器渲染后的形态：
# 链接只留锚文本，图片整体变成 <img>（innerText 里一个字都不剩）。
MD_WITH_LINKS = (
    "# 外链与图片回归\n\n"
    "参考资料：详见 [官方文档](https://example.com/docs/x) 这一节的说明。\n\n"
    "![系统架构示意图](https://example.com/img/arch.png)\n\n"
    "结论：正文带外链与图片时，回读不能把它误判成未生效。\n"
)
RENDERED_WITH_LINKS = (
    "外链与图片回归\n\n"
    "参考资料：详见 官方文档 这一节的说明。\n\n"
    "结论：正文带外链与图片时，回读不能把它误判成未生效。\n"
)

# ---- M3：每行都短于 _FRAGMENT_MIN_LEN 的速查表（key_fragments 返回 []）----
SHORT_LINES_MD = (
    "# 速查表\n\n"
    "- 键 A\n"
    "- 键 B\n"
    "- 键 C\n"
    "- 键 D\n"
    "- 键 E\n"
    "- 键 F\n"
)
SHORT_LINES_RENDERED = "速查表\n\n键 A\n键 B\n键 C\n键 D\n键 E\n键 F\n"
SHORT_LINES_OLD = "键 A\n键 B\n键 X\n键 Y\n键 Z\n键 W\n"

# ---- m1+m2：首段位置检查的两个边界 ---------------------------------------
# 短首行：旧实现给固定 40 字容差，9~40 字的陈旧前缀都能混过。
MD_SHORT_HEAD = (
    "# 短标题\n\n"
    "第一段正文，用来说明这一节到底要讲清楚什么问题。\n\n"
    "第二段正文，补充说明回读验证在整条发布链路里的位置。\n\n"
    "第三段正文，收尾并标记 END-OF-SHORT-HEAD-BODY。\n"
)
# 形态 A：首行标题被提到标题框，正文里没有它（知乎导入 md 就会这样）
RENDERED_SHORT_HEAD = (
    "第一段正文，用来说明这一节到底要讲清楚什么问题。\n\n"
    "第二段正文，补充说明回读验证在整条发布链路里的位置。\n\n"
    "第三段正文，收尾并标记 END-OF-SHORT-HEAD-BODY。\n"
)
# 形态 B：首行标题仍在正文开头（CodeMirror 这类原样渲染的平台）
RENDERED_SHORT_HEAD_KEEP = "短标题\n\n" + RENDERED_SHORT_HEAD

# 40 字首行（容差边界用），同样取"标题被提到标题框"的形态
MD_40_HEAD = (
    "# " + "标" * 39 + "题\n\n"
    "第一段正文，用来说明这一节到底要讲清楚什么问题。\n\n"
    "第二段正文，补充说明回读验证在整条发布链路里的位置。\n\n"
    "第三段正文，收尾并标记 END-OF-LONG-HEAD-BODY。\n"
)
RENDERED_40_HEAD = (
    "第一段正文，用来说明这一节到底要讲清楚什么问题。\n\n"
    "第二段正文，补充说明回读验证在整条发布链路里的位置。\n\n"
    "第三段正文，收尾并标记 END-OF-LONG-HEAD-BODY。\n"
)

# ---- m1+m2：首段落不进「最长的 3 段」时的追加检测 ------------------------
# 引导句是列表项且最短 → 不是关键片段之一 → 旧实现在这一支上 pos<0 静默放行。
# 编辑器渲染列表会带项目符号（•），压平后首行定位不到，但开头锚点还在。
_MD_BULLET = (
    "第一段正文，用来说明这一节到底要讲清楚什么问题。\n"
    "第二段正文，补充说明回读验证在整条发布链路里的位置。\n"
    "第三段正文，收尾并标记 END-OF-BULLET-HEAD-BODY。\n"
)
MD_BULLET_HEAD = (
    "# 列表引导\n\n"
    "- 这是一条列表引导语，交代本节要讲的内容。\n\n"
    + _MD_BULLET
)
RENDERED_BULLET_HEAD = (
    "列表引导\n\n"
    "• 这是一条列表引导语，交代本节要讲的内容。\n\n" + _MD_BULLET
)
BULLET_STALE_PREFIX = "上一轮遗留的旧正文，与新版没有任何重合片段，用来占住正文开头。\n"


class _FakeLocator:
    def __init__(self, page, sel, nth=0):
        self._p = page
        self._sel = sel
        self._nth = nth

    @property
    def first(self):
        return _FakeLocator(self._p, self._sel, 0)

    @property
    def last(self):
        return _FakeLocator(self._p, self._sel, 1 << 30)

    def nth(self, i):
        return _FakeLocator(self._p, self._sel, i)

    def filter(self, **_kw):
        return self

    def all(self):
        return [self]

    def count(self):
        return self._p.selector_count(self._sel)

    def is_visible(self):
        return True

    def is_disabled(self):
        return self._p.submit_disabled

    def click(self, timeout=None):
        self._p.focused_sel = self._sel
        self._p.on_click(self._sel)

    def fill(self, value, timeout=None):
        self._p.fill(self._sel, value)


class _FakeKeyboard:
    """假 keyboard：把「Ctrl+A → Delete」建模成真的清空编辑器。

    2026-09-27 知乎 Draft.js 实测：document.execCommand('selectAll' + 'delete')
    只清 DOM 不动 editorState，走真实键盘才清得掉。适配器因此改成用键盘清空，
    假 page 必须照着这个语义建模，否则清空这一步测不出任何东西。

    键入落到哪儿取决于 page.focused_sel：点在标题输入框上就改标题，点在编辑器
    上才改正文（掘金 update 就是点标题框后 type 标题的）。
    """

    def __init__(self, page):
        self._p = page

    def _on_title(self):
        sel = (self._p.focused_sel or "").lower()
        return "标题" in sel or "title" in sel

    def press(self, key, **_kw):
        self._p.keys.append(key)
        if key == "Control+A":
            self._p.selected_all = True
        elif key in ("Delete", "Backspace") and self._p.selected_all:
            if self._on_title():
                self._p.title_text = ""
            else:
                self._p.editor_text = ""
            self._p.selected_all = False

    def insert_text(self, text, **_kw):
        if self._on_title():
            if self._p.selected_all:
                self._p.title_text = text
                self._p.selected_all = False
            else:
                self._p.title_text = (self._p.title_text or "") + text
            return
        if self._p.selected_all:
            self._p.editor_text = text
            self._p.selected_all = False
        else:
            self._p.editor_text = (self._p.editor_text or "") + text

    def type(self, text, **_kw):
        self.insert_text(text)


class _FakePage:
    """假 page：只实现回读链路用到的那几个口子（goto/evaluate/locator/fill/...）。

    回读语义（模拟"保存到底有没有落库"）：
      editor_text —— 当前编辑器 DOM 里的正文
      persisted   —— 重新打开页面后编辑器里的正文；None 表示服务端存的就是
                     editor_text（保存生效），给字符串则代表"保存没生效"
    """

    def __init__(self, url="about:blank", editor_text=OLD_MD, title_text="",
                 persisted=None):
        self.url = url
        self.editor_text = editor_text
        self.title_text = title_text
        self.persisted = persisted
        self.body_text = ""
        self.toast_text = ""      # 只在 toast/notification 类容器里的文本
        self.goto_count = 0
        self.gotos = []           # 每次 goto 的地址，用来断言"回读有没有开错页"
        self.fills = []
        self.clicks = []
        self.submit_disabled = False
        self.on_navigate = None   # callable(page)，点提交后改 URL 用
        self.keys = []           # 真实键盘事件序列（Ctrl+A / Delete / ...）
        self.selected_all = False
        self.focused_sel = None  # 最近一次点击/聚焦的元素选择器
        self.keyboard = _FakeKeyboard(self)

    # ---------------- 导航 ----------------

    def goto(self, url, **_kw):
        self.goto_count += 1
        self.gotos.append(url)
        self.url = url

    def wait_for_load_state(self, *_a, **_kw):
        return None

    def wait_for_selector(self, *_a, **_kw):
        return None

    def wait_for_timeout(self, _ms):
        return None

    # ---------------- 元素 ----------------

    def locator(self, sel):
        return _FakeLocator(self, sel)

    def query_selector(self, sel):
        return _FakeLocator(self, sel)

    def click(self, sel, timeout=None):
        self.on_click(sel)

    def fill(self, sel, value, **_kw):
        self.fills.append((sel, value))
        if "标题" in sel or "title" in sel.lower():
            self.title_text = value

    def selector_count(self, _sel):
        return 1

    def inner_text(self, _sel):
        return self.body_text

    def on_click(self, sel):
        self.clicks.append(sel)
        if self.on_navigate and ("提交" in sel or "发布" in sel):
            self.on_navigate(self)

    # ---------------- 脚本 ----------------

    def evaluate(self, js, arg=None):
        # 回读原语都带哨兵注释，靠它区分是"读"还是"写"
        if "hub:focus-editor" in js:
            self.focused_sel = "editor"
            return True
        if "hub:submit-disabled" in js:
            return self.submit_disabled
        if "hub:toast-text" in js:
            return self.toast_text
        if "hub:editor-len" in js:
            # 「编辑器渲染出正文了没」——用长度表达，-1 是选择器没命中
            body = self.editor_text
            if self.goto_count > 1 and self.persisted is not None:
                body = self.persisted
            return len(body or "") if body is not None else -1
        if "hub:read-state" in js:
            body = self.editor_text
            if self.goto_count > 1 and self.persisted is not None:
                body = self.persisted
            return {"body": body, "title": self.title_text}
        if "hub:read-text" in js:
            return self.body_text
        if "insertText" in js:
            # 注入 JS「返回成功」但正文一个字没写（2026-09 知乎实况）
            return True
        return None


class _ServerCopyPage(_FakePage):
    """回读语义：重新打开写作页读到的是服务端那份 server_text。

    与 _FakePage 的差别是 goto 次数——这里模拟「API 写完立刻重开页面」，
    读到的永远是服务端副本，跟页面内存里的 editor_text 无关。
    """

    def __init__(self, *a, server_text=OLD_MD, **kw):
        super().__init__(*a, **kw)
        self.server_text = server_text

    def evaluate(self, js, arg=None):
        if "hub:read-state" in js:
            return {"body": self.server_text, "title": self.title_text}
        return super().evaluate(js, arg)


class ReadbackPrimitiveTests(unittest.TestCase):
    """V1：回读原语本身的行为（不依赖任何平台）。"""

    def test_content_evidence_rejects_stale_body(self):
        ok, detail = base_mod.content_evidence(NEW_MD, OLD_MD)
        self.assertFalse(ok, "旧正文还在页面上时必须判失败")
        self.assertIn("关键", detail)

    def test_content_evidence_accepts_rendered_same_body(self):
        ok, detail = base_mod.content_evidence(NEW_MD, RENDERED_NEW)
        self.assertTrue(ok, detail)

    def test_content_evidence_rejects_empty_readback(self):
        ok, detail = base_mod.content_evidence(NEW_MD, "")
        self.assertFalse(ok, "回读到空内容（编辑器没渲染/已跳走）必须判失败")
        self.assertIn("空", detail)

    def test_content_evidence_rejects_truncated_body(self):
        ok, _ = base_mod.content_evidence(NEW_MD, RENDERED_NEW[:20])
        self.assertFalse(ok, "只剩开头一点点不能算内容一致")

    def test_content_evidence_tolerates_heading_hoisted_to_title_box(self):
        """编辑器把首行 # 标题提到标题框时，正文里没有它也不能判失败。"""
        ok, detail = base_mod.content_evidence(NEW_MD, RENDERED_NEW.split("\n", 1)[1])
        self.assertTrue(ok, detail)

    def test_content_evidence_rejects_appended_body(self):
        """新内容被追加在旧内容后面（只 insertText 没 delete）= 没真正替换，必须判失败。

        旧实现只查「关键片段齐全 + 篇幅不短」，追加场景两项都过 → 假成功。
        """
        ok, detail = base_mod.content_evidence(NEW_MD, OLD_MD + "\n" + RENDERED_NEW)
        self.assertFalse(ok, "新正文被追加在旧正文后面时必须判失败")
        self.assertIn("开头", detail)

    def test_content_evidence_accepts_leading_ui_noise(self):
        """编辑器顶部夹带提示语（未保存/草稿标签）不该误杀——容忍前缀噪声。"""
        ok, detail = base_mod.content_evidence(NEW_MD, "未保存的草稿\n\n" + RENDERED_NEW)
        self.assertTrue(ok, detail)

    def test_key_fragments_are_distinct(self):
        frags = base_mod.key_fragments(NEW_MD)
        self.assertTrue(frags, "长正文必须能挑出关键片段")
        self.assertEqual(len(frags), len(set(frags)), "关键片段不能重复")
        # 比对前会压平（去掉 markdown 记号与空白），所以断言的是压平后的尾标
        self.assertTrue(any("ENDOFNEWBODY" in f for f in frags), frags)

    def test_key_fragments_empty_for_noise_body(self):
        self.assertEqual(base_mod.key_fragments("嗯\n\n# x\n"), [])

    # ---------------- M1：外链与图片不得误杀真成功 ----------------

    def test_flatten_keeps_anchor_text_and_drops_url(self):
        self.assertEqual(
            base_mod._flatten("[参考](https://example.com/docs/x)"), "参考")

    def test_flatten_drops_image_entirely(self):
        """图片在编辑器里是 <img>，innerText 一个字都不留——alt 文本不能进证据。"""
        self.assertEqual(
            base_mod._flatten("看图 ![系统架构示意图](https://example.com/i.png) 结束"),
            "看图结束")

    def test_flatten_keeps_angle_bracketed_types(self):
        """泛型写法 <T> 不是 HTML 标签：T 不能被当标签名删掉（> 本来就会被压掉）。"""
        self.assertEqual(base_mod._flatten("使用 <T> 泛型"), "使用<T泛型")

    def test_flatten_drops_bare_html_tags(self):
        self.assertEqual(
            base_mod._flatten('开头<br/>中间<div class="x">结尾</div>'),
            "开头中间结尾")

    def test_content_evidence_accepts_body_with_links_and_images(self):
        """技术文带外链与图片是常态：回读必须通过，不能被 URL 撑长的行误杀。"""
        ok, detail = base_mod.content_evidence(MD_WITH_LINKS, RENDERED_WITH_LINKS)
        self.assertTrue(ok, detail)

    def test_content_evidence_still_rejects_stale_body_with_links(self):
        """修链接误杀不能顺手把真失败也放过去（旧正文压在前面 = 追加）。"""
        ok, _ = base_mod.content_evidence(MD_WITH_LINKS, OLD_MD + "\n" + RENDERED_WITH_LINKS)
        self.assertFalse(ok)

    # ---------------- M3：短文不许 fail-open ----------------

    def test_key_fragments_are_empty_for_short_line_body(self):
        self.assertEqual(base_mod.key_fragments(SHORT_LINES_MD), [],
                         "每行都短于阈值时确实挑不出片段——这正是 fail-open 的入口")

    def test_content_evidence_short_line_body_is_not_accepted_blindly(self):
        """key_fragments 为空时只剩长度比 = fail-open：目标短文 vs 别人的短文必须判失败。"""
        ok, detail = base_mod.content_evidence(SHORT_LINES_MD, SHORT_LINES_OLD)
        self.assertFalse(ok, "片段检查空转时不能只看篇幅比")
        self.assertNotIn("关键片段齐全", detail, "detail 不能谎称关键片段齐全")

    def test_content_evidence_short_line_body_passes_when_fully_present(self):
        ok, detail = base_mod.content_evidence(SHORT_LINES_MD, SHORT_LINES_RENDERED)
        self.assertTrue(ok, detail)

    # ---------------- m1+m2：首段位置容差 ----------------

    def test_lead_budget_has_no_flat_forty_allowance(self):
        """短标题不再自带 40 字陈旧前缀的免检额度（m1）。

        预算写死成 15 = 首行 3 字 + 固定余量 12（余量见 base._HEAD_LEAD_EXTRA），
        不用常量算出来：这条就是钉死"不再有 40 字地板"这条策略。
        """
        budget = 15
        self.assertLess(budget, 40, "容差必须随首行长度缩放，不能有 40 字的地板")
        ok, _ = base_mod.content_evidence(MD_SHORT_HEAD, "旧" * budget + RENDERED_SHORT_HEAD)
        self.assertTrue(ok, "预算内的编辑器提示语不该误杀")
        ok, detail = base_mod.content_evidence(
            MD_SHORT_HEAD, "旧" * (budget + 1) + RENDERED_SHORT_HEAD)
        self.assertFalse(ok, "超出预算一个字的陈旧前缀必须判失败")
        self.assertIn("开头", detail)

    def test_lead_budget_keeps_own_heading_out_of_the_noise_allowance(self):
        """首行标题仍渲染在正文里时，它自己占掉的那截不能算成「编辑器噪声」。"""
        ok, _ = base_mod.content_evidence(
            MD_SHORT_HEAD, "旧" * 12 + RENDERED_SHORT_HEAD_KEEP)
        self.assertTrue(ok)
        ok, _ = base_mod.content_evidence(
            MD_SHORT_HEAD, "旧" * 13 + RENDERED_SHORT_HEAD_KEEP)
        self.assertFalse(ok)

    def test_lead_budget_boundary_40_char_first_line(self):
        """40 字首行的容差边界：预算 52 内放行，53 判失败。"""
        budget = 52   # 首行 40 字 + 固定余量 12
        ok, _ = base_mod.content_evidence(MD_40_HEAD, "旧" * budget + RENDERED_40_HEAD)
        self.assertTrue(ok)
        ok, _ = base_mod.content_evidence(
            MD_40_HEAD, "旧" * (budget + 1) + RENDERED_40_HEAD)
        self.assertFalse(ok)

    def test_append_detected_when_first_fragment_not_in_top3(self):
        """首段定位不到（pos<0）时追加检测不许静默失效（m2）。"""
        ok, detail = base_mod.content_evidence(
            MD_BULLET_HEAD, BULLET_STALE_PREFIX + RENDERED_BULLET_HEAD)
        self.assertFalse(ok, "首段落不进关键片段时，追加在旧正文后面必须判失败")
        self.assertIn("开头", detail)

    def test_bullet_head_body_accepted_without_stale_prefix(self):
        """控制组：没有陈旧前缀时，列表引导句被渲染成项目符号也不该误杀。"""
        ok, detail = base_mod.content_evidence(MD_BULLET_HEAD, RENDERED_BULLET_HEAD)
        self.assertTrue(ok, detail)

    # ---------------- ratio 边界 ----------------

    def test_ratio_boundary_034_rejected_035_accepted(self):
        """篇幅比：0.35（含）放行、0.35 以下判失败，两侧都要有钉死的用例。"""
        import math

        heads = "".join(
            "第%d段关键内容：这一行足够长，会被选进最长的三段关键片段里当证据。\n\n" % i
            for i in range(1, 4))
        target = heads + "补充行。\n" * 60
        rendered = heads                            # 三段关键内容原样渲染
        t_len = len(base_mod._flatten(target))
        h_len = len(base_mod._flatten(rendered))
        at_ok = math.ceil(0.35 * t_len)              # 刚好 ≥ 0.35 的实际字数
        at_no = at_ok - 1
        self.assertGreaterEqual(at_ok / t_len, 0.35)
        self.assertLess(at_no / t_len, 0.35)
        ok, _ = base_mod.content_evidence(target, rendered + "页" * (at_ok - h_len))
        self.assertTrue(ok, "篇幅比刚好 ≥ 0.35 必须放行")
        ok, detail = base_mod.content_evidence(
            target, rendered + "页" * (at_no - h_len))
        self.assertFalse(ok, "篇幅比掉到 0.35 以下必须判失败")
        self.assertIn("短于目标", detail)

    # ---------------- m3：标题前缀 ----------------

    def test_title_evidence_rejects_four_char_prefix(self):
        ok, _ = base_mod.title_evidence("完整标题与正文摘要", "完整标")
        self.assertFalse(ok, "4 字前缀不能放行")

    def test_title_evidence_rejects_seven_char_prefix(self):
        ok, _ = base_mod.title_evidence("完整标题与正文摘要", "完整标题与正文")
        self.assertFalse(ok, "7 字前缀仍不能放行")

    def test_title_evidence_accepts_eight_char_prefix(self):
        ok, detail = base_mod.title_evidence("完整标题与正文摘要", "完整标题与正文摘")
        self.assertTrue(ok, detail)

    def test_title_evidence_rejects_longer_actual_with_same_prefix(self):
        """平台只截尾不截头：实际值比目标长就不是截断。"""
        ok, _ = base_mod.title_evidence("完整标题与正文", "完整标题与正文草稿")
        self.assertFalse(ok)

    def test_title_evidence_ignores_whitespace_only_difference(self):
        ok, detail = base_mod.title_evidence("Python 协程最佳实践", "Python协程最佳实践")
        self.assertTrue(ok, detail)

    def test_title_evidence_rejects_mismatch(self):
        ok, detail = base_mod.title_evidence("新标题", "旧标题")
        self.assertFalse(ok)
        self.assertIn("标题", detail)

    def test_wait_for_url_change_raises_when_url_frozen(self):
        ad = PlatformAdapter()
        ad.name = "测试平台"
        page = _FakePage(url="https://x.test/editor/1")
        with self.assertRaises(PlatformError) as cm:
            ad.wait_for_url_change(
                page, "https://x.test/editor/1",
                accept=lambda u: "/p/" in u, timeout=0.05, poll=0.01)
        self.assertIn("没跳到预期地址", str(cm.exception))

    def test_wait_for_url_change_returns_when_navigated(self):
        ad = PlatformAdapter()
        page = _FakePage(url="https://x.test/p/42")
        got = ad.wait_for_url_change(
            page, "https://x.test/editor/1",
            accept=lambda u: "/p/" in u and "/edit" not in u,
            timeout=0.05, poll=0.01)
        self.assertEqual(got, "https://x.test/p/42")

    def test_verify_text_present_raises_when_absent(self):
        ad = PlatformAdapter()
        ad.name = "测试平台"
        page = _FakePage()
        page.body_text = "表单还差必填项"
        with self.assertRaises(PlatformError) as cm:
            ad.verify_text_present(page, ["发布成功"], timeout=0.05, poll=0.01)
        self.assertIn("发布成功", str(cm.exception))

    def test_verify_text_present_returns_matched_text(self):
        ad = PlatformAdapter()
        page = _FakePage()
        page.body_text = "发布成功，您的文章已上线"
        self.assertEqual(
            ad.verify_text_present(page, ["未找到", "发布成功"], timeout=0.05, poll=0.01),
            "发布成功")

    def test_verify_or_raise_raises_platform_error(self):
        ad = PlatformAdapter()
        ad.name = "测试平台"
        with self.assertRaises(PlatformError) as cm:
            ad.verify_or_raise("正文注入", False, "编辑器是空的")
        self.assertIn("正文注入", str(cm.exception))
        self.assertIn("编辑器是空的", str(cm.exception))

    def test_safe_eval_degrades_to_default(self):
        ad = PlatformAdapter()
        page = _FakePage()
        page.evaluate = mock.Mock(side_effect=RuntimeError("Execution context was destroyed"))
        self.assertEqual(ad._safe_eval(page, "whatever", None, ""), "")

    def test_find_text_returns_first_matching_candidate(self):
        self.assertEqual(
            base_mod.find_text("发布成功，您的文章已发布", ["未找到", "发布成功"]),
            "发布成功")

    def test_find_text_returns_empty_when_absent(self):
        self.assertEqual(base_mod.find_text("还差一步：设置分类", ["发布成功"]), "")

    def test_verify_text_present_uses_find_text(self):
        """成功文案匹配必须走共用原语，不允许各适配器各写一套 for 循环。"""
        import inspect

        src = inspect.getsource(base_mod.PlatformAdapter.verify_text_present)
        self.assertIn("find_text", src)


class ZhihuUpdateReadbackTests(unittest.TestCase):
    """V2：知乎原地更新的回读验证。"""

    ARTICLE = {"title": TITLE, "content_md": NEW_MD}

    def _update(self, page, import_ok):
        from core.adapters import zhihu as zhihu_mod

        ad = zhihu_mod.ZhihuAdapter()
        with mock.patch.object(zhihu_mod, "_click_button", return_value="发布"), \
                mock.patch.object(ad, "_import_md_file", return_value=import_ok), \
                mock.patch.object(ad, "save_debug", return_value="dump.html"), \
                mock.patch.object(zhihu_mod.time, "sleep"):
            return ad.update(page, dict(ZHIHU_PUB), dict(self.ARTICLE))

    def test_injection_landing_nothing_raises_before_publish(self):
        """_import_md_file 失败 + _inject_editor 返回成功但正文没换 → 必须报错。"""
        page = _FakePage(editor_text=OLD_MD, title_text=TITLE, persisted=OLD_MD)
        with self.assertRaises(PlatformError) as cm:
            self._update(page, import_ok=False)
        self.assertIn("回读", str(cm.exception))
        self.assertIn("正文", str(cm.exception))

    def test_save_not_persisted_raises(self):
        """正文换进去了、也点了「保存并发布」，但重开编辑器还是旧内容 → 必须报错。"""
        page = _FakePage(editor_text=RENDERED_NEW, title_text=TITLE, persisted=OLD_MD)
        with self.assertRaises(PlatformError) as cm:
            self._update(page, import_ok=True)
        self.assertIn("回读", str(cm.exception))

    def test_update_succeeds_when_readback_matches(self):
        page = _FakePage(editor_text=RENDERED_NEW, title_text=TITLE,
                         persisted=RENDERED_NEW)
        self.assertTrue(self._update(page, import_ok=True))

    def test_readback_never_reopens_the_blank_write_page(self):
        """回读不得开空白写页，也不得靠文章页的「编辑」按钮进编辑器。

        旧实现 `_readback_editor` 用 edit_url or post_url（与 update 的取值顺序
        相反）：新文章首次 autosave 未分配 id 时 edit_url 就是通用 /write，
        打开后是空白编辑器，读到空正文再把配置问题报成"选择器失效"。

        2026-09-27 真机又测出另一半：文章页上 button:has-text("编辑") 命中的是
        页头/搜索区的另一个按钮，点完跳到 www.zhihu.com/search?...，
        于是报「页面回读到空内容（……或页面已跳走）」。所以进编辑器只能走
        拼出来的 /p/<id>/edit，文章页本身不在候选里。
        """
        from core.adapters import zhihu as zhihu_mod

        ad = zhihu_mod.ZhihuAdapter()
        pub = {
            "post_url": ZHIHU_PUB["post_url"],
            "edit_url": "https://zhuanlan.zhihu.com/write",   # 竞态值：通用写页
        }
        page = _FakePage(url="about:blank", editor_text=RENDERED_NEW,
                         title_text=TITLE, persisted=RENDERED_NEW)
        with mock.patch.object(zhihu_mod, "_click_button", return_value="保存并发布"), \
                mock.patch.object(ad, "_import_md_file", return_value=True), \
                mock.patch.object(ad, "save_debug", return_value="dump.html"), \
                mock.patch.object(zhihu_mod.time, "sleep"):
            self.assertTrue(ad.update(page, dict(pub), dict(self.ARTICLE)))
        self.assertNotIn("zhuanlan.zhihu.com/write", "".join(page.gotos),
                         "回读绝不能打开空白写页")
        self.assertNotIn("www.zhihu.com/search", "".join(page.gotos),
                         "进编辑器不能靠文章页的「编辑」按钮（会跳搜索页）")
        for u in page.gotos:
            self.assertTrue(u.endswith("/edit"), "只能走 /p/<id>/edit，实际：%s" % u)



class ZhihuPublishEditUrlTests(unittest.TestCase):
    """M2：publish 拿 post_id 后必须回写确定的编辑地址，不留竞态值。"""

    def test_publish_writes_back_deterministic_edit_url(self):
        from core.adapters import zhihu as zhihu_mod

        ad = zhihu_mod.ZhihuAdapter()
        page = _FakePage(url="https://zhuanlan.zhihu.com/write",
                         editor_text=RENDERED_NEW, title_text=TITLE)
        post_url = "https://zhuanlan.zhihu.com/p/2087370000076220077"
        page.on_navigate = lambda p: setattr(p, "url", post_url)
        with mock.patch.object(ad, "_import_md_file", return_value=True), \
                mock.patch.object(ad, "save_debug", return_value="dump.html"), \
                mock.patch.object(zhihu_mod.time, "sleep"):
            r = ad.publish(page, {"title": TITLE, "content_md": NEW_MD})
        self.assertEqual(r["post_id"], "2087370000076220077")
        self.assertEqual(
            r["edit_url"],
            "https://zhuanlan.zhihu.com/p/2087370000076220077/edit",
            "edit_url 必须是拼出来的确定地址，不能是点按钮那一刻的竞态值")


class ZhihuPublishReadbackTests(unittest.TestCase):
    """V2b：知乎发布也必须先证明正文真的进了编辑器再点发布。"""

    def test_publish_raises_when_editor_never_filled(self):
        from core.adapters import zhihu as zhihu_mod

        ad = zhihu_mod.ZhihuAdapter()
        page = _FakePage(url="about:blank", editor_text=OLD_MD, title_text=TITLE)
        with mock.patch.object(ad, "_import_md_file", return_value=False), \
                mock.patch.object(ad, "save_debug", return_value="dump.html"), \
                mock.patch.object(ad, "PUBLISH_VERIFY_TIMEOUT", 0.05), \
                mock.patch.object(ad, "PUBLISH_VERIFY_POLL", 0.01), \
                mock.patch.object(zhihu_mod.time, "sleep"):
            with self.assertRaises(PlatformError) as cm:
                ad.publish(page, {"title": TITLE, "content_md": NEW_MD})
        self.assertIn("正文注入", str(cm.exception))
        self.assertNotIn("发布", "".join(page.clicks),
                         "正文没进去就不该点发布按钮")


class JuejinPublishReadbackTests(unittest.TestCase):
    """V3：掘金发布以「已发布列表接口」为准，URL 跳 /post/ 只是线索。"""

    ARTICLE = {"title": TITLE, "content_md": NEW_MD, "summary": "摘要"}
    DRAFT_ID = "7300000000000000001"

    def _patched(self, listed):
        from core.adapters import juejin as jj_mod

        ad = jj_mod.JuejinAdapter()

        def _get(_page, url):
            if "user_api" in url:
                return {"data": {"user_id": "7300000000000000000"}}
            return {"data": listed}

        stack = mock.patch.multiple(
            ad,
            api_post=lambda *a, **k: {"data": {"id": self.DRAFT_ID}},
            api_get=_get,
            save_debug=lambda *a: "dump.html",
            VERIFY_TRIES=2,
            VERIFY_PAUSE=0,
        )
        return ad, stack, mock.patch(
            "core.adapters.juejin._resolve_tag_ids", return_value=["7104"]
        ), mock.patch("core.adapters.juejin.time.sleep")

    def test_publish_raises_when_article_not_in_published_list(self):
        ad, p1, p2, p3 = self._patched(listed=[])
        page = _FakePage(url="https://juejin.cn/editor/drafts/1")
        with p1, p2, p3:
            with self.assertRaises(PlatformError) as cm:
                ad.publish(page, dict(self.ARTICLE), {})
        self.assertIn("未生效", str(cm.exception))
        self.assertIn(self.DRAFT_ID, str(cm.exception))

    def test_publish_returns_success_only_when_list_shows_status2(self):
        """标题兜底要 status=2 且比本次 publish 更新（article_info.ctime）。"""
        listed = [{"title": TITLE, "article_id": "7304899000000000002",
                   "article_info": {"status": 2, "ctime": int(time.time())}}]
        ad, p1, p2, p3 = self._patched(listed)
        page = _FakePage(url="https://juejin.cn/editor/drafts/1")
        with p1, p2, p3:
            r = ad.publish(page, dict(self.ARTICLE), {})
        self.assertFalse(r["draft_only"])
        self.assertEqual(r["post_id"], "7304899000000000002")
        self.assertEqual(r["post_url"], "https://juejin.cn/post/7304899000000000002")

    def test_draft_status_is_not_published(self):
        """列表里 status=1（草稿）不算发布成功。"""
        listed = [{"title": TITLE, "article_id": "7304899000000000002",
                   "article_info": {"status": 1}}]
        ad, p1, p2, p3 = self._patched(listed)
        page = _FakePage(url="https://juejin.cn/editor/drafts/1")
        with p1, p2, p3:
            with self.assertRaises(PlatformError) as cm:
                ad.publish(page, dict(self.ARTICLE), {})
        self.assertIn(f"juejin.cn/editor/drafts/{self.DRAFT_ID}", str(cm.exception),
                      "报错必须给出那条已建好的草稿地址")

    def test_same_title_draft_does_not_prove_publish(self):
        """只有标题相同、status 不是 2 → 不能判成功（防"库里已有同名草稿"）。"""
        listed = [{"title": TITLE, "article_id": "7304899000000000003",
                   "article_info": {"status": 1}}]
        ad, p1, p2, p3 = self._patched(listed)
        page = _FakePage(url="https://juejin.cn/editor/drafts/1")
        with p1, p2, p3:
            with self.assertRaises(PlatformError) as cm:
                ad.publish(page, dict(self.ARTICLE), {})
        self.assertIn(f"juejin.cn/editor/drafts/{self.DRAFT_ID}", str(cm.exception))

    # ---------------- C1：强证据（URL 里的 article_id）不被弱证据覆盖 ----------------

    NEW_ID = "7304899000000000009"
    OLD_SAME_TITLE_ID = "7304899000000000004"

    def test_same_title_published_row_never_overrides_url_article_id(self):
        """账号里已有一篇同名 status=2 的旧文章 + URL 给出新 id → 必须判失败。

        旧实现用 `or` 把标题相同当成命中：平台没真发布也能回读到那条旧文章，
        于是返回 draft_only=False + 旧文章 id —— 一次新的假成功。
        """
        listed = [{"title": TITLE, "article_id": self.OLD_SAME_TITLE_ID,
                   "article_info": {"status": 2, "ctime": int(time.time())}}]
        ad, p1, p2, p3 = self._patched(listed)
        page = _FakePage(url="https://juejin.cn/editor/drafts/1")
        # 点完「确定并发布」后 URL 跳到了新文章页 —— 这就是本次发布的强证据
        page.on_navigate = lambda p: setattr(
            p, "url", f"https://juejin.cn/post/{self.NEW_ID}")
        with p1, p2, p3:
            with self.assertRaises(PlatformError) as cm:
                ad.publish(page, dict(self.ARTICLE), {})
        msg = str(cm.exception)
        self.assertIn("未生效", msg)
        self.assertIn(f"juejin.cn/editor/drafts/{self.DRAFT_ID}", msg)
        self.assertIn(self.NEW_ID, msg, "报错要说明本次页面给出的 id 是哪个")
        self.assertNotIn(f"post_id={self.OLD_SAME_TITLE_ID}", msg)

    def test_find_published_honours_url_article_id_only(self):
        ad, p1, _p2, p3 = self._patched(
            listed=[{"title": TITLE, "article_id": self.NEW_ID,
                     "article_info": {"status": 2}}])
        page = _FakePage(url=f"https://juejin.cn/post/{self.NEW_ID}")
        with p1, p3:
            self.assertEqual(
                ad._find_published(page, TITLE, self.NEW_ID, since=time.time() - 60),
                self.NEW_ID)

    def test_title_fallback_rejects_stale_published_row(self):
        """URL 没给 id 时才允许标题兜底，且必须比本次 publish 更新的那条才算。"""
        now = int(time.time())
        listed = [{"title": TITLE, "article_id": self.OLD_SAME_TITLE_ID,
                   "article_info": {"status": 2, "ctime": now - 86400}}]
        ad, p1, _p2, p3 = self._patched(listed)
        page = _FakePage(url="https://juejin.cn/editor/drafts/1")
        with p1, p3:
            self.assertEqual(
                ad._find_published(page, TITLE, "", since=now - 1), "")

    def test_title_fallback_accepts_row_newer_than_publish_start(self):
        now = int(time.time())
        listed = [{"title": TITLE, "article_id": self.NEW_ID,
                   "article_info": {"status": 2, "ctime": (now + 5) * 1000}}]
        ad, p1, _p2, p3 = self._patched(listed)
        page = _FakePage(url="https://juejin.cn/editor/drafts/1")
        with p1, p3:
            self.assertEqual(
                ad._find_published(page, TITLE, "", since=now - 1), self.NEW_ID)

    def test_title_fallback_rejects_row_without_readable_time(self):
        """article_info 里读不到 ctime/mtime 就没有时效证据，不能拿来当成功。"""
        listed = [{"title": TITLE, "article_id": self.NEW_ID,
                   "article_info": {"status": 2}}]
        ad, p1, _p2, p3 = self._patched(listed)
        page = _FakePage(url="https://juejin.cn/editor/drafts/1")
        with p1, p3:
            self.assertEqual(
                ad._find_published(page, TITLE, "", since=time.time() - 60), "")

    def test_publish_uses_publish_start_time_as_freshness_floor(self):
        """发布链路必须把"本次 publish 的起点"传给回读（否则 stale 判定形同虚设）。

        走真实分支：URL 没跳 /post/ → 只有标题兜底可用，而列表里那条同名文章
        是本次发布之前就存在的旧文，必须判失败。
        """
        now = int(time.time())
        listed = [{"title": TITLE, "article_id": self.OLD_SAME_TITLE_ID,
                   "article_info": {"status": 2, "ctime": now - 86400}}]
        ad, p1, p2, p3 = self._patched(listed)
        page = _FakePage(url="https://juejin.cn/editor/drafts/1")
        with p1, p2, p3:
            with self.assertRaises(PlatformError) as cm:
                ad.publish(page, dict(self.ARTICLE), {})
        self.assertIn("未生效", str(cm.exception))

    def test_verify_api_failure_still_carries_draft_url(self):
        """回读接口本身挂了，错误消息里也必须能拿到那条已建好的草稿。"""
        from core.adapters import juejin as jj_mod
        from core.adapters.base import PlatformError as PE

        ad = jj_mod.JuejinAdapter()

        def _get(_page, url):
            if "user_api" in url:
                return {"data": {"user_id": "7300000000000000000"}}
            raise PE("GET 查询列表 -> HTTP 503")

        with mock.patch.multiple(
                ad,
                api_post=lambda *a, **k: {"data": {"id": self.DRAFT_ID}},
                api_get=_get,
                save_debug=lambda *a: "dump.html",
        ), mock.patch("core.adapters.juejin._resolve_tag_ids", return_value=["7104"]), \
                mock.patch("core.adapters.juejin.time.sleep"):
            with self.assertRaises(PlatformError) as cm:
                ad.publish(_FakePage(url="https://juejin.cn/editor/drafts/1"),
                           dict(self.ARTICLE), {})
        msg = str(cm.exception)
        self.assertIn("503", msg)
        self.assertIn(self.DRAFT_ID, msg)
        self.assertIn("无法确认是否发布成功", msg)


class JuejinUpdateReadbackTests(unittest.TestCase):
    """V3b：掘金原地更新同样要回读，不能点了就 return True。"""

    def _update(self, page):
        from core.adapters import juejin as jj_mod

        ad = jj_mod.JuejinAdapter()
        with mock.patch("core.adapters.juejin._click_text", return_value="确定并发布"), \
                mock.patch.object(ad, "set_editor_content", return_value="codemirror"), \
                mock.patch.object(ad, "save_debug", lambda *a: "dump.html"), \
                mock.patch.object(jj_mod.time, "sleep"):
            return ad.update(page, {"post_id": "1"},
                             {"title": TITLE, "content_md": NEW_MD})

    def test_update_raises_when_editor_readback_is_stale(self):
        page = _FakePage(url="https://juejin.cn/editor/drafts/1",
                         editor_text=NEW_MD, title_text=TITLE, persisted=OLD_MD)
        with self.assertRaises(PlatformError) as cm:
            self._update(page)
        self.assertIn("回读", str(cm.exception))

    def test_update_succeeds_when_readback_matches(self):
        page = _FakePage(url="https://juejin.cn/editor/drafts/1",
                         editor_text=NEW_MD, title_text=TITLE, persisted=NEW_MD)
        self.assertTrue(self._update(page))


class SegmentFaultPublishReadbackTests(unittest.TestCase):
    """V4：思否发布必须区分「草稿已建但未发布」与「发布成功」。"""

    ARTICLE = {"title": TITLE, "content_md": NEW_MD}
    DRAFT_ID = 1220000048319538
    WRITE_URL = f"https://segmentfault.com/write?draftId={DRAFT_ID}"

    def _patched(self):
        from core.adapters import segmentfault as sf_mod

        ad = sf_mod.SegmentFaultAdapter()
        stack = mock.patch.multiple(
            ad,
            get_cookie=lambda _p, _n: "PHPSESSID",
            api_post=lambda *a, **k: {"id": self.DRAFT_ID, "object_id": 0},
            save_debug=lambda *a: "dump.html",
            SUBMIT_VERIFY_TIMEOUT=0.05,
            SUBMIT_VERIFY_POLL=0.01,
        )
        return ad, stack, mock.patch("core.adapters.segmentfault.time.sleep")

    def _page(self, body="", url=None, toast=""):
        p = _FakePage(url=url or self.WRITE_URL, editor_text=NEW_MD, title_text=TITLE)
        p.body_text = body
        p.toast_text = toast
        return p

    def test_disabled_submit_raises_draft_not_published(self):
        ad, p1, p2 = self._patched()
        page = self._page("请选择文章分类")
        page.submit_disabled = True
        with p1, p2:
            with self.assertRaises(PlatformError) as cm:
                ad.publish(page, dict(self.ARTICLE), {})
        msg = str(cm.exception)
        self.assertIn("草稿已创建", msg)
        self.assertIn("未发布", msg)
        self.assertIn(f"draftId={self.DRAFT_ID}", msg)
        # 必须真的走的是「按钮 disabled」这条分支，而不是兜底的 unconfirmed
        self.assertIn("disabled", msg)

    def test_transient_disabled_button_is_not_a_publish_failure(self):
        """提交后按钮会短暂 disabled（处理中），不能就此判定没发出去。"""
        ad, p1, p2 = self._patched()
        page = self._page("")   # 第一轮还没有成功提示
        page.submit_disabled = True
        probes = []

        def _submit_disabled(pg):
            probes.append(1)
            pg.toast_text = "发布成功，您的文章已发布"  # 下一轮才出成功提示
            return True

        with p1, p2, mock.patch.object(ad, "_submit_disabled", _submit_disabled):
            r = ad.publish(page, dict(self.ARTICLE), {})
        self.assertTrue(probes, "disabled 探测必须被调用过")
        self.assertFalse(r["draft_only"])

    def test_navigated_to_article_url_is_success(self):
        ad, p1, p2 = self._patched()
        page = self._page()
        page.on_navigate = lambda p: setattr(
            p, "url", "https://segmentfault.com/a/1190000005123456")
        with p1, p2:
            r = ad.publish(page, dict(self.ARTICLE), {})
        self.assertFalse(r["draft_only"])
        self.assertEqual(r["post_id"], "1190000005123456")
        self.assertEqual(r["post_url"], "https://segmentfault.com/a/1190000005123456")

    def test_success_toast_without_navigation_keeps_url_honest(self):
        ad, p1, p2 = self._patched()
        page = self._page(toast="发布成功，您的文章已发布")
        with p1, p2:
            r = ad.publish(page, dict(self.ARTICLE), {})
        self.assertFalse(r["draft_only"])
        self.assertEqual(r["post_url"], "", "拿不到真实文章页就不能编一个链接")
        self.assertIn("warning", r)

    def test_success_text_outside_toast_is_not_evidence(self):
        """m5：整页 innerText 命中「发布成功」太宽，只认 toast/notification 容器。

        写作页本身满是「发布设置」「发布」字样，草稿列表/历史记录里也可能留着
        上一轮的「发布成功」；拿整页文本当证据等于凭空造一次假成功。
        """
        ad, p1, p2 = self._patched()
        page = self._page("文章发布设置\n发布成功，您的文章已发布")
        with p1, p2:
            with self.assertRaises(PlatformError) as cm:
                ad.publish(page, dict(self.ARTICLE), {})
        msg = str(cm.exception)
        self.assertIn("未发布", msg)
        self.assertIn(f"draftId={self.DRAFT_ID}", msg)

    def test_no_evidence_at_all_raises(self):
        ad, p1, p2 = self._patched()
        page = self._page("还差一步：设置文章分类")
        with p1, p2:
            with self.assertRaises(PlatformError) as cm:
                ad.publish(page, dict(self.ARTICLE), {})
        self.assertIn("未发布", str(cm.exception))
        self.assertIn(f"draftId={self.DRAFT_ID}", str(cm.exception))


class SegmentFaultUpdateReadbackTests(unittest.TestCase):
    """V5：思否原地更新也必须回读。api_post 一返回就 return True 是同一类假成功。"""

    ARTICLE = {"title": TITLE, "content_md": NEW_MD, "tags": "回读, 测试"}
    DRAFT_ID = 1220000048319538

    def _update(self, server_text, title_text=TITLE):
        from core.adapters import segmentfault as sf_mod

        ad = sf_mod.SegmentFaultAdapter()
        page = _ServerCopyPage(
            url=f"https://segmentfault.com/write?draftId={self.DRAFT_ID}",
            editor_text=NEW_MD, title_text=title_text, server_text=server_text)
        with mock.patch.multiple(
                ad,
                get_cookie=lambda _p, _n: "PHPSESSID",
                api_post=lambda *a, **k: {"id": self.DRAFT_ID, "object_id": 0},
                save_debug=lambda *a: "dump.html"), \
                mock.patch.object(sf_mod.time, "sleep"):
            return ad.update(page, {"post_id": self.DRAFT_ID}, dict(self.ARTICLE))

    def test_update_raises_when_server_copy_is_stale(self):
        """API 返回成功但服务端存的还是旧正文 → 必须抛错。"""
        with self.assertRaises(PlatformError) as cm:
            self._update(OLD_MD)
        self.assertIn("回读", str(cm.exception))
        self.assertIn(str(self.DRAFT_ID), str(cm.exception))

    def test_update_raises_when_server_copy_is_empty(self):
        with self.assertRaises(PlatformError) as cm:
            self._update("")
        self.assertIn("空", str(cm.exception))

    def test_update_raises_when_title_not_saved(self):
        with self.assertRaises(PlatformError) as cm:
            self._update(NEW_MD, title_text="旧标题")
        self.assertIn("标题", str(cm.exception))

    def test_update_reads_back_from_served_draft_not_memory(self):
        """回读必须走「重开写作页」这条真往返，不能看当前页面的内存态。"""
        from core.adapters import segmentfault as sf_mod

        ad = sf_mod.SegmentFaultAdapter()
        page = _ServerCopyPage(url="https://segmentfault.com/write?draftId=1",
                               editor_text=NEW_MD, title_text=TITLE,
                               server_text=OLD_MD)
        with mock.patch.multiple(
                ad,
                get_cookie=lambda _p, _n: "PHPSESSID",
                api_post=lambda *a, **k: {"id": self.DRAFT_ID},
                save_debug=lambda *a: "dump.html"), \
                mock.patch.object(sf_mod.time, "sleep"):
            with self.assertRaises(PlatformError) as cm:
                ad.update(page, {"post_id": self.DRAFT_ID}, dict(self.ARTICLE))
        msg = str(cm.exception)
        self.assertIn("回读", msg)
        self.assertIn(f"draftId={self.DRAFT_ID}", msg,
                      "报错必须带草稿地址：人工接手要知道去哪儿核对")
        self.assertGreaterEqual(page.goto_count, 1,
                                "没有重开写作页就等于没做往返验证")

    def test_update_succeeds_when_readback_matches(self):
        self.assertTrue(self._update(NEW_MD))


class PublicationLedgerTests(unittest.TestCase):
    """V6（M4）：适配器抛 PlatformError 时 publications.status 必须是 failed。

    这是本批唯一没被覆盖的接缝——上层会不会把 PlatformError 吞掉、让台账
    停在上一次的 "ok"（于是「库里显示已同步成功、平台正文是旧的」成批出现）。
    绕开 Hub.__init__（TaskManager 起线程 + 浏览器池），只测记账这一段。
    """

    ARTICLE = {"title": TITLE, "content_md": NEW_MD, "summary": "摘要"}

    def setUp(self):
        import tempfile

        from core import db
        from core.service import Hub

        self._db = db
        tmp = tempfile.TemporaryDirectory(prefix="hub_verify_")
        self.addCleanup(tmp.cleanup)
        self.hub = Hub.__new__(Hub)
        self.hub.demo = False
        self.hub.conn = db.connect(Path(tmp.name) / "hub.db")
        self.addCleanup(self.hub.conn.close)
        self.article_id = self._db.create_article(
            self.hub.conn, TITLE, NEW_MD, summary="摘要")

    def _seed_publication(self, status):
        self._db.upsert_publication(
            self.hub.conn, self.article_id, "zhihu", "default",
            status=status, post_id="2087370000076220077", draft_only=0,
            content_hash="stale-hash-from-last-sync")
        rows = self._db.get_publications(
            self.hub.conn, article_id=self.article_id, platform="zhihu")
        self.assertEqual(len(rows), 1)
        return rows[0]

    def _with_adapter_raising(self, err):
        def _with_adapter(platform, account, fn, page_hook=None):
            class _Ad:
                def update(self, page, pub, article):
                    raise err

            return fn(_Ad(), None)

        self.hub._with_adapter = _with_adapter

    def _status(self):
        row = self._db.get_publications(
            self.hub.conn, article_id=self.article_id, platform="zhihu")[0]
        return row["status"], row["last_error"]

    def test_platform_error_marks_publication_failed(self):
        pub = self._seed_publication("ok")
        self._with_adapter_raising(PlatformError("知乎保存后回读未通过"))
        with self.assertRaises(PlatformError):
            self.hub.update_single(
                self.article_id, "zhihu", pub, dict(self.ARTICLE))
        status, last_error = self._status()
        self.assertEqual(status, "failed",
                         "适配器抛 PlatformError 时 status 不能停在 ok")
        self.assertIn("回读", last_error)

    def test_successful_update_marks_publication_ok(self):
        pub = self._seed_publication("failed")

        def _ok(platform, account, fn, page_hook=None):
            class _Ad:
                def update(self, page, pub, article):
                    return True

            return fn(_Ad(), None)

        self.hub._with_adapter = _ok
        r = self.hub.update_single(self.article_id, "zhihu", pub, dict(self.ARTICLE))
        self.assertTrue(r["ok"])
        self.assertEqual(self._status()[0], "ok")

    def test_failed_job_is_recorded(self):
        pub = self._seed_publication("ok")
        self._with_adapter_raising(PlatformError("思否提交按钮点不到"))
        with self.assertRaises(PlatformError):
            self.hub.update_single(
                self.article_id, "zhihu", pub, dict(self.ARTICLE))
        rows = self.hub.conn.execute(
            "SELECT status, message FROM jobs WHERE article_id=? AND platform='zhihu'"
            " ORDER BY id DESC LIMIT 1", (self.article_id,)).fetchall()
        self.assertTrue(rows)
        self.assertEqual(rows[0]["status"], "failed")
        self.assertIn("点不到", rows[0]["message"])


if __name__ == "__main__":
    unittest.main()
