# -*- coding: utf-8 -*-
"""SegmentFault 思否适配器：API 建草稿 + 写作页点发布。

- 草稿接口 /gateway/draft 只要 cookie（token 传 PHPSESSID），可靠
- 正式公开发布的接口未公开稳定，走写作页 UI 点「发布」
"""

import time

from service.publishing.adapters.base import PlatformAdapter, PlatformError, register

HOST = "https://segmentfault.com"


@register
class SegmentFaultAdapter(PlatformAdapter):
    id = "segmentfault"
    name = "思否"
    login_url = "https://segmentfault.com/user/login"

    # 页面结构版本（第三刀加固）：平台改版时更新此版本并同步 key_selectors
    selector_version = "2026-09"
    key_selectors = {'editor': '.CodeMirror, .ProseMirror', 'title_input': "input[placeholder*='标题']"}
    home_url = "https://segmentfault.com/write"
    list_url = "https://segmentfault.com/user/articles"
    new_url = "https://segmentfault.com/write"

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
            page.click("text=发布", timeout=8000)
            time.sleep(1.5)
            # 可能弹分类/标签确认弹层，能点就点
            for t in ("确定", "确认发布", "发布"):
                try:
                    page.click(f"text={t}", timeout=3000)
                    break
                except Exception:
                    continue
        except Exception:
            self.save_debug(page, "sf_publish_btn")
            raise PlatformError("思否写作页找不到「发布」按钮（可能改版），"
                                f"草稿已建好：{HOST}/write?draftId={draft_id}，可手动发布")
        time.sleep(3)
        return {"post_id": str(draft_id),
                "post_url": f"{HOST}/a/{draft_id}",   # 思否文章页 /a/{id}，以草稿 ID 兜底
                "edit_url": f"{HOST}/write?draftId={draft_id}", "draft_only": False}

    # ---------------- 原地更新 ----------------

    def update(self, page, pub, article):
        draft_id = pub.get("post_id")
        if not draft_id:
            raise PlatformError("思否原地更新需要 post_id")
        token = self.get_cookie(page, "PHPSESSID")
        tags = [t.strip() for t in (article.get("tags") or "").split(",") if t.strip()]
        self.api_post(
            page, f"{HOST}/gateway/draft",
            {"title": article["title"], "tags": tags,
             "text": article.get("content_md", ""),
             "object_id": draft_id, "type": "article", "language": "", "cover": ""},
            headers={"token": token})
        time.sleep(1)
        return True
