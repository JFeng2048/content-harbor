# -*- coding: utf-8 -*-
"""博客园适配器：走 MetaWeblog XML-RPC 标准协议，**不需要浏览器**。

为什么单独做它：博客园是少数开放了标准写入协议的老牌平台，
用 xmlrpc 发/改/列都比模拟浏览器稳一个数量级，还不用管登录态过期。

开通：博客园 → 管理 → 设置 → 其他设置 → 勾选「允许 MetaWeblog 博客客户端访问」。
页面会给出三样东西，一个都不能猜：
  MetaWeblog 访问地址  https://rpc.cnblogs.com/metaweblog/<博客地址名>
  MetaWeblog 登录名    注意：不是邮箱，也不是昵称
  MetaWeblog 访问令牌  注意：2025 起**密码登录已取消**，填登录密码必挂

配置写进 config.json：
{
  "platforms": {
    "cnblogs": {
      "endpoint": "https://rpc.cnblogs.com/metaweblog/你的博客地址名",
      "username": "MetaWeblog 登录名",
      "token": "MetaWeblog 访问令牌"
    }
  }
}

坑（文档里没写，踩过才知道）：
  1. endpoint 里那段是**博客地址名**（https://www.cnblogs.com/<这段>/），
     不是数字用户 ID。填错的表现是 500，不是 404，极具迷惑性。
  2. 密码必须是**访问令牌**，登录密码会被拒：「密码登录已取消，请在密码框中输入访问令牌」。
  3. categories 里**必须带 "[Markdown]"**，否则博客园把内容当 HTML 渲染，
     Markdown 全变成一行纯文本。
  4. 没勾「允许 MetaWeblog 博客客户端访问」同样是 500。
"""

import json
import xmlrpc.client
from datetime import datetime
from pathlib import Path

from service.publishing.adapters.base import PlatformAdapter, PlatformError, register

# 本文件在 core/adapters/ 下，往上三级才是项目根
ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = ROOT / "config.json"
MARKDOWN_FLAG = "[Markdown]"


def _creds():
    if not CONFIG_FILE.exists():
        raise PlatformError("没有 config.json，博客园需要配 endpoint/username/token")
    cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    c = (cfg.get("platforms") or {}).get("cnblogs") or {}
    for k in ("endpoint", "username"):
        if not c.get(k):
            raise PlatformError(f"config.json 里 platforms.cnblogs.{k} 没填")
    # token 优先；老配置写 password 也能用，但会提示改名
    if not (c.get("token") or c.get("password")):
        raise PlatformError(
            "config.json 里 platforms.cnblogs 缺 token。"
            "博客园已取消密码登录，必须填「MetaWeblog 访问令牌」")
    c["secret"] = c.get("token") or c.get("password")
    c["using_token"] = bool(c.get("token"))
    # 占位符守卫：endpoint/username/token 任一带中文，说明还是模板值没换成真凭据。
    # 不拦的话，XML-RPC 会在发请求时抛晦涩的 UnicodeEncodeError，用户看不懂该去填配置。
    for k in ("endpoint", "username", "secret"):
        v = str(c.get(k, ""))
        if any("\u4e00" <= ch <= "\u9fff" for ch in v):
            raise PlatformError(
                f"config.json 里 platforms.cnblogs.{k} 还是占位符，没换成真实值。"
                "去博客园 管理→设置→其他设置 勾「允许 MetaWeblog 访问」，"
                "把真实的 endpoint / 登录名 / 访问令牌填进去。")
    return c

def _client():
    c = _creds()
    return xmlrpc.client.ServerProxy(c["endpoint"], allow_none=True), c


@register
class CnblogsAdapter(PlatformAdapter):
    id = "cnblogs"
    name = "博客园"
    needs_browser = False          # 纯协议，不开浏览器
    login_url = "https://account.cnblogs.com/signin"

    # 页面结构版本（第三刀加固）：平台改版时更新此版本并同步 key_selectors
    selector_version = "2026-09"
    key_selectors = {'editor': '.CodeMirror', 'title_input': "input[name='Title'], #post_title"}
    home_url = "https://i.cnblogs.com/posts"
    list_url = "https://i.cnblogs.com/posts"
    new_url = "https://i.cnblogs.com/posts/edit"

    # ---------------- 登录态 ----------------

    def check_auth(self, page=None) -> bool:
        try:
            s, c = _client()
            blogs = s.blogger.getUsersBlogs("", c["username"], c["secret"])
            return bool(blogs)
        except xmlrpc.client.ProtocolError as e:
            # 博客园对"凭据错 / blogApp 错"统一返回 500，不告诉你哪个错，只能自己排查
            raise PlatformError(
                f"MetaWeblog 返回 {e.errcode}。三种可能：\n"
                f"  1) endpoint 里的博客名不对（现在用的：{_creds().get('endpoint','')}）\n"
                f"  2) 密码不是 MetaWeblog 令牌（博客园要单独设置，不是登录密码）\n"
                f"  3) 没开通 MetaWeblog：设置 → 其他设置 → 允许 MetaWeblog 访问")
        except PlatformError:
            raise          # 配置缺失这类自身错误，原样透传，别包装成"连不上"
        except Exception as e:
            raise PlatformError(f"连不上 MetaWeblog: {type(e).__name__} {e}")

    def whoami(self):
        """排查用：把 endpoint 和拿到的博客信息打出来（不含密码）。"""
        s, c = _client()
        blogs = s.blogger.getUsersBlogs("", c["username"], c["secret"])
        return {"endpoint": c["endpoint"], "username": c["username"], "blogs": blogs}

    def _blogid(self, s, c):
        blogs = s.blogger.getUsersBlogs("", c["username"], c["secret"])
        if not blogs:
            raise PlatformError("拿不到 blogid，检查 MetaWeblog 是否开通")
        return blogs[0]["blogid"]

    # ---------------- 列表 ----------------

    def list_articles(self, page=None, limit=50):
        s, c = _client()
        bid = self._blogid(s, c)
        posts = s.metaWeblog.getRecentPosts(bid, c["username"], c["secret"], limit)
        out = []
        for p in posts:
            pid = str(p.get("postid", ""))
            out.append({
                "post_id": pid,
                "title": p.get("title", ""),
                "url": p.get("link", ""),
                "edit_url": f"https://i.cnblogs.com/posts/edit;postId={pid}",
                "status": "published",
                "stats": {},
            })
        return out

    # ---------------- 发布 ----------------

    def publish(self, page, article, options=None):
        options = options or {}
        s, c = _client()
        bid = self._blogid(s, c)
        tags = [t.strip() for t in (article.get("tags") or "").split(",") if t.strip()]
        struct = {
            "title": article["title"],
            "description": article.get("content_md", ""),
            "categories": [MARKDOWN_FLAG] + tags,   # 不加这个会当 HTML 渲染
            "dateCreated": xmlrpc.client.DateTime(datetime.now()),
        }
        publish_flag = not options.get("draft_only")
        pid = s.metaWeblog.newPost(bid, c["username"], c["secret"], struct, publish_flag)
        pid = str(pid)
        return {"post_id": pid,
                "post_url": f"https://www.cnblogs.com/p/{pid}.html",
                "edit_url": f"https://i.cnblogs.com/posts/edit;postId={pid}",
                "draft_only": bool(options.get("draft_only"))}

    # ---------------- 原地更新 ----------------

    def update(self, page, pub, article):
        s, c = _client()
        pid = pub.get("post_id")
        if not pid:
            raise PlatformError("没有 post_id，更新不了")
        tags = [t.strip() for t in (article.get("tags") or "").split(",") if t.strip()]
        struct = {
            "title": article["title"],
            "description": article.get("content_md", ""),
            "categories": [MARKDOWN_FLAG] + tags,
            "dateCreated": xmlrpc.client.DateTime(datetime.now()),
        }
        # MetaWeblog 的 editPost 是全额覆盖，天然就是"原地更新"
        ok = s.metaWeblog.editPost(pid, c["username"], c["secret"], struct, True)
        if not ok:
            raise PlatformError(f"editPost 返回 {ok}")
        return True
