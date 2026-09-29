# -*- coding: utf-8 -*-
"""掘金适配器：发布 + 原地更新 + 列表。

平台专属常量都在这上面，掘金改版了就改这一块。
"""

import time

from service.publishing.adapters.base import PlatformAdapter, PlatformError, register

AID = "2608"
API = "https://api.juejin.cn"

# 分类 ID（掘金官方值）。若失效，打开 juejin.cn/editor/drafts/new 抓一下分类下拉即可更新
CATEGORIES = {
    "前端": "6809637767543259144",
    "后端": "6809637769959178254",
    "android": "6809635626879549454",
    "ios": "6809635626951802894",
    "人工智能": "6809637771511070734",
    "开发工具": "6809637776263217166",
    "代码人生": "6809637772874219534",
    "阅读": "6809637773935378440",
}
DEFAULT_CATEGORY = "后端"

# 常用标签 ID 兜底表：搜索不到时按名字直接命中（掘金 tag_api 常见值）
KNOWN_TAG_IDS = {
    "Python": "7104", "JavaScript": "7003", "前端": "7003",
    "Java": "7002", "后端": "7104", "Go": "7097",
    "Android": "7095", "iOS": "7093", "人工智能": "7034",
    "机器学习": "7034", "开发工具": "7015", "程序员": "7005",
    "面试": "7039", "架构": "7103", "数据库": "7030",
}


def _resolve_tag_ids(page, tag_names):
    """把文章标签解析成掘金 tag_id 列表（优先精确搜索，兜底常用表，再兜底 Python）。

    掘金 tag_api/v1/query_tag_list 按关键词搜；搜不到的名字直接跳过，
    至少保证一个 tag_id，发布弹窗里才有标签可显示。
    """
    ids = []
    for name in (tag_names or [])[:5]:
        name = name.strip()
        if not name:
            continue
        if name in KNOWN_TAG_IDS and KNOWN_TAG_IDS[name] not in ids:
            ids.append(KNOWN_TAG_IDS[name])
            continue
        try:
            data = api_tag_search(page, name)
            hit = None
            # 字段名兼容：tag_name/name 都可能，ID 同理 tag_id/id
            for t in (data.get("data") or [])[:10]:
                tname = t.get("tag_name") or t.get("name") or ""
                if tname and tname.lower() == name.lower():
                    hit = t
                    break
            if hit is None:
                for t in (data.get("data") or []):
                    if t.get("tag_id") or t.get("id"):
                        hit = t
                        break
            if hit:
                tid = str(hit.get("tag_id") or hit.get("id") or "").strip()
                # 真 tag_id 是 7 位数字；19 位的是其他对象（如文章ID），过滤
                if tid.isdigit() and len(tid) <= 12 and tid not in ids:
                    ids.append(tid)
        except Exception:
            continue
    if not ids:
        ids = [KNOWN_TAG_IDS["Python"]]
    return ids


def api_tag_search(page, keyword):
    """掘金标签搜索接口（页面上下文 fetch，cookie 自动带）。"""
    return page.evaluate("""async ([kw]) => {
        const r = await fetch('https://api.juejin.cn/tag_api/v1/query_tag_list'
            + '?aid=2608&spider=0', {
            method: 'POST', credentials: 'include',
            headers: {'content-type': 'application/json'},
            body: JSON.stringify({key_word: kw, cursor: '0', limit: 10})
        });
        return {status: r.status, text: await r.text()};
    }""", [keyword])


def _click_text(page, texts, timeout=8000):
    for t in texts:
        try:
            page.click(f"text={t}", timeout=timeout)
            return t
        except Exception:
            continue
    raise PlatformError(f"页面上找不到这些按钮: {texts}")


def tag_name_for_search(category):
    """把掘金分类名映射为 tag 搜索词。"""
    mapping = {
        "前端": "JavaScript",
        "后端": "Python",
        "android": "Android",
        "ios": "iOS",
        "人工智能": "机器学习",
        "开发工具": "开发工具",
        "代码人生": "程序员",
        "阅读": "技术",
    }
    return mapping.get(category, "Python")


@register
class JuejinAdapter(PlatformAdapter):
    id = "juejin"
    name = "稀土掘金"
    login_url = "https://juejin.cn/login"

    # 页面结构版本（第三刀加固）：平台改版时更新此版本并同步 key_selectors
    selector_version = "2026-09"
    key_selectors = {'editor': '.bytemd, .CodeMirror', 'title_input': "input[placeholder*='标题'], .title-input"}
    home_url = "https://juejin.cn/"   # 2026-09-25：creator/home 对数据中心 IP 风控(4xx)，改首页（页面在 juejin.cn 域即可带 cookie 走 API）
    list_url = "https://juejin.cn/creator/content/article"
    new_url = "https://juejin.cn/editor/drafts/new"

    # ---------------- 登录态 ----------------

    def check_auth(self, page) -> bool:
        try:
            data = self.api_get(page, f"{API}/user_api/v1/user/get?aid={AID}")
            return bool((data.get("data") or {}).get("user_id"))
        except Exception:
            return False

    def _user_id(self, page):
        data = self.api_get(page, f"{API}/user_api/v1/user/get?aid={AID}")
        uid = (data.get("data") or {}).get("user_id")
        if not uid:
            raise PlatformError("拿不到 user_id，登录态可能失效")
        return uid

    # ---------------- 列表 ----------------

    def list_articles(self, page, limit=50):
        uid = self._user_id(page)
        page.goto(self.list_url, timeout=60000, wait_until="domcontentloaded")
        # 等 SPA 真把文章行渲染出来再动手，比死等 3 秒又快又稳；
        # 空账号列表不会出现链接，兜底再给 1 秒收尾
        try:
            page.wait_for_selector('a[href*="/editor/"]', timeout=8000)
        except Exception:
            time.sleep(1)

        # 编辑链接从 DOM 抓，不猜 —— 标题和 href 对齐存起来
        edit_map = {}
        try:
            items = page.evaluate("""() => {
                const out = [];
                document.querySelectorAll('a[href*="/editor/"]').forEach(a => {
                    const row = a.closest('li, tr, div[class*="item"]');
                    const t = (row && row.innerText || a.innerText || '').split('\\n')[0].trim();
                    if (t) out.push({title: t, href: a.getAttribute('href')});
                });
                return out;
            }""")
            for it in items:
                if it["href"] and it["title"]:
                    edit_map[it["title"]] = it["href"]
        except Exception:
            pass

        data = self.api_get(
            page, f"{API}/content_api/v1/article/query_list"
                  f"?aid={AID}&user_id={uid}&sort_type=2&cursor=0")
        rows = data.get("data") or []
        out = []
        for a in rows[:limit]:
            title = (a.get("title") or "").strip()
            aid_ = a.get("article_id") or a.get("article_info", {}).get("article_id")
            info = a.get("article_info") or {}
            href = edit_map.get(title)
            edit_url = ("https://juejin.cn" + href) if href and href.startswith("/") else href
            out.append({
                "post_id": aid_,
                "title": title,
                "url": f"https://juejin.cn/post/{aid_}" if aid_ else "",
                "edit_url": edit_url or "",
                "status": "published" if info.get("status") == 2 else "draft",
                "stats": {
                    "view": info.get("view_count", 0),
                    "digg": info.get("digg_count", 0),
                    "comment": info.get("comment_count", 0),
                },
            })
        return out

    # ---------------- 发布 ----------------

    def publish(self, page, article, options=None):
        options = options or {}
        cat = options.get("category") or DEFAULT_CATEGORY
        cat_id = CATEGORIES.get(cat) or CATEGORIES[DEFAULT_CATEGORY]
        brief = (article.get("summary")
                 or (article.get("content_md", "")[:100].replace("\n", " ")))

        # 确保在掘金域名下（cookie 需要）。goto 失败不拦：page 若已在
        # juejin.cn 域（首页能开）就继续走 API；风控页打不开也尽力发 API
        if "juejin.cn" not in page.url:
            try:
                page.goto(self.home_url, timeout=60000, wait_until="domcontentloaded")
                time.sleep(2)
            except Exception:
                pass

        # 标签：把文章标签解析成掘金 tag_id（找不到时兜底 Python 7104）
        tag_ids = options.get("tag_ids") or _resolve_tag_ids(
            page, options.get("tags") or [])

        payload = {
            "category_id": cat_id,
            "tag_ids": tag_ids,
            "link_url": "",
            "cover_image": article.get("cover") or "",
            "title": article["title"],
            "brief_content": brief,
            "edit_type": 10,                      # 10 = Markdown
            "html_content": "deprecated",
            "mark_content": article.get("content_md", ""),
            "theme_ids": [],
        }
        draft = self.api_post(
            page, f"{API}/content_api/v1/article_draft/create?aid={AID}&spider=0", payload)
        draft_id = (draft.get("data") or {}).get("id")
        if not draft_id:
            raise PlatformError(f"创建草稿失败: {draft}")

        if options.get("draft_only"):
            return {"post_id": draft_id,
                    "post_url": "",
                    "edit_url": f"https://juejin.cn/editor/drafts/{draft_id}",
                    "draft_only": True}

        # ====== 掘金 2026-09：publish API 已封死，走 UI 面板发布 ======
        # 流程：进编辑器 → 点"发布"按钮开面板 → 点"确定并发布"
        # 注意：2026-09 前端点"确定并发布"后只发 article_draft/update，
        # 不发 article/publish。如果 URL 没跳到 /post/xxx，说明发布未成功。
        # 此时返回 draft-only 结果，用户需手动在浏览器里点一次"确定并发布"。

        # 1. 进草稿编辑器
        page.goto(f"https://juejin.cn/editor/drafts/{draft_id}",
                  timeout=60000, wait_until="domcontentloaded")
        time.sleep(6)

        # 2. 点"发布"按钮（.xitu-btn 主按钮），打开右侧发布面板
        try:
            page.locator("button.xitu-btn").filter(has_text="发布").first.click(timeout=8000)
        except Exception:
            page.locator("button:has-text('发布')").first.click(timeout=8000)
        time.sleep(4)

        # 3. 直接点"确定并发布"（草稿创建时已带 tag_ids，面板里 tag 显示正确）
        try:
            page.locator("button:has-text('确定并发布')").first.click(timeout=8000)
        except Exception:
            try:
                page.locator("button.ui-btn.btn.primary").last.click(timeout=8000)
            except Exception:
                pass
        time.sleep(10)

        # 4. 检查 URL 是否跳到 /post/xxx
        article_id = ""
        for _ in range(5):
            if "/post/" in page.url:
                article_id = page.url.split("/post/")[-1].split("?")[0].split("/")[0]
                break
            time.sleep(2)

        if article_id:
            return {
                "post_id": article_id,
                "post_url": f"https://juejin.cn/post/{article_id}",
                "edit_url": f"https://juejin.cn/editor/drafts/{draft_id}",
                "draft_only": False,
            }

        # 5. 发布未成功——返回 draft-only（用户可手动在浏览器里完成最后一步）
        return {
            "post_id": draft_id,
            "post_url": "",
            "edit_url": f"https://juejin.cn/editor/drafts/{draft_id}",
            "draft_only": True,
            "warning": "掘金 2026-09 版 publish API 变更，自动发布未成功，草稿已创建，请手动在浏览器里点'确定并发布'",
        }

    # ---------------- 原地更新 ----------------

    def update(self, page, pub, article):
        edit_url = pub.get("edit_url") or f"https://juejin.cn/editor/drafts/{pub.get('post_id')}"
        page.goto(edit_url, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_selector(".CodeMirror", timeout=30000)
        time.sleep(2)

        # 标题
        try:
            title_input = page.query_selector('input[placeholder*="标题"]')
            if title_input:
                title_input.click()
                page.keyboard.press("Control+A")
                page.keyboard.type(article["title"])
        except Exception:
            pass

        self.set_editor_content(page, article.get("content_md", ""))
        time.sleep(1)

        _click_text(page, ["发布", "发布文章"])
        time.sleep(1.5)
        _click_text(page, ["确定并发布", "确认发布", "并发布"])
        time.sleep(4)
        return True
