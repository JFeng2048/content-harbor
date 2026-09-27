# -*- coding: utf-8 -*-
"""SegmentFault 思否适配器：API 建草稿 + 写作页点发布。

- 草稿接口 /gateway/draft 只要 cookie（token 传 PHPSESSID），可靠
- 正式公开发布的接口未公开稳定，走写作页 UI 点「发布」
- 点完「提交」必须回读（2026-09）：提交按钮在必填态没满足时是 disabled，
  点不动也会掉进旧的成功分支。结果分三档，证不出来就抛错：
    published      —— URL 跳到 /a/<id>，或页面出现成功文案
    not_submitted  —— 提交按钮 disabled（草稿已建但根本没发出去）
    unconfirmed    —— 点了，但既没跳转也没有成功提示
- 原地更新同样要回读：api_post 返回 2xx 只说明"请求被受理"，不说明草稿真被
  改写，所以改完必须重开该草稿的写作页把编辑器内容读回来比对
"""

import time

from core.adapters.base import (
    PlatformAdapter,
    PlatformError,
    find_text,
    register,
)

HOST = "https://segmentfault.com"
EDITOR_SEL = ".CodeMirror"          # 写作页正文编辑器
TITLE_SEL = 'input[placeholder*="标题"]'   # 写作页标题输入框


@register
class SegmentFaultAdapter(PlatformAdapter):
    id = "segmentfault"
    name = "思否"
    login_url = "https://segmentfault.com/user/login"

    # 页面结构版本（第三刀加固）：平台改版时更新此版本并同步 key_selectors
    selector_version = "2026-09b"
    key_selectors = {'editor': '.CodeMirror, .ProseMirror', 'title_input': "input[placeholder*='标题']",
                     # 2026-09 实测：写作页提交按钮文案是「提交」，不是「发布」；
                     # 用 text=发布 会命中 14 个无关元素（发布设置等）导致点错。
                     'publish_btn': "button:has-text('提交')"}
    home_url = "https://segmentfault.com/write"
    list_url = "https://segmentfault.com/user/articles"
    new_url = "https://segmentfault.com/write"

    # 提交后的回读轮询参数（提成类属性，便于回归测试缩短）
    SUBMIT_VERIFY_TIMEOUT = 15
    SUBMIT_VERIFY_POLL = 1.5
    # 「已发布」的页面级证据：URL 跳到 /a/<id>，或出现这些成功文案
    SUCCESS_TEXTS = ("发布成功", "发表成功", "文章已发布")
    # 成功文案只在 toast / notification 类容器里才算证据（2026-09 审查 m5）。
    # 旧实现拿整页 innerText 找「发布成功」，写作页本身就满是「发布设置」「发布」
    # 字样，草稿列表/历史记录里也可能留着上一轮的「发布成功」——那是凭空造出来的
    # 假成功。取交集的另一条路（URL 里没有 draftId）与下面 URL 判定重复，
    # 这里选容器收敛：不限定容器就只能靠一次线上实测确认思否到底会不会在
    # 发布成功后仍保留 draftId 参数（保留则只能等超时），不做无依据的假设。
    SUCCESS_TEXT_SELECTORS = (
        ".toast", ".Toast", ".toast-message", ".toast__message",
        "[class*='toast']", "[class*='Toast']",
        ".ant-message", ".ant-message-notice", ".ant-notification-notice",
        ".el-message", ".el-notification", ".layui-layer-msg", ".layui-layer",
        "[role='alert']", "[role='status']", ".notification", ".alert",
    )

    # ---------------- 登录态 ----------------

    DOMAIN = "segmentfault.com"

    def check_auth(self, page) -> bool:
        # 未登录访问 /write 会被跳到 /user/login。
        # 已在域内时只读 URL 判定，不 goto（避免打断扫码）
        try:
            url = page.url
            if self.DOMAIN not in url:
                page.goto(self.new_url, timeout=60000, wait_until="domcontentloaded")
                url = page.url
                time.sleep(1.5)
            return "/user/login" not in url
        except Exception:
            return False

    # ---------------- 列表 ----------------


    # ---------------- 回读验证 ----------------

    def _submit_disabled(self, page):
        """可见的「提交/发布」按钮是不是全都 disabled。找不到按钮返回 False。"""
        js = """/* hub:submit-disabled */ () => {
            const bs = [...document.querySelectorAll('button')]
                .filter(b => b.offsetParent !== null
                         && /提交|发布/.test(b.innerText || b.textContent || ''));
            if (!bs.length) return false;
            return bs.every(b => b.disabled
                             || b.getAttribute('aria-disabled') === 'true');
        }"""
        return self._safe_eval(page, js, None, False) is True

    def _success_toast_text(self, page):
        """只读 toast/notification 类容器里的文本。页面没有这类容器就返回空串。

        取不到证据不是「验证通过」——空串交给 verify_or_raise 判失败。
        """
        js = """/* hub:toast-text */ (sels) => {
            const out = [];
            for (const s of sels) {
                let nodes = [];
                try { nodes = document.querySelectorAll(s); } catch (e) { continue; }
                for (const el of nodes) {
                    if (el.offsetParent === null && el.getClientRects().length === 0) continue;
                    const t = (el.innerText || el.textContent || '').trim();
                    if (t) out.push(t);
                }
            }
            return out.join('\\n');
        }"""
        return self._safe_eval(
            page, js, list(self.SUCCESS_TEXT_SELECTORS), "") or ""

    def _submit_verdict(self, page, draft_id):
        """回读判定提交结果，返回 (verdict, detail)。

        verdict ∈ {published, not_submitted, unconfirmed}。

        证据强度：URL 离开写作页（draftId 消失）是强证据；toast 容器里的成功
        文案是弱证据，只在 URL 还没跳时兜底，且必须落在 toast/notification
        容器里（见 SUCCESS_TEXT_SELECTORS 的说明）。

        disabled 要连续两轮都成立才算 not_submitted：提交后按钮会短暂进入
        处理中（disabled）状态，只看一轮会把"正在发"误判成"发不出去"。
        """
        deadline = time.time() + self.SUBMIT_VERIFY_TIMEOUT
        why = ""
        disabled_streak = 0
        while time.time() < deadline:
            url = page.url or ""
            if f"draftId={draft_id}" not in url:
                return "published", f"页面已离开写作页（{url}）"
            hit = find_text(self._success_toast_text(page), self.SUCCESS_TEXTS)
            if hit:
                return "published", f"成功提示出现在提示容器内「{hit}」"
            disabled_streak = (disabled_streak + 1 if self._submit_disabled(page)
                               else 0)
            if disabled_streak >= 2:
                # 必填态没满足，按钮压根点不动——这是"草稿已建但没发布"，
                # 不该继续等下去，也绝不能当成功。
                return "not_submitted", "提交按钮持续处于 disabled 状态（必填项没满足，点不动）"
            why = f"{self.SUBMIT_VERIFY_TIMEOUT}s 内既没跳到文章页，也没出现成功文案"
            time.sleep(self.SUBMIT_VERIFY_POLL)
        return "unconfirmed", why

    # ---------------- 发布 ----------------

    def publish(self, page, article, options=None):
        options = options or {}
        token = self.get_cookie(page, "PHPSESSID")
        if not token:
            raise PlatformError("思否登录态缺失（没有 PHPSESSID），先登录")

        res = self.api_post(
            page, f"{HOST}/gateway/draft",
            {"title": article["title"], "tags": options.get("tags") or [],
             "text": article.get("content_md", ""),
             "object_id": "", "type": "article", "language": "", "cover": ""},
            headers={"token": token})
        draft_id = res.get("id") if isinstance(res, dict) else None
        if not draft_id:
            raise PlatformError(f"思否创建草稿失败: {str(res)[:200]}")

        if options.get("draft_only"):
            return {"post_id": str(draft_id), "post_url": "",
                    "edit_url": f"{HOST}/write?draftId={draft_id}", "draft_only": True}

        # 打开草稿进写作页，Markdown 编辑器（CodeMirror）里点发布
        page.goto(f"{HOST}/write?draftId={draft_id}", timeout=60000,
                  wait_until="domcontentloaded")
        page.wait_for_selector(".CodeMirror", timeout=30000)
        time.sleep(3)

        try:
            # 提交按钮优先按 key_selectors 精确匹配，退回文案候选。
            # 必须用 locator().first + :visible：写作页有 2 个「提交」按钮
            # （一个隐藏），page.click(选择器) 会撞 Playwright 严格模式直接报错。
            clicked = False
            for sel in ("button:has-text('提交'):visible",
                        "button:has-text('发布'):visible"):
                loc = page.locator(sel).first
                if loc.count() == 0:
                    continue
                try:
                    # aqg: top-level boundary 候选按钮点不到就换下一个
                    loc.click(timeout=5000)
                    clicked = True
                    break
                except Exception:
                    continue
            if not clicked:
                raise PlatformError("提交按钮点不到")
            time.sleep(1.5)
            # 可能弹分类/标签确认弹层，能点就点。
            # 已经跳到文章页就别再点了——那时的「确定」是文章页上的无关按钮。
            for t in ("确定", "确认发布", "发布"):
                if f"draftId={draft_id}" not in (page.url or ""):
                    break
                # aqg: top-level boundary 确认弹层文案随版本变，点不到就跳过
                try:
                    page.locator("text=%s" % t).first.click(timeout=3000)
                    break
                except Exception:
                    continue
            # aqg: top-level boundary 存现场截图 + 抛可读错误（草稿不丢，人工可续）
        except Exception as e:
            self.save_debug(page, "sf_publish_btn")
            raise PlatformError(f"思否写作页提交按钮操作失败（{str(e)[:60]}），"
                                f"草稿已建好：{HOST}/write?draftId={draft_id}，"
                                f"可手动发布")
        time.sleep(3)

        # 回读验证：区分「草稿已建但未发布」与「发布成功」。旧实现不管点没点动
        # 都返回 draft_only=False + 一个拿草稿 ID 拼出来的假文章页链接。
        verdict, why = self._submit_verdict(page, draft_id)
        if verdict != "published":
            self.save_debug(page, "sf_publish_unconfirmed")
            raise PlatformError(
                f"思否草稿已创建但未发布（{why}）。"
                f"草稿地址：{HOST}/write?draftId={draft_id}，"
                f"请在浏览器里补齐必填项后手动点「提交」。")

        # 文章页 ID 只有跳到 /a/<id> 才是真的；只拿到成功文案时不编链接。
        url = page.url or ""
        article_id = ""
        if "/a/" in url:
            article_id = url.split("/a/")[-1].split("?")[0].split("/")[0]
        out = {"post_id": article_id or str(draft_id),
               "post_url": f"{HOST}/a/{article_id}" if article_id else "",
               "edit_url": f"{HOST}/write?draftId={draft_id}", "draft_only": False}
        if not article_id:
            # 只有成功文案没拿到链接：发布确实发生了，但文章页地址拿不到，
            # 宁可留空也不拿草稿 ID 编一个 /a/<草稿ID> 的假链接。
            out["warning"] = (f"思否已发布（{why}），但页面没给出文章页地址，"
                              f"post_url 留空；post_id 暂记草稿 ID {draft_id}，"
                              f"可到 {HOST}/user/articles 核对真实 ID")
        return out

    # ---------------- 原地更新 ----------------

    def update(self, page, pub, article):
        """API 改草稿 → 重开写作页回读（verify-after-act）。

        旧实现是 api_post 一返回就 return True，响应体整个丢掉：平台没真存下
        也照样被上层 update_single 记成 status="ok"（那一层丢弃适配器返回值，
        直接按成功记账，所以这里只能抛错，没有"返回 False"这条路）。
        API 回执不算证据——必须重开该草稿的写作页，把编辑器里的正文与标题读回来。
        """
        draft_id = pub.get("post_id")
        if not draft_id:
            raise PlatformError("思否原地更新需要 post_id")
        token = self.get_cookie(page, "PHPSESSID")
        if not token:
            raise PlatformError("思否登录态缺失（没有 PHPSESSID），先登录")
        tags = [t.strip() for t in (article.get("tags") or "").split(",") if t.strip()]
        self.api_post(
            page, f"{HOST}/gateway/draft",
            {"title": article["title"], "tags": tags,
             "text": article.get("content_md", ""),
             "object_id": draft_id, "type": "article", "language": "", "cover": ""},
            headers={"token": token})
        time.sleep(1)

        md_content = article.get("content_md", "")
        url = f"{HOST}/write?draftId={draft_id}"
        try:
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_selector(EDITOR_SEL, timeout=30000)
            time.sleep(3)
            self.require_content(
                page, md_content, article["title"],
                EDITOR_SEL, TITLE_SEL, "保存后回读")
        # aqg: top-level boundary 重开页面/比对任何一环失败都先存现场再抛，
        # 错误里必须带草稿地址：人工接手时要知道去哪儿核对
        except PlatformError as e:
            self.save_debug(page, "sf_update_unverified")
            raise PlatformError(
                f"{e}｜未能确认草稿 {draft_id} 是否真的更新成功，"
                f"请人工核对 {url}")
        return True
