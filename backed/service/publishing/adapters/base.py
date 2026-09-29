# -*- coding: utf-8 -*-
"""平台适配器接口。

四个动作，AI 能管的全靠这四个：
    check_auth   登录了吗
    list         账号里有哪些文章（顺带把 edit_url 抓回来）
    publish      发一篇新的，返回 post_id
    update       原地更新已发布的（打开 edit_url 改内容再保存）

设计原则：
  1. edit_url 一律从列表页抓，不靠拼 URL —— 拼错了就是灾难，抓来的才准
  2. 平台专属的 URL / API / 选择器全部集中在各适配器顶部常量区，改平台只改那一块
  3. 任何一步失败都抛 PlatformError，由上层记进 jobs 表，不影响其他平台
"""

import json
import time

import markdown as _md_lib


def md_to_html(text):
    """Markdown 转 HTML。知乎/B站/头条/开源中国这类富文本编辑器粘贴时用。"""
    if not text:
        return ""
    try:
        return _md_lib.markdown(text, extensions=["fenced_code", "tables", "nl2br"])
    except Exception:
        # 转不了就整段塞进 <pre>，至少内容不丢
        import html as _html
        return f"<pre>{_html.escape(text)}</pre>"


# 通用"往富文本编辑器粘贴 HTML"的 JS。知乎(Draft.js)/头条/开源中国(UEditor) 都吃这套：
# 构造 ClipboardEvent 带 text/html 数据 → 编辑器自己解析富文本，比 setValue 稳。
PASTE_HTML_JS = """([sel, html]) => {
    const editor = document.querySelector(sel);
    if (!editor) return false;
    editor.focus();
    const ev = new ClipboardEvent('paste', {
        bubbles: true, cancelable: true, clipboardData: new DataTransfer(),
    });
    ev.clipboardData.setData('text/html', html);
    editor.dispatchEvent(ev);
    editor.dispatchEvent(new Event('input', {bubbles: true}));
    editor.dispatchEvent(new Event('change', {bubbles: true}));
    return true;
}"""


class PlatformError(Exception):
    pass


class PlatformAdapter:
    id = ""
    name = ""
    needs_browser = True   # 走标准协议的平台（如博客园 MetaWeblog）设 False，省一个浏览器实例
    login_url = ""
    home_url = ""      # 登录后才能进的页面，用来判断登录态
    list_url = ""      # 内容管理页
    new_url = ""       # 新建文章页

    # 选择器版本化（第三刀）：每个子类声明它依赖的页面结构版本与关键选择器，
    # 平台改版时 dump-dom 能立刻对上号，而不是报一堆无关错误。
    selector_version = ""    # 例如 "2026-09"（适配/验证时手动更新）
    key_selectors = {}       # 例如 {"editor": ".CodeMirror", "publish_btn": "button:has-text('发布')"}

    def sel_fail(self, sel_name):
        """选择器失效的统一报错：带上版本号与 DOM dump 指引，方便一键补适配。"""
        return PlatformError(
            f"[{self.name}] 页面结构失效：关键选择器 '{sel_name}' 未命中"
            f"（适配器版本 {self.selector_version or '未知'}）。"
            f"请先跑一次 dump-dom 采集当前页面结构，更新 core/adapters/{self.id}.py 的 key_selectors。")

    # ---------------- 子类必须实现的四个动作 ----------------

    def check_auth(self, page) -> bool:
        raise NotImplementedError

    def list_articles(self, page, limit=50):
        """返回 [{'post_id','title','url','edit_url','status','stats':{}}]

        未实现的平台统一抛"需实机采集"错误（含 dump-dom 指引），
        而不是静默返回空列表——空列表会让"同步/更新"静默失效。
        """
        raise PlatformError(
            f"[{self.name}] 已发文章列表暂未适配。"
            f"该平台内容管理页 {self.list_url or '未知'} 需要实机登录后 "
            f"用 dump-dom 采集结构，再在 core/adapters/{self.id}.py 补 list_articles；"
            f"或改用该平台官方 API 对接。发布/草稿能力不受影响。")

    def publish(self, page, article: dict, options: dict = None):
        """返回 {'post_id','post_url','edit_url','draft_only'}"""
        raise NotImplementedError

    def update(self, page, pub: dict, article: dict) -> bool:
        """原地更新。pub 里带着 post_id / edit_url"""
        raise NotImplementedError

    # ---------------- 通用工具 ----------------

    def api_get(self, page, url):
        """在页面上下文里发 GET，自动带 cookie —— 比直接 requests 省事也更像真人。"""
        js = """async (u) => {
            const r = await fetch(u, {credentials: 'include'});
            return {status: r.status, text: await r.text()};
        }"""
        res = page.evaluate(js, url)
        if res["status"] != 200:
            raise PlatformError(f"GET {url} -> HTTP {res['status']}")
        try:
            return json.loads(res["text"])
        except Exception:
            raise PlatformError(f"响应不是 JSON: {res['text'][:200]}")

    def api_post(self, page, url, payload, headers=None):
        js = """async ([u, body, hdrs]) => {
            const r = await fetch(u, {
                method: 'POST',
                credentials: 'include',
                headers: Object.assign({'content-type': 'application/json'}, hdrs || {}),
                body: JSON.stringify(body)
            });
            return {status: r.status, text: await r.text()};
        }"""
        res = page.evaluate(js, [url, payload, headers])
        try:
            data = json.loads(res["text"])
        except Exception:
            raise PlatformError(f"响应不是 JSON: {res['text'][:200]}")
        if res["status"] != 200 or (isinstance(data, dict) and data.get("err_no") not in (0, None)):
            raise PlatformError(f"POST {url} 失败: {res['text'][:200]}")
        return data

    def api_put(self, page, url, payload, headers=None):
        """PUT JSON。更新文章用。"""
        js = """async ([u, body, hdrs]) => {
            const r = await fetch(u, {
                method: 'PUT',
                credentials: 'include',
                headers: Object.assign({'content-type': 'application/json'}, hdrs || {}),
                body: JSON.stringify(body)
            });
            return {status: r.status, text: await r.text()};
        }"""
        res = page.evaluate(js, [url, payload, headers])
        try:
            data = json.loads(res["text"])
        except Exception:
            raise PlatformError(f"响应不是 JSON: {res['text'][:200]}")
        if res["status"] != 200:
            raise PlatformError(f"PUT {url} 失败: {res['text'][:200]}")
        return data

    def api_post_form(self, page, url, fields):
        """multipart/FormData POST。B站专栏草稿用（JSON 会拒）。fields: {str: str}"""
        js = """async ([u, obj]) => {
            const fd = new FormData();
            for (const [k, v] of Object.entries(obj)) fd.append(k, v);
            const r = await fetch(u, {method: 'POST', credentials: 'include', body: fd});
            return {status: r.status, text: await r.text()};
        }"""
        res = page.evaluate(js, [url, {k: str(v) for k, v in fields.items()}])
        try:
            data = json.loads(res["text"])
        except Exception:
            raise PlatformError(f"响应不是 JSON: {res['text'][:200]}")
        if res["status"] != 200 or (isinstance(data, dict) and data.get("code") not in (0, None)):
            raise PlatformError(f"POST {url} 失败: {res['text'][:200]}")
        return data

    def get_cookie(self, page, name):
        return page.evaluate(
            """(n) => {
                const m = document.cookie.split('; ').find(c => c.startsWith(n + '='));
                return m ? m.slice(n.length + 1) : '';
            }""", name)

    def set_editor_content(self, page, content, editor_sel=".CodeMirror"):
        """
        往 Markdown 编辑器里塞内容。三级降级，从最快到最稳：
          1. CodeMirror 实例 setValue（秒级，编辑器能感知）
          2. 剪贴板粘贴
          3. 逐字输入（慢，但一定能触发事件）
        """
        # 1) CodeMirror
        try:
            ok = page.evaluate("""([sel, text]) => {
                const el = document.querySelector(sel);
                if (!el) return false;
                const cm = el.CodeMirror || (el.querySelector('.CodeMirror') || {}).CodeMirror;
                if (cm && cm.setValue) { cm.setValue(text); return true; }
                return false;
            }""", [editor_sel, content])
            if ok:
                time.sleep(0.5)
                return "codemirror"
        except Exception:
            pass

        # 2) 剪贴板
        try:
            page.evaluate("(t) => navigator.clipboard.writeText(t)", content)
            page.click(editor_sel, timeout=5000)
            page.keyboard.press("Control+A")
            page.keyboard.press("Control+V")
            time.sleep(0.8)
            return "clipboard"
        except Exception:
            pass

        # 3) 硬输
        page.click(editor_sel, timeout=5000)
        page.keyboard.press("Control+A")
        page.keyboard.press("Delete")
        page.keyboard.insert_text(content)
        return "typing"

    def save_debug(self, page, tag):
        from service.publishing.browser import dump_dom
        path = dump_dom(page, tag)
        return str(path)


ADAPTERS = {}


def register(cls):
    ADAPTERS[cls.id] = cls()
    return cls


def get_adapter(platform):
    if platform not in ADAPTERS:
        raise PlatformError(f"不支持的平台: {platform}，已注册: {list(ADAPTERS)}")
    return ADAPTERS[platform]
