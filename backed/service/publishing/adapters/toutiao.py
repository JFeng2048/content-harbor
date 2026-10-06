# -*- coding: utf-8 -*-
"""头条号适配器：mp 后台 UI 注入（自研富文本编辑器）。

- 未登录访问发布页会跳 sso.toutiao.com —— 跳转判定登录态
- 标题 textarea + contenteditable 编辑器 HTML 粘贴 + button.publish-btn
- 正式发布走「预览并发布」→ 预览页再点一次「发布」，弹窗部分交人工
"""

import time

from service.publishing.adapters.base import (
    PASTE_HTML_JS,
    PlatformAdapter,
    PlatformError,
    md_to_html,
    register,
)

TITLE_SEL = 'textarea[placeholder*="请输入文章标题"]'
EDITOR_SEL = 'div[contenteditable="true"]'


@register
class ToutiaoAdapter(PlatformAdapter):
    id = "toutiao"
    name = "头条号"
    login_url = "https://sso.toutiao.com/login?service=https%3A%2F%2Fmp.toutiao.com%2F"

    # 页面结构版本（第三刀加固）：平台改版时更新此版本并同步 key_selectors
    selector_version = "2026-09"
    key_selectors = {'editor': '.ProseMirror, .syl-editor', 'title_input': "input[placeholder*='标题']"}
    home_url = "https://mp.toutiao.com/profile_v4/graphic/publish"
    list_url = "https://mp.toutiao.com/profile_v4/graphic/articles"
    new_url = "https://mp.toutiao.com/profile_v4/graphic/publish"

    # ---------------- 登录态 ----------------

    DOMAIN = "toutiao.com"

    def check_auth(self, page) -> bool:
        # mp 后台未登录：要么跳 sso，要么 SPA 内部跳到 /auth/page/login 且不渲染编辑器。
        # 已在域内时优先读 URL，避免打断用户扫码
        try:
            url = page.url
            if self.DOMAIN not in url:
                page.goto(self.new_url, timeout=60000, wait_until="domcontentloaded")
                time.sleep(2)
                url = page.url
            if "sso.toutiao.com" in url or "/auth/page/login" in url:
                return False
            # 编辑器标题框出现才算真正可写（SPA 可能仍在渲染登录组件）
            try:
                page.wait_for_selector(TITLE_SEL, timeout=10000)
                return True
            except Exception:
                return False
        except Exception:
            return False

    # ---------------- 列表 ----------------


    # ---------------- 发布 ----------------

    def publish(self, page, article, options=None):
        options = options or {}
        page.goto(self.new_url, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_selector(TITLE_SEL, timeout=30000)
        time.sleep(2)

        # 标题（头条限 30 字）
        page.fill(TITLE_SEL, article["title"][:30])

        # 正文
        html = md_to_html(article.get("content_md", ""))
        ok = page.evaluate(PASTE_HTML_JS, [EDITOR_SEL, html])
        if not ok:
            self.save_debug(page, "toutiao_no_editor")
            raise PlatformError("找不到头条号正文编辑器，可能改版或未登录")
        time.sleep(4)

        if options.get("draft_only"):
            # 头条编辑器会自动存草稿，草稿箱在内容管理页
            return {"post_id": "", "post_url": "", "edit_url": self.list_url,
                    "draft_only": True}

        try:
            page.click("button.publish-btn", timeout=8000)
            time.sleep(3)
            # 预览页/确认弹层里再点一次「发布」
            for t in ("发布", "确认发布", "确定"):
                try:
                    page.locator(f"button:has-text(\"{t}\")").first.click(timeout=4000)
                    break
                except Exception:
                    continue
            time.sleep(3)
        except Exception:
            self.save_debug(page, "toutiao_publish_btn")
            raise PlatformError("点了发布但没成功，内容已填好，去浏览器手动确认")

        return {"post_id": "", "post_url": page.url if "article" in page.url else "",
                "edit_url": self.list_url, "draft_only": False}

    # ---------------- 原地更新 ----------------

    def update(self, page, pub, article):
        raise PlatformError("头条号暂不支持原地更新，请删除后重发")
