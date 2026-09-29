# -*- coding: utf-8 -*-
"""B站专栏适配器：创作 API 建草稿（FormData + csrf）。

- 登录探针: /x/web-interface/nav（code==0 已登录 / -101 未登录），最稳
- 草稿接口: /x/article/creative/draft/addupdate，FormData，csrf 取 cookie bili_jct
- 正式公开发布需要二级确认（分区选择），默认交付到草稿箱 + 编辑页
"""

from service.publishing.adapters.base import PlatformAdapter, PlatformError, md_to_html, register

NAV = "https://api.bilibili.com/x/web-interface/nav"
DRAFT_API = "https://api.bilibili.com/x/article/creative/draft/addupdate"


@register
class BilibiliAdapter(PlatformAdapter):
    id = "bilibili"
    name = "B站专栏"
    login_url = "https://passport.bilibili.com/login"

    # 页面结构版本（第三刀加固）：平台改版时更新此版本并同步 key_selectors
    selector_version = "2026-09"
    key_selectors = {'editor': '.ProseMirror, .ql-editor', 'title_input': "input[placeholder*='标题']"}
    home_url = "https://member.bilibili.com/platform/upload-manager/article"
    list_url = "https://member.bilibili.com/platform/upload-manager/article"
    new_url = "https://member.bilibili.com/platform/upload-manager/article/editor"

    # ---------------- 登录态 ----------------

    def check_auth(self, page) -> bool:
        try:
            data = self.api_get(page, NAV)
            return isinstance(data, dict) and data.get("code") == 0
        except Exception:
            return False

    # ---------------- 列表 ----------------


    # ---------------- 发布 ----------------

    def publish(self, page, article, options=None):
        options = options or {}
        csrf = self.get_cookie(page, "bili_jct")
        if not csrf:
            raise PlatformError("B站登录态缺失（没有 bili_jct cookie），先登录")

        html = md_to_html(article.get("content_md", ""))
        # B站标题限 40 字，超出会被接口拒
        title = article["title"][:40]
        summary = (article.get("summary") or article.get("content_md", "")[:100])
        fields = {
            "title": title, "content": html, "summary": summary, "banner_url": "",
            "words": len(html), "category": "0", "list_id": "0", "tid": "0",
            "reprint": "0", "tags": ",".join(options.get("tags") or []),
            "image_urls": "", "origin_image_urls": "",
            "dynamic_intro": summary[:60], "media_id": "0", "spoiler": "0",
            "original": "1", "top_video_bvid": "", "csrf": csrf,
        }
        res = self.api_post_form(page, DRAFT_API, fields)
        aid = (res.get("data") or {}).get("aid") if isinstance(res, dict) else None
        if not aid:
            raise PlatformError(f"B站创建专栏草稿失败: {str(res)[:200]}")

        edit_url = f"https://member.bilibili.com/article-text/home?aid={aid}"
        if options.get("draft_only"):
            return {"post_id": str(aid), "post_url": "", "edit_url": edit_url,
                    "draft_only": True}

        # 正式发表需要二次选分区，goto 编辑页让用户瞄一眼再点「发表」——
        # API 直接发表会被 B站拒（缺少分区信息），这里不做假成功
        return {"post_id": str(aid), "post_url": "", "edit_url": edit_url,
                "draft_only": True}

    # ---------------- 原地更新 ----------------

    def update(self, page, pub, article):
        aid = pub.get("post_id")
        if not aid:
            raise PlatformError("B站原地更新需要 post_id")
        csrf = self.get_cookie(page, "bili_jct")
        html = md_to_html(article.get("content_md", ""))
        self.api_post_form(page, DRAFT_API, {
            "title": article["title"][:40], "content": html,
            "summary": article.get("summary") or html[:100], "banner_url": "",
            "words": len(html), "category": "0", "list_id": "0", "tid": "0",
            "reprint": "0", "tags": "", "image_urls": "", "origin_image_urls": "",
            "dynamic_intro": "", "media_id": "0", "spoiler": "0", "original": "1",
            "top_video_bvid": "", "aid": aid, "csrf": csrf,
        })
        return True
