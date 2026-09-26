# -*- coding: utf-8 -*-
"""知乎适配器：专栏文章，走 UI（Markdown 文件导入 + 点发布）。

为什么不用 API：知乎的 /api/v4/* 大多要求 x-zse-96 签名（前端 JS 生成），
裸 fetch 会被拒。走页面 UI 让前端自己发请求，签名/风控都由它处理，反而最稳。

选择器参考社区实测（MultiPost-Extension），知乎改版后用 dump_dom 重新抓。

正文注入策略（2026-09 实测）：
  - PASTE_HTML_JS 的 ClipboardEvent 对知乎新版 Draft.js 已失效（paste 事件被禁用）
  - 知乎工具栏有「导入」按钮，点开后触发 input[type=file] 文件对话框
  - 用 Playwright set_input_files 直接注入 .md 文件（最稳，正确解析代码块/表格）
  - 降级方案：document.execCommand('insertText') 逐字输入
"""

import time

from core.adapters.base import (
    PlatformAdapter,
    PlatformError,
    md_to_html,
    register,
)

TITLE_SEL = 'textarea.Input[placeholder*="请输入标题"]'  # 知乎标题框是 class="Input" 的 textarea
EDITOR_SEL = 'div[data-contents="true"]'  # Draft.js 编辑器根节点
CE_SEL = "[data-contents=true] [contenteditable=true], [data-contents=true][contenteditable=true]"


def _click_button(page, texts, timeout=8000):
    """点文本匹配的按钮（知乎按钮样式多，按文本找最稳）"""
    for t in texts:
        try:
            page.locator(f'button:has-text("{t}")').first.click(timeout=timeout)
            return t
        except Exception:
            continue
    # 兜底：按 CSS class（发布按钮 class 含 Button--primary）
    try:
        page.locator("button.Button--primary").first.click(timeout=timeout)
        return "Button--primary"
    except Exception:
        pass
    raise PlatformError(f"页面上找不到按钮: {texts}")


@register
class ZhihuAdapter(PlatformAdapter):
    id = "zhihu"
    name = "知乎"
    login_url = "https://www.zhihu.com/signin?next=%2F"

    # 页面结构版本（第三刀加固）：平台改版时更新此版本并同步 key_selectors
    selector_version = "2026-09"
    key_selectors = {
        "editor": ".DraftEditor-root",
        "title_input": "textarea, input[placeholder*='标题']",
    }
    home_url = "https://zhuanlan.zhihu.com/write"
    list_url = "https://www.zhihu.com/creator"  # 创作中心（内容管理在里面）
    new_url = "https://zhuanlan.zhihu.com/write"

    # ---------------- 登录态 ----------------

    DOMAIN = "zhihu.com"
    # 「我」接口地址。提成类属性让 E2E mock 可替换（与 login_url 同理）。
    me_api = "https://www.zhihu.com/api/v4/me"

    def check_auth(self, page) -> bool:
        # 只认「我」接口返回真实用户：URL 判断有假成功（扫码确认页/未登录页
        # 都可能不含 /signin，2026-09-25 实测 z_c0 缺失的根因）
        try:
            data = self.api_get(page, self.me_api)
            return bool(data and (data.get("id") or data.get("url_token")))
        except Exception:
            return False

    # ---------------- 列表 ----------------

    # ---------------- 正文注入 ----------------

    def _import_md_file(self, page, content):
        """通过知乎「导入」按钮 → 弹出 modal → 点上传区触发 filechooser → 注入 .md 文件。

        流程（2026-09 实测）：
          1. 点工具栏「导入」按钮 → 弹出 Popover 子菜单
          2. 点「导入文档」(button[aria-label="导入文档"]) → 弹出 Modal（上传区在 modal 里）
          3. 对 Modal 里的上传区（div[role=button]）点击，同时用 expect_file_chooser 捕获文件对话框
          4. file_chooser.set_files(临时 .md 路径) → 知乎解析 Markdown → 自动填入编辑器，关闭 Modal
          5. 编辑器 4713 字符验证通过，发布按钮自动从 disabled 变为 enabled

        返回 True 成功，False 失败（调用方降级到 _inject_editor）。
        """
        import tempfile, os

        tmp = None
        try:
            tmp = tempfile.NamedTemporaryFile(
                suffix=".md", mode="w", encoding="utf-8", delete=False, dir="data"
            )
            tmp.write(content)
            tmp.close()

            # Step 1: 点「导入」工具栏按钮，弹出子菜单
            try:
                page.locator('button:has-text("导入")').first.click(timeout=5000)
                time.sleep(2)
            except Exception:
                pass

            # Step 2: 点「导入文档」（弹出 Modal，里面有 MD 上传区）
            try:
                page.locator('button[aria-label="导入文档"]').first.click(timeout=5000)
                time.sleep(3)
            except Exception:
                pass

            # Step 3: 点 Modal 里的上传区（div[role=button]），同时捕获 filechooser
            # 知乎的上传区是 div.css-xxx（class 是 CSS-in-JS 哈希，用 role=button 定位更稳）
            with page.expect_file_chooser(timeout=10000) as fc_info:
                # 点 modal 里的上传区（role=button + 含"点击选择"文字）
                page.locator('.Modal [role="button"]').first.click(timeout=5000)

            file_chooser = fc_info.value
            file_chooser.set_files(tmp.name)
            time.sleep(12)  # 等知乎解析 Markdown 并渲染到编辑器
            os.unlink(tmp.name)
            tmp = None
            return True
        except Exception:
            if tmp:
                try:
                    os.unlink(tmp.name)
                except Exception:
                    pass
            return False

    def _inject_editor(self, page, content):
        """知乎 Draft.js 键盘逐字输入，最可靠。

        实测发现：
          - PASTE_HTML_JS 的 ClipboardEvent 对知乎新版 Draft.js 草稿编辑器已失效（paste 事件被禁用）
          - 编辑器 contenteditable 在 JS 里可见但 Playwright 的 query_selector_all 不识别
          - 改用 page.evaluate + document.execCommand('insertText') 最稳定
        """
        js = """(text) => {
            const ces = document.querySelectorAll('[contenteditable="true"]');
            if (!ces.length) return false;
            const ed = ces[0];
            ed.focus();
            document.execCommand('selectAll', false, null);
            document.execCommand('delete', false, null);
            document.execCommand('insertText', false, text);
            return true;
        }"""
        ok = page.evaluate(js, content)
        if not ok:
            raise PlatformError("知乎编辑器注入失败：找不到 contenteditable")
        time.sleep(1.5)

    # ---------------- 发布 ----------------

    def publish(self, page, article, options=None):
        options = options or {}
        page.goto(self.new_url, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_selector(TITLE_SEL, timeout=30000)
        time.sleep(2)

        # 标题（知乎限 100 字）
        page.fill(TITLE_SEL, article["title"][:100])

        # 正文：优先用 Markdown 文件导入（正确解析代码块/表格），降级到逐字输入
        md_content = article.get("content_md", "")
        import_ok = self._import_md_file(page, md_content)
        if not import_ok:
            self._inject_editor(page, md_content)
        time.sleep(3)  # 等编辑器自动保存

        if options.get("draft_only"):
            # 知乎编辑器自动存草稿，但没有公开的草稿 ID 可拿 —— 不点发布，交人工确认
            return {
                "post_id": "",
                "post_url": "",
                "edit_url": self.new_url,
                "draft_only": True,
            }

        _click_button(page, ["发布"])
        time.sleep(2)

        # 可能弹发布设置（首次发布弹开通/话题选择），有「确认/发布」就再点一次
        try:
            _click_button(page, ["确认发布", "确定", "发布"], timeout=5000)
        except Exception:
            pass

        # 发布成功后 URL 会跳到 /p/<id>
        deadline = time.time() + 30
        while time.time() < deadline:
            time.sleep(1.5)
            if "/p/" in page.url:
                post_id = page.url.rstrip("/").split("/p/")[-1].split("?")[0]
                return {
                    "post_id": post_id,
                    "post_url": f"https://zhuanlan.zhihu.com/p/{post_id}",
                    "edit_url": page.url,
                    "draft_only": False,
                }
        self.save_debug(page, "zhihu_publish_stuck")
        raise PlatformError(
            "点了发布但 30 秒内没跳到文章页，可能弹了人工确认窗口，"
            "去浏览器里手动确认后用「原地更新」补状态"
        )

    # ---------------- 原地更新 ----------------

    def update(self, page, pub, article):
        page.goto(
            pub.get("post_url") or pub.get("edit_url"),
            timeout=60000,
            wait_until="domcontentloaded",
        )
        page.wait_for_load_state("domcontentloaded")
        time.sleep(2)
        _click_button(page, ["编辑"], timeout=10000)
        page.wait_for_selector(EDITOR_SEL, timeout=30000)
        time.sleep(2)

        try:
            page.fill(TITLE_SEL, article["title"][:100])
        except Exception:
            pass

        md_content = article.get("content_md", "")
        import_ok = self._import_md_file(page, md_content)
        if not import_ok:
            self._inject_editor(page, md_content)
        time.sleep(3)

        # 编辑已发布文章的按钮是「保存并发布」；纯草稿是「发布」
        _click_button(page, ["保存并发布", "发布"])
        time.sleep(2)
        try:
            _click_button(page, ["确认发布", "确定"], timeout=5000)
        except Exception:
            pass
        time.sleep(3)
        return True
