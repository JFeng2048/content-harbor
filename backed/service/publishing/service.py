# -*- coding: utf-8 -*-
"""业务层：把 文章库 × 内置浏览器 × 平台适配器 串起来。

AI 或者 REST API 调的都是这里的方法，不用碰浏览器细节。
"""

import atexit
import json
import os
import random
import threading
import time
from pathlib import Path

import hashlib

from service.publishing import db
from service.publishing.tasks import TaskManager
from service.publishing.adapters.base import PlatformError, get_adapter


def _content_hash(article):
    """内容指纹：update 前比对用。标题+正文+摘要任一变化都会触发更新。"""
    return hashlib.sha256(
        f"{article['title']}\n{article['content_md']}\n{article.get('summary') or ''}"
        .encode("utf-8")).hexdigest()
from service.publishing.browser import (BuiltinBrowser, ensure_login, CaptchaPolicy,
                          wait_human_captcha, browser_thread_run)
from service.publishing.observability import TraceContext, METRICS, emit
from service.publishing import gate as aigc_gate

ROOT = Path(__file__).resolve().parent.parent

# 导入即注册
from service.publishing.adapters import (  # noqa: F401
    bilibili, cnblogs, csdn, juejin, metaweblog, oschina, segmentfault, toutiao, zhihu, wuyi_cto,
)


class Hub:
    # 无头浏览器实例池上限。复用省掉每次发布 1~3 秒的启动开销；
    # 超出后按 LRU 关最旧的（每个实例是一个常驻 Chromium，别开太多）
    POOL_MAX = 4

    def __init__(self, headless=True):
        self.conn = db.connect()
        self.headless = headless
        # 演示模式（DEMO=1）：不开浏览器、不调外部 API，登录/发布/更新/AI 写稿
        # 全部模拟成功，用于产品演示与宣传片录制。任务引擎照常真实运转。
        self.demo = os.environ.get("DEMO") == "1"
        # 统一任务引擎：REST/MCP 的登录、发布、更新、同步全部走它（重构第一刀）
        self.tasks = TaskManager(self, self.conn)
        # 风控：平台间隔 + 文章间隔，别调太小，被限流了别来找我
        # 演示模式下不需要风控延迟，直接归零让流程顺畅
        self.delay_platform = (0, 0) if self.demo else (8, 20)
        self.delay_article = (0, 0) if self.demo else (30, 90)
        # 遇到验证码时怎么处理：handoff=交人工 / abort=直接放弃
        self.on_captcha = "handoff"
        # 无头浏览器实例池：key=(platform, account)，登录流程不走池（它要独立的有头实例）
        self._pool = {}
        self._pool_order = []
        # FastAPI 同步端点跑在线程池，多线程同时 _acquire 会竞态——加锁护住 LRU
        self._pool_lock = threading.Lock()
        # 体检 B3 修复（QA 标质力 2026-09-21）：per-key 互斥。同一 (platform,account)
        # 的浏览器实例是单线程玩物（Playwright sync 基于 greenlet），两个并发请求
        # 拿同一个实例 = greenlet 崩溃。_pool_lock 只护字典读写，这里补"实例占用"互斥。
        self._busy = {}
        # 进程退出兜底关浏览器（原来这行写在 _busy_for 的 return 后面，
        # 是永远执行不到的死代码——退出时浏览器从不自动关）
        atexit.register(self.close_all)

    def _busy_for(self, platform, account):
        """取（或建）per-key 互斥锁。调用方用 with 包住整个浏览器操作过程。"""
        key = (platform, account)
        with self._pool_lock:
            if key not in self._busy:
                self._busy[key] = threading.Lock()
            return self._busy[key]

    # ------------- 浏览器实例池 -------------

    def _acquire(self, platform, account):
        """拿（或起）一个 headless 实例。拿到的不关，池里常驻复用。"""
        key = (platform, account)
        with self._pool_lock:
            br = self._pool.get(key)
            if br is not None:
                if key in self._pool_order:
                    self._pool_order.remove(key)
                self._pool_order.append(key)          # touch LRU
                return br
            br = BuiltinBrowser(platform, account, headless=self.headless)
            self._pool[key] = br
            self._pool_order.append(key)
            while len(self._pool_order) > self.POOL_MAX:
                old = self._pool_order.pop(0)
                victim = self._pool.pop(old, None)
                if victim:
                    try:
                        victim.close()
                    except Exception:
                        pass
            return br

    def _drop(self, platform, account):
        """实例疑似崩了：踢出池关掉，下次 _acquire 会起全新的。
        关闭经 browser_thread_run 路由——实例的 greenlet 属于浏览器线程，
        跨线程 close 会抛（会被吞掉但状态关不干净）。"""
        key = (platform, account)
        with self._pool_lock:
            victim = self._pool.pop(key, None)
            if key in self._pool_order:
                self._pool_order.remove(key)
        if victim:
            try:
                browser_thread_run(victim.close)   # 已在浏览器线程则内联执行
            except Exception:
                pass

    def close_all(self):
        """进程退出前把池里所有浏览器关干净（atexit 兜底，CLI/serve 都生效）。"""
        try:
            self.tasks.close()
        except Exception:
            pass
        with self._pool_lock:
            victims = list(self._pool.values())
            self._pool.clear()
            self._pool_order.clear()
        for br in victims:
            try:
                browser_thread_run(br.close)
            except Exception:
                pass

    # ---------------- 账号 ----------------

    def login(self, platform, account="default", timeout=600, on_captcha=None):
        """扫码/过验证登录一次，登录态存进本地 profile，之后长期有效。"""
        if self.demo:
            db.upsert_account(self.conn, platform, account, "-", "logined")
            return True, "演示模式：模拟登录成功"
        ad = get_adapter(platform)
        # 纯协议平台不用开浏览器，直接验凭据
        if not ad.needs_browser:
            try:
                ok = ad.check_auth(None)
                db.upsert_account(self.conn, platform, account, "-",
                                  "logined" if ok else "offline")
                return ok, ("凭据有效（免登录 API）" if ok else "凭据无效，检查 config.json")
            except PlatformError as e:
                db.upsert_account(self.conn, platform, account, "-", "offline")
                return False, str(e)

        # profile 目录是独占的：先释放池里可能占着它的实例，不然有头浏览器起不来。
        # B3：整个登录过程持 per-key 互斥，防止与池实例/另一路登录争同一 profile
        with self._busy_for(platform, account):
            self._drop(platform, account)

            def _op():
                br = BuiltinBrowser(platform, account, headless=False)  # 登录必须有头
                try:
                    ok, msg = ensure_login(br, ad.login_url, ad.check_auth, timeout=timeout,
                                           on_captcha=on_captcha or self.on_captcha)
                    if ok:
                        # 登录态快照：Python 同步写盘（2026-09-22 掘金扫码成功但
                        # chromium 关窗前没刷 cookie、状态丢失的修复）
                        try:
                            br.export_auth()
                        except Exception:
                            pass
                    db.upsert_account(self.conn, platform, account,
                                      str(br.profile_dir), "logined" if ok else "offline")
                    return ok, msg
                finally:
                    br.close()
            return browser_thread_run(_op)

    def _check_auth_settled(self, ad, page, settle=2.0, tries=2):
        """登录态检查（带沉降重试）。

        竞态：goto 等到 domcontentloaded 后 SPA 可能仍在跳转/替换文档，
        立即 evaluate 打在销毁的 context 上会抛异常，被 check_auth 吞掉
        变成假"未登录"（2026-09-22 掘金无头复查连假的教训）。
        首次 False/异常 → 沉降 settle 秒再试一次。
        """
        for i in range(tries):
            try:
                if ad.check_auth(page):
                    return True
            except Exception:
                pass
            if i < tries - 1:
                time.sleep(settle)
        return False

    def check(self, platform, account="default"):
        if self.demo:
            return True
        ad = get_adapter(platform)
        if not ad.needs_browser:
            try:
                ok = ad.check_auth(None)
            except PlatformError:
                ok = False
            db.upsert_account(self.conn, platform, account, "-",
                              "logined" if ok else "offline")
            return ok
        # B3 补洞（2026-09-22）：check 同样要持 per-key 互斥。
        # 存量体检（2026-09-22）：浏览器操作全部经 browser_thread_run 下沉
        # 专属线程——greenlet/循环状态永远单线程，根治 "inside the asyncio
        # loop" 500（线程池复用 + dispatcher 挂起泄漏循环状态的组合病）。
        def _op():
            br = self._acquire(platform, account)
            page = None
            try:
                page = br.new_page()
                # 关键：check_auth 多在页面上下文里 fetch 平台 API。停在 about:blank
                # 上是 null 源跨站请求，SameSite cookie 全被拦 → data:null → 永远
                # 假"未登录"（2026-09-22 掘金复查连假的根因）。先落到平台域再查。
                target = ad.home_url or ad.login_url
                if target:
                    try:
                        page.goto(target, timeout=60000, wait_until="domcontentloaded")
                    except Exception:
                        pass  # 首页打不开不拦着，交给沉降重试兜底
                ok = self._check_auth_settled(ad, page)
                if ok:
                    # 登录态保鲜：检查通过即刷新快照——平台轮换会话后快照
                    # 跟着最新态走（2026-09-22 "一次登录一直记住"要求）
                    try:
                        br.export_auth()
                    except Exception:
                        pass
                # 登录态正常但页面在弹验证码，说明"能登但不一定能操作"，得告诉用户
                if ok and CaptchaPolicy.detect(page):
                    db.upsert_account(self.conn, platform, account, str(br.profile_dir),
                                      "logined")
                    return ok
                db.upsert_account(self.conn, platform, account, str(br.profile_dir),
                                  "logined" if ok else "offline")
                return ok
            except Exception:
                self._drop(platform, account)   # 页面出事：踢出池，下次用全新的
                raise
            finally:
                if page is not None:
                    try:
                        page.close()
                    except Exception:
                        pass
        with self._busy_for(platform, account):
            return browser_thread_run(_op)

    def logout(self, platform, account="default"):
        """清除某个平台的登录态：删 profile 目录 + auth 快照，账号状态置离线。

        登录态管理闭环：login(存) → check(验) → logout(清)。不清的话
        profile 目录会一直在磁盘上（cookie 也会过期，但留着占地方、易混淆）。
        """
        from service.publishing.browser import PROFILE_ROOT
        import shutil
        # 先把池里可能占着 profile 的实例释放掉，否则删不掉
        self._drop(platform, account)
        removed = []
        profile_dir = PROFILE_ROOT / f"{platform}_{account}"
        auth_file = PROFILE_ROOT / f"{platform}_{account}.auth.json"
        if profile_dir.exists():
            shutil.rmtree(profile_dir, ignore_errors=True)
            removed.append(str(profile_dir))
        if auth_file.exists():
            auth_file.unlink(missing_ok=True)
            removed.append(str(auth_file))
        # 数据库状态置离线
        self.conn.execute(
            "UPDATE accounts SET status='offline', last_check=? WHERE platform=? AND name=?",
            (time.time(), platform, account))
        self.conn.commit()
        return {"platform": platform, "removed": removed,
                "note": "登录态已清除，下次登录需重新扫码"}

    def diagnose(self, platform):
        """排查端点：这平台到底该怎么接入、验证码怎么过，一目了然。"""
        from service.publishing.browser import ensure_display
        ad = get_adapter(platform)
        info = {
            "platform": platform, "name": ad.name,
            "需要浏览器": ad.needs_browser,
            "登录页": ad.login_url,
            "反检测": "已启用（隐藏 webdriver / 伪装 WebGL 与硬件指纹 / 拟人输入鼠标）",
        }
        if platform in CaptchaPolicy.API_FIRST:
            info["推荐接入"] = CaptchaPolicy.API_FIRST[platform]
        info["验证码策略"] = (
            "免登 API，不会遇到验证码" if not ad.needs_browser else
            "L1 反检测降低触发 → L2 登录态持久化 → L3 弹了就半自动试一次，不行转人工"
        )
        if ad.needs_browser:
            info["有头显示"] = ensure_display() or "不可用（装 xvfb：apt install -y xvfb）"
        return info

    def assist_open(self, platform, url, timeout=900, account="default"):
        """带登录态的有头浏览器打开平台页——把"去平台互动"接进本机。

        演示模式：直接返回成功，不真开浏览器。
        用我们的 profile（已登录），用户在弹出窗口里完成平台侧最后一步
        （如掘金「确定并发布」），关窗即结束。登录态四层保障全程继承。"""
        if self.demo:
            return {"ok": True, "msg": "演示模式：模拟打开平台页（带登录态）"}
        with self._busy_for(platform, account):
            self._drop(platform, account)

            def _op():
                br = BuiltinBrowser(platform, account, headless=False)
                closed = threading.Event()
                try:
                    ctx = br.start()
                    page = ctx.new_page()
                    page.on('close', lambda _: closed.set())
                    page.goto(url, timeout=60000, wait_until='domcontentloaded')
                    closed.wait(timeout=timeout)
                    msg = ('平台页已关闭——如已完成操作，回管理页点「已处理，恢复」'
                           if closed.is_set() else f'assist 超时({timeout}s)自动关闭')
                    return {'ok': True, 'msg': msg}
                finally:
                    try:
                        br.close()
                    except Exception:   # aqg: top-level boundary（关窗兜底，assist 任务收尾）
                        pass
            return browser_thread_run(_op)

    def bootstrap_cnblogs(self, username, password, account="default",
                          timeout=600, on_captcha="handoff"):
        """浏览器登录博客园，登录后自动抠出 MetaWeblog 三件套写进 config.json。

        这是取代「让用户手贴令牌」的正确路径：账号+密码登一次，登录态存盘，
        设置页里把 endpoint/username/token 自动抠出来，之后发布走纯协议。
        """
        from service.publishing.browser import BuiltinBrowser
        from service.publishing.cnblogs_login import login_browser, extract_metaweblog
        from service.publishing.browser import ensure_display

        ensure_display()
        self._drop("cnblogs", account)   # profile 独占，先释放池里的实例

        def _op():
            br = BuiltinBrowser("cnblogs", account, headless=False)  # 登录必须有头
            try:
                r = login_browser(br, username, password,
                                  on_captcha=on_captcha, timeout=timeout)
                if r.get("outcome") != "success":
                    db.upsert_account(self.conn, "cnblogs", account, str(br.profile_dir),
                                      "offline")
                    return r
                # 登录成功，抠令牌（username 用登录名，别拿 blogApp 冒充）
                page = br.new_page()
                mw = extract_metaweblog(page, save_to=str(ROOT / "config.json"),
                                        login_username=username)
                page.close()
                db.upsert_account(self.conn, "cnblogs", account, str(br.profile_dir),
                                  "logined")
                r["metaweblog"] = mw
                return r
            finally:
                br.close()
        return browser_thread_run(_op)

    def solve_captcha(self, platform, account="default", wait=180):
        """打开平台页面，如果弹验证码就地处理：先半自动，不行转人工。

        这是给"登录时弹了验证码，想单独处理一下"准备的入口。
        """
        from service.publishing.browser import CaptchaPolicy, wait_human_captcha
        ad = get_adapter(platform)
        if not ad.needs_browser:
            return {"ok": True, "msg": f"{platform} 走免登 API，不会有验证码"}
        self._drop(platform, account)   # profile 独占，先释放池里的实例

        def _op():
            br = BuiltinBrowser(platform, account, headless=False)
            try:
                page = br.new_page()
                page.goto(ad.login_url, timeout=60000, wait_until="domcontentloaded")
                import time as _t
                _t.sleep(3)
                kind = CaptchaPolicy.detect(page)
                if not kind:
                    return {"ok": True, "msg": "当前页面没有验证码"}
                ok, info = wait_human_captcha(page, platform, timeout=wait)
                return {"ok": ok, "kind": kind, **info}
            finally:
                br.close()
        return browser_thread_run(_op)

    def accounts(self):
        return [dict(r) for r in db.list_accounts(self.conn)]

    # ---------------- 文章 ----------------

    def create(self, title, content_md="", **kw):
        return db.create_article(self.conn, title, content_md, **kw)

    def edit(self, article_id, **kw):
        """改文章。内容一改，已发布实例自动标成 pending，等 sync_pending 去同步。"""
        ok = db.update_article(self.conn, article_id, **kw)
        pending = db.get_pending_updates(self.conn)
        return ok, len(pending)

    def get(self, article_id):
        r = db.get_article(self.conn, article_id)
        return dict(r) if r else None

    def list(self, status=None, limit=100):
        return [dict(r) for r in db.list_articles(self.conn, status, limit)]

    def search(self, keyword):
        return [dict(r) for r in db.search_articles(self.conn, keyword)]

    def import_md(self, path, title=None, tags=""):
        from pathlib import Path
        p = Path(path).expanduser()
        # 路径越权防护：只允许导入项目根内的 Markdown 文件，拒绝符号链接逃逸。
        # 对标 2026 最小权限实践——API 客户端不应能借 import 读机器任意文件。
        root = ROOT.resolve()
        try:
            target = p.resolve()
        except Exception:
            raise ValueError(f"非法导入路径: {path}")
        if not target.is_file():
            raise ValueError(f"导入文件不存在: {target}")
        if target != root and root not in target.parents:
            raise ValueError(f"导入路径越权（仅允许项目目录内）: {target}")
        text = target.read_text(encoding="utf-8", errors="replace")
        if text.startswith("---"):  # 顺手吃掉 front-matter 当元数据
            parts = text.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].splitlines():
                    if line.lower().startswith("title:"):
                        title = title or line.split(":", 1)[1].strip()
                    if line.lower().startswith("tags:"):
                        tags = tags or line.split(":", 1)[1].strip().strip("[]")
                text = parts[2]
        title = title or p.stem
        aid = db.create_article(self.conn, title, text.lstrip("\n"),
                                tags=tags, source="import")
        return aid

    # ---------------- 发布 / 更新 ----------------

    def _with_adapter(self, platform, account, fn, page_hook=None):
        """统一入口：需要浏览器的开浏览器，走协议的直接调。
        浏览器从池里拿，常驻复用；页面用完即关（ctx 保留）。
        page_hook(page)：页面就绪后回调（已废弃，保留签名以兼容旧调用），
        必须在浏览器操作线程内调用（greenlet 约束）。"""
        ad = get_adapter(platform)
        if not ad.needs_browser:
            if not ad.check_auth(None):
                raise PlatformError(f"{platform} 凭据无效，检查 config.json")
            return fn(ad, None)

        # B3：同一实例同时只允许一个操作者，等也要等在这（公平串行）。
        # 存量体检（2026-09-22）：操作体下沉专属浏览器线程（greenlet 同线程）。
        with self._busy_for(platform, account):
            def _op():
                page = None
                for attempt in (1, 2):
                    br = self._acquire(platform, account)
                    try:
                        page = br.new_page()
                        # 先把页面带到平台域再发 API：新开的 page 停在 about:blank 上是
                        # null origin，fetch 属于跨域，cookie 带不上还会被 CORS 拦下。
                        # 落到平台自己的页面上，后面的 api_get/api_post 就是同源请求。
                        try:
                            page.goto(ad.home_url, timeout=60000, wait_until="domcontentloaded")
                        except Exception:
                            pass  # 首页打不开不拦着纯 API 调用，尽力继续
                        if not self._check_auth_settled(ad, page):
                            raise PlatformError(f"{platform}({account}) 未登录，先跑 login")
                        if page_hook:
                            try:
                                page_hook(page)
                            except Exception:
                                pass  # 预览挂载失败不影响发布主流程
                        return fn(ad, page)
                    except PlatformError:
                        raise                       # 业务错误（未登录/配置缺失），重试没意义
                    except Exception as e:
                        if attempt == 2:
                            raise
                        # 像浏览器/页面崩了的错误：踢出池换全新实例再试一次
                        # （greenlet 跨线程冲突=池实例被别的线程创建，重建即在当前线程）
                        if any(s in str(e) for s in ("Target closed", "Browser has been closed",
                                                     "Session closed", "浏览器启动失败",
                                                     "Cannot switch to a different thread",
                                                     "greenlet")):
                            self._drop(platform, account)
                            continue
                        raise
                    finally:
                        if page is not None:
                            try:
                                page.close()
                            except Exception:
                                pass
                            page = None
            return browser_thread_run(_op)

    # ---------------- AI ----------------

    def _demo_article(self, topic, style="", words=2000, tags_hint=""):
        """演示模式下的 AI 写稿：本地模板生成，不依赖 LLM。"""
        import hashlib
        seed = hashlib.md5(topic.encode("utf-8")).hexdigest()[:4]
        return {
            "title": topic,
            "summary": f"《{topic}》深度解读：从背景到实践，一文讲透（演示文章）。",
            "content_md": (
                f"# {topic}\n\n"
                f"> 这是一篇由 **AI 内容中台** 在演示模式下生成的文章（DEMO 演示）。\n\n"
                f"## 背景\n\n{topic}正在成为内容创作者关注的焦点。"
                f"本文带你从零了解它的来龙去脉、核心概念与落地方法。\n\n"
                f"## 核心要点\n\n"
                f"1. **统一入口**：一个后台管理所有内容平台，不用再逐站登录、逐站发布。\n"
                f"2. **一次登录**：扫码一次，登录态长期复用，之后全自动发布。\n"
                f"3. **一键多投**：选中目标平台，一篇文章同时发往知乎、掘金、CSDN 等。\n"
                f"4. **原地更新**：改一处，已发布文章全平台同步更新，不产生重复内容。\n"
                f"5. **人工兜底**：平台风控或验证码出现时，任务自动转人工，处理后可恢复。\n\n"
                f"## 适用场景\n\n"
                f"个人博客、技术社区运营、自媒体矩阵维护，都可以用它把重复劳动交给自动化。\n\n"
                f"## 写在最后\n\n"
                f"内容中台的价值在于：**把时间还给创作，把重复交给机器**。"
                f"（本文为产品演示而生成，实际发布内容由你的真实文章决定。）\n"
            ),
            "tags": (tags_hint or "AI,内容中台,自动化"),
            "ai_model": "demo-local",
            "ext": "{}",
        }

    def ai_write(self, topic, style="", words=2000, tags_hint="", publish_to=None):
        """AI 写一篇并入库。传了 publish_to 就顺手发出去。

        合规闸门：AI 源文章发布强制 draft_only（人审闸门），禁止 AI 内容
        直接正式上线。想上线须人工二次确认后再调 publish(draft_only=False)。
        """
        if self.demo:
            art = self._demo_article(topic, style, words, tags_hint)
        else:
            from service.publishing import ai as ai_mod
            art = ai_mod.write_article(topic, style, words, tags_hint)
        # 入库前打 AIGC 标识（法规要求显式标识 + 可追溯模型来源）
        art = aigc_gate.add_aigc_label(art, art.get("ai_model", ""))
        ext = json.loads(art.get("ext", "{}") or {})
        aid = db.create_article(self.conn, art["title"], art["content_md"],
                                summary=art["summary"], tags=art["tags"],
                                source="ai", ai_model=art.get("ai_model", ""),
                                ext=json.dumps(ext, ensure_ascii=False),
                                status="draft")
        out = {"id": aid, "title": art["title"], "summary": art["summary"],
               "tags": art["tags"], "chars": len(art["content_md"]),
               "aigc_labeled": True}
        if publish_to:
            # 人审闸门：AI 内容只发草稿，正式上线需人工确认后单独 publish
            out["publish"] = self.publish(aid, publish_to, draft_only=True)
            out["note"] = "AI 内容已按合规闸门以草稿(draft_only)发布；" \
                          "确认无误后请调 /articles/{id}/publish(draft_only=false) 正式上线"
        return out

    def ai_rewrite(self, article_id, instruction, publish_to=None):
        """AI 改写已有文章，改完自动标记待同步。"""
        from service.publishing import ai as ai_mod
        art = self.get(article_id)
        if not art:
            raise ValueError(f"文章 {article_id} 不存在")
        new_md = ai_mod.rewrite(art["content_md"], instruction)
        db.update_article(self.conn, article_id, content_md=new_md)
        out = {"id": article_id, "chars": len(new_md),
               "pending_sync": len(db.get_pending_updates(self.conn))}
        if publish_to:
            out["update"] = self.update(article_id, publish_to)
        return out

    def ai_polish(self, article_id):
        from service.publishing import ai as ai_mod
        art = self.get(article_id)
        if not art:
            raise ValueError(f"文章 {article_id} 不存在")
        new_md = ai_mod.polish(art["content_md"])
        db.update_article(self.conn, article_id, content_md=new_md)
        return {"id": article_id, "pending_sync": len(db.get_pending_updates(self.conn))}

    def ai_ready(self):
        if self.demo:
            return True
        from service.publishing import ai as ai_mod
        return ai_mod.is_ready()

    def publish_single(self, article_id, platform, article, account="default",
                       draft_only=False, page_hook=None, settings=None):
        """发布到单个平台并完成落库（jobs/publications 记账）。

        演示模式：直接返回模拟成功（含平台域名下的模拟链接），
        让任务引擎、发布记录、前端全链路真实呈现，只差"真的打到平台"。"""
        if self.demo:
            # 轻延迟：让前端能捕捉到任务 running → ok 的真实流转，而非秒过
            time.sleep(0.8 + random.random() * 0.9)
            from service.publishing.adapters.base import get_adapter as _ga
            _nm = _ga(platform).name
            _demo_hosts = {
                "zhihu": "zhuanlan.zhihu.com/p/", "bilibili": "www.bilibili.com/read/cv",
                "cnblogs": "www.cnblogs.com/demo/p/", "csdn": "blog.csdn.net/demo/article/details/",
                "juejin": "juejin.cn/post/",
                "oschina": "my.oschina.net/demo/blog/", "segmentfault": "segmentfault.com/a/",
                "toutiao": "www.toutiao.com/article/",
            }
            import random as _r
            _pid = str(_r.randint(7000000000000000000, 9999999999999999999))
            _url = "https://" + _demo_hosts.get(platform, "example.com/") + _pid
            db.upsert_publication(self.conn, article_id, platform, account,
                                  post_id=_pid, post_url=_url,
                                  edit_url=_url + "/edit",
                                  status="ok" if not draft_only else "pending",
                                  draft_only=1 if draft_only else 0,
                                  content_hash=_content_hash(article),
                                  published_at=db.now())
            db.finish_job(self.conn,
                          db.add_job(self.conn, "publish", article_id, platform),
                          True, "演示模式：发布成功")
            return {"platform": platform, "ok": True, "status": "ok",
                    "post_id": _pid, "post_url": _url, "edit_url": _url + "/edit",
                    "draft_only": draft_only, "demo": True,
                    "note": f"已模拟发布到《{_nm}》（演示模式）"}
        """发布到单个平台并完成落库（jobs/publications 记账）。

        统一入口：legacy 与任务引擎都走这里（重构第一刀）
        共用的唯一发布原语。成功返回结果 dict（platform/ok/status/post_id/...），
        失败在完成失败记账后抛异常。
        """
        job = db.add_job(self.conn, "publish", article_id, platform)
        try:
            def _do(ad, page):
                # 平台特有字段从 options 下发（标签/分类/摘要等），
                # 各适配器自行决定用哪些、忽略哪些。
                # 发布面板里手动设置的（settings[platform]）优先于文章字段。
                ps = (settings or {}).get(platform) or {}
                art_tags = [t.strip() for t in (article.get("tags") or "").split(",")
                            if t.strip()]
                set_tags = [t.strip() for t in (ps.get("tags") or "").split(",")
                            if t.strip()]
                tag_list = set_tags or art_tags
                return ad.publish(page, article, {
                    "draft_only": draft_only,
                    "tags": tag_list,                 # 标签：面板设置 > 文章 tags
                    "tag_category": tag_list[0] if tag_list else "",
                    "category": (ps.get("category") or "").strip() or None,
                    "summary": article.get("summary") or "",
                })
            r = self._with_adapter(platform, account, _do, page_hook=page_hook)
            # 体检 B1 修复（QA 标质力 2026-09-21）：适配器返回 error 键时
            # 必须走失败分支，否则"发布未完成"会被静默记成"发布成功"
            if r.get("error"):
                raise PlatformError(str(r["error"]))
            warning = r.get("warning", "")
            # 体检 B10 修复：非用户主动要求的 draft_only（如掘金自动发布
            # 失败回落到草稿）→ 记 pending_human，可程序化列出"哪些草稿
            # 等人点发布"；这类平台不算发布完成，文章状态收敛保持 draft
            status = "ok"
            if r.get("draft_only") and not draft_only:
                status = "pending_human"
            db.upsert_publication(self.conn, article_id, platform, account,
                                  post_id=r.get("post_id", ""),
                                  post_url=r.get("post_url", ""),
                                  edit_url=r.get("edit_url", ""),
                                  status=status,
                                  draft_only=1 if r.get("draft_only") else 0,
                                  content_hash=_content_hash(article),
                                  published_at=db.now())
            db.finish_job(self.conn, job, True,
                          "发布成功" + (f"（警告: {warning}）" if warning else ""))
            out = {"platform": platform, "ok": True, "status": status,
                   "post_id": r.get("post_id", ""), "post_url": r.get("post_url", ""),
                   "edit_url": r.get("edit_url", ""),
                   "draft_only": r.get("draft_only", "")}
            # 适配器可能带回额外键，透传（不含内部键）
            out.update({k: v for k, v in r.items()
                        if k not in ("error", "warning", "post_id", "post_url",
                                     "edit_url", "draft_only")})
            if warning:
                out["warning"] = warning
            return out
        except Exception as e:
            db.upsert_publication(self.conn, article_id, platform, account,
                                  status="failed", last_error=str(e)[:300])
            db.finish_job(self.conn, job, False, str(e)[:300])
            raise

    def publish(self, article_id, platforms, account="default", draft_only=False,
                page_hook=None, settings=None):
        art = self.get(article_id)
        if not art:
            raise ValueError(f"文章 {article_id} 不存在")
        # AIGC 合规门禁：发布前强制过闸（安全扫描 + 双模型审查 + 人审闸门）
        try:
            gate_r = aigc_gate.apply_gate_before_publish(art, draft_only=draft_only)
        except aigc_gate.GateError as ge:
            # 门禁拒绝：记入 jobs（每个平台各一条），便于 /ai/gate 端点追溯
            for pf in platforms:
                jid = db.add_job(self.conn, "publish", article_id, pf)
                db.finish_job(self.conn, jid, False, f"合规门禁拒绝: {str(ge)[:200]}")
            # 抛 HTTPException（422 语义"内容不合规"），让 FastAPI 返回 4xx 而非 500
            from fastapi import HTTPException
            raise HTTPException(422, f"合规门禁拒绝发布: {ge}")
        art = gate_r["article"]   # AI 源已打 AIGC 标识
        if not (art.get("title") or "").strip():
            raise ValueError("文章标题为空，拒绝发布（B19 预检）")
        results = []
        all_ok = True
        # 发布链路 trace：所有平台子步骤串进同一 trace_id，事后看卡点
        with TraceContext("publish", article_id=article_id,
                          platforms=platforms, draft_only=draft_only,
                          account=account, aigc=gate_r.get("aigc_labeled", False)) as tctx:
            for pf in platforms:
                _t0 = time.time()
                try:
                    r = self.publish_single(article_id, pf, art, account=account,
                                            draft_only=draft_only, page_hook=page_hook,
                                            settings=settings)
                except Exception as e:
                    all_ok = False
                    results.append({"platform": pf, "ok": False, "error": str(e)})
                    tctx.step(f"{pf}.publish", dur=time.time() - _t0, ok=False,
                               detail=str(e)[:160])
                else:
                    # 体检 B10 修复（QA 标质力 2026-09-21）：回落草稿（pending_human）
                    # 不算发布完成，文章状态收敛保持 draft
                    if r.get("status") == "pending_human":
                        all_ok = False
                    results.append(r)
                    tctx.step(f"{pf}.publish", dur=time.time() - _t0, ok=True,
                               detail=str(r.get("post_id", ""))[:80])
                if pf != platforms[-1]:
                    time.sleep(random.uniform(*self.delay_platform))
        # 状态收敛：全部成功才标 published；有失败保持 draft 并留待重试，
        # 避免中间一个平台失败就把整篇文章误标成已发布
        if all_ok and not draft_only:
            db.update_article(self.conn, article_id, status="published")
        return results

    def update_single(self, article_id, platform, pub, article, account="default"):
        """原地更新单个平台实例并完成落库（jobs/publications 记账）。

        演示模式：直接返回更新成功。"""
        if self.demo:
            db.upsert_publication(self.conn, article_id, platform, account,
                                  status="ok", last_error="", draft_only=0,
                                  content_hash=_content_hash(article),
                                  updated_at=db.now())
            db.finish_job(self.conn,
                          db.add_job(self.conn, "update", article_id, platform),
                          True, "演示模式：更新成功")
            return {"platform": platform, "ok": True, "demo": True,
                    "note": "演示模式：模拟更新成功"}
        """原地更新单个平台实例并完成落库（jobs/publications 记账）。

        legacy update() 循环体与工作流节点 update_instance 共用的唯一更新原语
        （对称于 publish_single，M5/ADR-007）。pub 携带 post_id/edit_url。
        成功返回 {'platform', 'ok': True}；失败在完成失败记账后抛异常。
        平台间 sleep 由本层统一控制——
        本方法为逐行搬移 legacy 循环体（R3 门禁：行为逐字不变）。"""
        # 内容没变就不空发：改过的才值得占平台额度（B13 数据层加固）
        pub_hash = pub["content_hash"] if isinstance(pub, dict) else pub["content_hash"]
        if pub_hash == _content_hash(article):
            return {"platform": platform, "ok": True, "skipped": "内容未变化"}

        job = db.add_job(self.conn, "update", article_id, platform)
        try:
            def _do(ad, page):
                return ad.update(page, dict(pub), article)
            self._with_adapter(platform, account, _do)
            db.upsert_publication(self.conn, article_id, platform, account,
                                  status="ok", last_error="",
                                  draft_only=0, content_hash=_content_hash(article),
                                  updated_at=db.now())
            db.finish_job(self.conn, job, True, "原地更新成功")
            return {"platform": platform, "ok": True}
        except Exception as e:   # aqg: top-level boundary（失败记账后重抛，publish_single 对称）
            db.upsert_publication(self.conn, article_id, platform, account,
                                  last_error=str(e)[:300])
            db.finish_job(self.conn, job, False, str(e)[:300])
            raise

    def update(self, article_id, platforms=None, account="default"):
        """原地更新：打开各平台的编辑页改内容，改完就是更新，不是新发一篇。"""
        art = self.get(article_id)
        if not art:
            raise ValueError(f"文章 {article_id} 不存在")
        pubs = db.get_publications(self.conn, article_id=article_id)
        if platforms:
            pubs = [p for p in pubs if p["platform"] in platforms]
        pubs = [p for p in pubs if p["post_id"] or p["edit_url"]]
        if not pubs:
            return {"skipped": "没有已发布实例可更新，先 publish"}

        results = []
        for p in pubs:
            try:
                r = self.update_single(article_id, p["platform"], p, art,
                                       account=account)
            except Exception as e:   # aqg: top-level boundary（单平台失败记错误行，循环继续）
                results.append({"platform": p["platform"],
                                "ok": False, "error": str(e)})
            else:
                results.append(r)
            # 体检 B12 修复（QA 标质力 2026-09-21）：最后一个平台不再空等 30-90s
            if p is not pubs[-1]:
                time.sleep(random.uniform(*self.delay_article))
        return results

    def sync_pending(self, account="default"):
        """把内容变更同步到所有已发布平台——AI 改完文章点这个就完事。
        按文章聚合其全部 pending 平台，一次 update 同步到位，避免逐行漏同步。"""
        rows = db.get_pending_updates(self.conn)
        by_article = {}
        for r in rows:
            by_article.setdefault(r["article_id"], {"title": r["title"], "platforms": []})
            by_article[r["article_id"]]["platforms"].append(r["platform"])
        out = []
        for aid, info in by_article.items():
            platforms = sorted(set(info["platforms"]))
            res = self.update(aid, platforms=platforms, account=account)
            out.append({"article_id": aid, "title": info["title"],
                        "platforms": platforms,
                        "result": res.get("results") if isinstance(res, dict) else res})
        return out

    def refresh(self, platform, account="default", limit=50):
        """把平台上的文章列表抓回来入库，AI 才能"看见账号里有什么"。"""
        if self.demo:
            items = [{
                "post_id": f"demo-{platform}-{i}", "title": f"《{platform} 平台演示文章 {i}》",
                "url": f"https://example.com/{platform}/{i}", "edit_url": "",
                "status": "published", "stats": {"read": 100 + i * 7, "like": 5 + i},
            } for i in range(1, 4)]
            for it in items:
                aid = db.create_article(self.conn, it["title"], "",
                                        status="published", source="import")
                db.upsert_publication(self.conn, aid, platform, account,
                                      post_id=it["post_id"], post_url=it["url"],
                                      edit_url="", status="ok",
                                      stats=json.dumps(it["stats"]), draft_only=0)
            self.conn.commit()
            return {"platform": platform, "count": len(items), "saved": len(items),
                    "items": items, "demo": True}
        def _do(ad, page):
            return ad.list_articles(page, limit=limit)
        items = self._with_adapter(platform, account, _do)
        saved = 0
        for it in items:
            # 已有同 post_id 的更新，否则新建一条孤儿记录等人工关联
            row = self.conn.execute(
                "SELECT * FROM publications WHERE platform=? AND post_id=?",
                (platform, it["post_id"])).fetchone()
            if row:
                self.conn.execute(
                    "UPDATE publications SET edit_url=?, post_url=?, stats=?, status='ok' WHERE id=?",
                    (it.get("edit_url", ""), it.get("url", ""),
                     json.dumps(it.get("stats", {}), ensure_ascii=False), row["id"]))
            else:
                aid = db.create_article(self.conn, it["title"], "",
                                        status="published", source="import")
                db.upsert_publication(self.conn, aid, platform, account,
                                      post_id=it["post_id"], post_url=it.get("url", ""),
                                      edit_url=it.get("edit_url", ""), status="ok",
                                      stats=json.dumps(it.get("stats", {}), ensure_ascii=False),
                                      draft_only=0)
            saved += 1
        self.conn.commit()
        return {"platform": platform, "count": len(items), "saved": saved, "items": items}

    def status(self):
        arts = self.conn.execute("SELECT COUNT(*) c FROM articles").fetchone()["c"]
        pubs = self.conn.execute("SELECT COUNT(*) c FROM publications").fetchone()["c"]
        ok = self.conn.execute(
            "SELECT COUNT(*) c FROM publications WHERE status='ok'").fetchone()["c"]
        pend = self.conn.execute(
            "SELECT COUNT(*) c FROM publications WHERE status='pending'").fetchone()["c"]
        return {"articles": arts, "publications": pubs, "published": ok,
                "pending_sync": pend, "accounts": self.accounts()}
