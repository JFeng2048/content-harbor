# -*- coding: utf-8 -*-
"""REST API：AI 或你自己的脚本通过这个管整个中台。

已深度合并进新的 FastAPI 后端：本模块导出 ``hub_router``（APIRouter）与
``register_hub(app)``，由 ``app/factory.py`` 在 ``backed/start.py`` 统一装配；
同时保留 ``app`` 以便独立运行（``python -m api.hub`` / ``uvicorn api.hub:app``）。
"""

import json
import os
import time
from ipaddress import ip_address, ip_network
from pathlib import Path
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from service.publishing.service import Hub
from service.publishing import observability as obs

ROOT = Path(__file__).resolve().parent.parent

hub = Hub(headless=True)
hub_router = APIRouter()


# ---------------- 可选 API 鉴权 ----------------
# config.json 里配 "api_token": "一串随机字符串" 即启用：
# 非信任来源的所有请求，必须带 X-API-Token 头。默认不配 = 不启用（本地用）。
# 信任来源：本机回环 / testclient / 信任网段（可经环境变量 TRUSTED_NETS 追加 CIDR）。
def _api_token():
    try:
        return (json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
                or {}).get("api_token") or ""
    except Exception:
        return ""


def _trusted_sources():
    """本机回环 + 测试客户端 + 配置的信任网段（CIDR）。"""
    nets = ["127.0.0.0/8", "::1/128"]
    extra = os.environ.get("TRUSTED_NETS", "").strip()
    if extra:
        nets += [n.strip() for n in extra.split(",") if n.strip()]
    return nets


def _client_ip(request):
    """反代感知取真实客户端 IP：优先 X-Forwarded-For 首个，回退到直连 host。"""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        first = fwd.split(",")[0].strip()
        try:
            return ip_address(first)
        except ValueError:
            pass
    host = request.client.host if request.client else ""
    if host:
        try:
            return ip_address(host)
        except ValueError:
            pass
    return None


def _is_trusted(request):
    ip = _client_ip(request)
    if ip is None:
        return False
    for net in _trusted_sources():
        try:
            if ip in ip_network(net, strict=False):
                return True
        except Exception:
            continue
    return False


def _attach_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def _auth(request, call_next):
        token = _api_token()
        if token and not _is_trusted(request) \
                and request.headers.get("X-API-Token") != token:
            return JSONResponse({"detail": "无效的 API Token"}, status_code=401)
        return await call_next(request)

    # ---------------- 可观测性：结构化 access log + 指标 ----------------
    # 每个 API 请求落一条 JSON 行到 data/observability/events.log，
    # 带 method/path/status/duration/client_ip，排障时直接 grep 链路。
    # /metrics 自身不记录（避免指标端点把日志刷爆）。
    _LOG_SKIP = ("/metrics", "/health", "/docs", "/openapi.json", "/redoc")

    @app.middleware("http")
    async def _access_log(request, call_next):
        t0 = time.time()
        resp = await call_next(request)
        dur = round(time.time() - t0, 3)
        path = request.url.path
        if not any(path.startswith(s) for s in _LOG_SKIP):
            status = getattr(resp, "status_code", 0)
            ok = 200 <= status < 400
            obs.METRICS.incr(f"api.{ 'ok' if ok else 'fail' }")
            obs.METRICS.observe("api.dur", dur)
            obs.METRICS.incr(f"api.{request.method.lower()}.hits")
            obs.emit("api.access",
                     method=request.method, path=path, status=status,
                     duration=dur,
                     client_ip=(request.client.host if request.client else ""))
        return resp


# ---------------- CORS（默认仅同源；跨域部署时用环境变量 CORS_ORIGINS 白名单） ----------------
_cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]


class ArticleIn(BaseModel):
    title: str
    content_md: str = ""
    summary: str = ""
    tags: str = ""
    cover: str = ""
    status: str = "draft"
    source: str = "human"   # AI 写稿时由 service 显式传 ai，别默认标成 AI
    ai_model: str = ""


class ArticlePatch(BaseModel):
    title: Optional[str] = None
    content_md: Optional[str] = None
    summary: Optional[str] = None
    tags: Optional[str] = None
    cover: Optional[str] = None
    status: Optional[str] = None


class PublishIn(BaseModel):
    platforms: List[str]
    account: str = "default"
    draft_only: bool = False
    live: bool = False      # true=附带实时预览页（异步端点专用）
    settings: Optional[Dict[str, Dict]] = None  # 平台特有字段：{平台id: {category, tags}}


class UpdateIn(BaseModel):
    platforms: Optional[List[str]] = None   # None/缺省 = 全部可更新实例
    account: str = "default"


class ResumeIn(BaseModel):
    approved: bool = True
    note: str = ""


class ImportIn(BaseModel):
    path: str
    tags: str = ""


class AIWriteIn(BaseModel):
    topic: str
    style: str = ""
    words: int = 2000
    tags_hint: str = ""
    publish_to: Optional[List[str]] = None


class AIRewriteIn(BaseModel):
    instruction: str
    publish_to: Optional[List[str]] = None


@hub_router.get("/status")
def status():
    return hub.status()


# ---------------- 文章 ----------------

@hub_router.get("/articles")
def list_articles(status: str = None, limit: int = 100):
    return hub.list(status, limit)


@hub_router.post("/articles")
def create_article(a: ArticleIn):
    return {"id": hub.create(**a.dict())}


@hub_router.get("/articles/{aid}")
def get_article(aid: int):
    r = hub.get(aid)
    if not r:
        raise HTTPException(404, "文章不存在")
    return r


@hub_router.put("/articles/{aid}")
def update_article(aid: int, patch: ArticlePatch):
    data = {k: v for k, v in patch.dict().items() if v is not None}
    ok, pending = hub.edit(aid, **data)
    return {"ok": ok, "pending_sync": pending}


@hub_router.get("/articles/search/{keyword}")
def search(keyword: str):
    return hub.search(keyword)


@hub_router.post("/articles/import")
def import_md(body: ImportIn):
    return {"id": hub.import_md(body.path, tags=body.tags)}


# ---------------- 发布 / 更新 / 同步（统一任务引擎语义，重构第一刀） ----------------
# 三套入口（legacy 同步 / async / workflow）合并为一套：提交任务 → 返回 task_id →
# 轮询 GET /tasks/{task_id}。AI/无人值守与 Web 前端走同一条路，不再有回退分支。

@hub_router.post("/articles/{aid}/publish")
def publish(aid: int, body: PublishIn):
    """异步发布：提交到统一任务引擎，立即返回 task_id，轮询 GET /tasks/{task_id}。"""
    task_id = hub.tasks.submit("publish", article_id=aid, platforms=body.platforms,
                               account=body.account, draft_only=body.draft_only,
                               settings=body.settings)
    return {"task_id": task_id, "status": "pending", "poll": f"/tasks/{task_id}"}


@hub_router.post("/articles/{aid}/update")
def update(aid: int, body: UpdateIn):
    """异步原地更新：提交任务，轮询 GET /tasks/{task_id}。"""
    task_id = hub.tasks.submit("update", article_id=aid, platforms=body.platforms,
                               account=body.account)
    return {"task_id": task_id, "status": "pending", "poll": f"/tasks/{task_id}"}


@hub_router.post("/sync/pending")
def sync_pending(body: Optional[UpdateIn] = None):
    """异步同步扇出：把所有待更新实例提交一个 sync 任务，引擎内部分组执行。"""
    account = body.account if body else "default"
    task_id = hub.tasks.submit("sync", account=account)
    return {"task_id": task_id, "status": "pending", "poll": f"/tasks/{task_id}"}


# ---------------- 统一任务查询 / 恢复 ----------------

@hub_router.get("/tasks")
def tasks_list(limit: int = 50, kind: str = None, status: str = None):
    """任务列表（替代原 /runs）：按 kind/status 过滤，默认返回最近 50 条。"""
    return hub.tasks.list(limit=limit, kind=kind, status=status)


@hub_router.get("/tasks/{task_id}")
def tasks_detail(task_id: str):
    """查询任意任务状态：pending / running / ok / failed / waiting_human。"""
    t = hub.tasks.get(task_id)
    if not t:
        raise HTTPException(404, "任务不存在或已过期")
    t = dict(t)
    try:
        t["result"] = json.loads(t.get("result") or "{}")
    except Exception:
        t["result"] = {}
    try:
        t["platforms"] = json.loads(t.get("platforms") or "[]")
    except Exception:
        t["platforms"] = []
    return t


@hub_router.post("/tasks/{task_id}/resume")
def tasks_resume(task_id: str, body: Optional[ResumeIn] = None):
    """恢复 waiting_human 任务：approved=true 重新执行；false 标记放弃。"""
    approved = body.approved if body else True
    r = hub.tasks.resume(task_id, approved=approved)
    if not r.get("ok"):
        raise HTTPException(409, r.get("error", "恢复失败"))
    return r


@hub_router.get("/pending-human")
def pending_human():
    """需要人工处理的发布实例（如掘金草稿等人点"确定并发布"）。
    前端轮询这个端点做角标提醒；点"去处理"直接打开草稿编辑页。"""
    rows = hub.conn.execute(
        """SELECT p.article_id, a.title, p.platform, p.account, p.edit_url,
                  p.post_id, p.updated_at
           FROM publications p LEFT JOIN articles a ON a.id = p.article_id
           WHERE p.status = 'pending_human'
           ORDER BY p.updated_at DESC""").fetchall()
    return [dict(r) for r in rows]


@hub_router.get("/publications")
def publications(article_id: int = None, platform: str = None):
    sql = ("SELECT p.*, a.title FROM publications p "
           "LEFT JOIN articles a ON a.id = p.article_id WHERE 1=1")
    args = []
    if article_id is not None:
        sql += " AND p.article_id=?"
        args.append(article_id)
    if platform is not None:
        sql += " AND p.platform=?"
        args.append(platform)
    sql += " ORDER BY p.updated_at DESC"
    return [dict(r) for r in hub.conn.execute(sql, args).fetchall()]


# ---------------- 账号 / 平台 ----------------

@hub_router.get("/platforms")
def platforms():
    from service.publishing.adapters.base import ADAPTERS
    return [{"id": a.id, "name": a.name, "needs_browser": a.needs_browser}
            for a in ADAPTERS.values()]


@hub_router.get("/accounts")
def accounts():
    return hub.accounts()


@hub_router.get("/accounts/{platform}/check")
def check_account(platform: str, account: str = "default"):
    return {"platform": platform, "logined": hub.check(platform, account)}


class LoginIn(BaseModel):
    account: str = "default"
    timeout: int = 600
    # handoff=弹验证码就暂停交人工（默认）；abort=无人值守时直接放弃
    on_captcha: str = "handoff"


@hub_router.post("/accounts/{platform}/login")
def login(platform: str, body: LoginIn):
    """异步启动登录：提交任务，轮询 GET /tasks/{task_id}。
    引擎会开有头浏览器去平台登录页等扫码，登录态落盘后任务结束；
    遇验证码默认 handoff 交人工（无人值守可传 on_captcha=abort）。"""
    task_id = hub.tasks.submit("login", platforms=[platform], account=body.account)
    return {"task_id": task_id, "platform": platform, "status": "pending",
            "poll": f"/tasks/{task_id}"}


@hub_router.delete("/accounts/{platform}")
def logout(platform: str):
    """清除登录态：删 profile + cookie 快照，账号状态置离线。"""
    r = hub.logout(platform)
    return {"ok": True, **r}


@hub_router.get("/accounts/{platform}/diagnose")
def diagnose(platform: str):
    """这个平台该怎么接、验证码怎么过——排查用。"""
    return hub.diagnose(platform)


class CaptchaIn(BaseModel):
    account: str = "default"
    wait: int = 180


@hub_router.post("/accounts/{platform}/solve-captcha")
def solve_captcha(platform: str, body: CaptchaIn):
    """打开页面就地处理验证码：先半自动试，不行转人工。"""
    return hub.solve_captcha(platform, body.account, body.wait)


class AssistIn(BaseModel):
    url: str
    timeout: int = 900


@hub_router.post("/accounts/{platform}/assist")
def assist_open(platform: str, body: AssistIn):
    """带登录态的内置有头浏览器打开平台页（人工步骤接管），提交任务轮询结果。"""
    if not body.url.startswith(("http://", "https://")):
        raise HTTPException(422, "url 必须是 http(s) 地址")
    task_id = hub.tasks.submit("assist", platforms=[platform], url=body.url)
    return {"task_id": task_id, "status": "pending", "poll": f"/tasks/{task_id}"}


@hub_router.post("/refresh/{platform}")
def refresh(platform: str, limit: int = 50):
    """异步抓取平台文章入库：提交任务，轮询 GET /tasks/{task_id}。"""
    task_id = hub.tasks.submit("refresh", platforms=[platform])
    return {"task_id": task_id, "status": "pending", "poll": f"/tasks/{task_id}"}


# ---------------- AI 写稿 ----------------

@hub_router.post("/ai/write")
def ai_write(body: AIWriteIn):
    return hub.ai_write(body.topic, body.style, body.words,
                        body.tags_hint, body.publish_to)


@hub_router.post("/articles/{aid}/ai-rewrite")
def ai_rewrite(aid: int, body: AIRewriteIn):
    return hub.ai_rewrite(aid, body.instruction, body.publish_to)


@hub_router.post("/articles/{aid}/ai-polish")
def ai_polish(aid: int):
    return hub.ai_polish(aid)


@hub_router.get("/ai/status")
def ai_status():
    return {"ready": hub.ai_ready()}


@hub_router.get("/ai/gate")
def ai_gate():
    """AIGC 合规门禁状态：开关、审查模型、高危词数、最近拒绝。"""
    from service.publishing import gate as g
    snap = {"enabled": g.is_enabled(),
            "review_model": g._cfg("REVIEW_MODEL", "").strip() or "(未配置，走本地 heuristic)",
            "dangerous_terms": len(g.DANGEROUS_PATTERNS),
            "human_review_gate": "AI 源内容禁止直接 publish，须 draft_only + 人工确认"}
    try:
        rows = hub.conn.execute(
            "SELECT * FROM jobs WHERE type='publish' AND status='failed' "
            "ORDER BY id DESC LIMIT 50").fetchall()
        denied = [dict(r) for r in rows if any(
            k in (r["message"] or "") for k in ("门禁", "高危", "人工确认", "合规"))]
        snap["recent_denied"] = denied[:10]
    except Exception:
        snap["recent_denied"] = []
    return snap


@hub_router.get("/jobs")
def jobs(limit: int = 50):
    from service.publishing import db
    return [dict(r) for r in db.list_jobs(hub.conn, limit)]


# ---------------- 可观测性端点 ----------------

@hub_router.get("/metrics")
def metrics():
    """实时指标快照：计数器 + 耗时直方图 + 事件计数。

    重启归零；长期趋势看 jobs 表 + events.log（grep trace_id 串联链路）。
    """
    snap = obs.METRICS.snapshot()
    snap["events_log"] = str(obs.EVENT_LOG)
    snap["trace_hint"] = "发布/更新链路 grep 'trace' + trace_id 于 events.log"
    return snap


def register_hub(app: FastAPI, include_health: bool = True) -> None:
    """把平台发布 REST API 挂载进（新的）FastAPI 应用。

    - 统一装配鉴权 / 访问日志中间件
    - 主后端 ``app/factory.py`` 调用本函数即完成"把 server/api.py 合并进新后端"
    - ``include_health=False`` 时复用主后端自带的 /health（避免重复路由）
    - 前端静态资源不再由 FastAPI 托管，请用独立静态服务器（nginx / web dev server）提供
    """
    _attach_middleware(app)
    app.include_router(hub_router)

    if include_health:
        @app.get("/health")
        def health():
            """存活探测：DB 可读 + 事件日志可写 + AI 是否就绪。供反代/监控探活。"""
            db_ok = False
            try:
                db_ok = hub.conn.execute("SELECT 1").fetchone()[0] == 1
            except Exception:
                pass
            log_ok = Path(obs.EVENT_LOG.parent).exists()
            return {"ok": db_ok and log_ok, "db": db_ok, "events_log": log_ok,
                    "ai_ready": hub.ai_ready(), "ts": time.time()}


# ---------------- 独立运行入口 ----------------
app = FastAPI(title="AI 内容中台", version="0.2.0")
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )
register_hub(app, include_health=True)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8800)
