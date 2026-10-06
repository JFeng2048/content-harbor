# -*- coding: utf-8 -*-
"""开源中国 OSCHINA 适配器：写作页 UI 注入（UEditor iframe 富文本）。

- 写作页 my.oschina.net/blog/write 需登录，未登录 404/跳登录 —— 可做跳转判定
- 编辑器是 UEditor（iframe），往 iframe body 粘贴 HTML
- 发布按钮 div.button_publish.item.editor-btn（新版编辑器）
"""

import time

from service.publishing.adapters.base import (
    PASTE_HTML_JS,
    PlatformAdapter,
    PlatformError,
    md_to_html,
    register,
)

HOME = "https://my.oschina.net"


@register
class OschinaAdapter(PlatformAdapter):
    id = "oschina"
    name = "开源中国"
    login_url = "https://www.oschina.net/home/login"

    # 页面结构版本（第三刀加固）：平台改版时更新此版本并同步 key_selectors
    selector_version = "2026-09"
    key_selectors = {'editor': '.CodeMirror, .bytemd', 'title_input': "input[placeholder*='标题']"}
    home_url = HOME
    list_url = "https://my.oschina.net/blog"
    new_url = "https://my.oschina.net/blog/write"

    # ---------------- 登录态 ----------------

    DOMAIN = "oschina.net"

    def check_auth(self, page) -> bool:
        # 首页右上角未登录有「登录/注册」链接，登录后消失。
        # 已在域内时不 goto（避免打断登录页上的扫码/输密码）
        try:
            if self.DOMAIN not in page.url:
                page.goto(HOME, timeout=60000, wait_until="domcontentloaded")
                time.sleep(2)
            if "/home/login" in page.url:
                return False
            return page.query_selector('a[href*="/home/login"]') is None
        except Exception:
            return False

    # ---------------- 列表 ----------------


    # ---------------- 发布 ----------------

    def _paste_into_iframe_editor(self, page, html):
        """UEditor 的编辑区在 iframe 里，得进 frame 粘贴。返回 True/False"""
        for frame in page.frames:
            try:
                if frame == page.main_frame:
                    continue
                body = frame.query_selector("body[contenteditable=true], body.editable")
                if not body:
                    # UEditor iframe 的 body 默认可编辑，直接试粘贴
                    ok = frame.evaluate(
                        """(html) => {
                            if (!document.body || document.designMode !== 'on' &&
                                document.body.getAttribute('contenteditable') !== 'true' &&
                                !document.body.isContentEditable) return false;
                            document.body.focus();
                            const ev = new ClipboardEvent('paste', {
                                bubbles: true, cancelable: true, clipboardData: new DataTransfer(),
                            });
                            ev.clipboardData.setData('text/html', html);
                            document.body.dispatchEvent(ev);
                            return true;
                        }""", html)
                    if ok:
                        return True
            except Exception:
                continue
        # 兜底：主页面上的 contenteditable 编辑器
        return page.evaluate(PASTE_HTML_JS, ['div[contenteditable="true"]', html])

    def publish(self, page, article, options=None):
        options = options or {}
        page.goto(self.new_url, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_selector('input[placeholder*="标题"], textarea[placeholder*="标题"], input[name="title"]',
                               timeout=30000)
        time.sleep(2)

        # 标题
        for sel in ('input[placeholder*="标题"]', 'textarea[placeholder*="标题"]', 'input[name="title"]'):
            el = page.query_selector(sel)
            if el:
                el.fill(article["title"])
                break

        # 正文
        html = md_to_html(article.get("content_md", ""))
        if not self._paste_into_iframe_editor(page, html):
            self.save_debug(page, "oschina_no_editor")
            raise PlatformError("找不到开源中国编辑器（UEditor），可能改版")
        time.sleep(3)

        if options.get("draft_only"):
            return {"post_id": "", "post_url": "", "edit_url": self.new_url,
                    "draft_only": True}

        try:
            page.click("div.button_publish.item.editor-btn, .editor-btn:has-text('发布')",
                       timeout=8000)
            time.sleep(2)
            # 发布一般会弹设置弹层（分类/摘要），能确认就确认
            for t in ("确定", "发布", "确认"):
                try:
                    page.click(f"text={t}", timeout=3000)
                    break
                except Exception:
                    continue
            time.sleep(3)
        except Exception:
            self.save_debug(page, "oschina_publish_btn")
            raise PlatformError("点了发布但没成功，内容已填好，去浏览器手动确认")

        return {"post_id": "", "post_url": page.url if "/blog/" in page.url else "",
                "edit_url": self.new_url, "draft_only": False}

    # ---------------- 原地更新 ----------------

    def update(self, page, pub, article):
        raise PlatformError("开源中国暂不支持原地更新，请删除后重发")
