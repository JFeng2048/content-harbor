# -*- coding: utf-8 -*-
"""统一任务引擎（重构第一刀）。

替代三样东西：
  1. LangGraph 工作流层（workflows/ 870 行）—— 一个「遍历平台 + 失败重试 +
     暂停等人」的循环被包装成双状态图，功能上等价于本模块 100 行。
  2. server/api.py 里三个复制粘贴的内存任务字典（LOGIN/PUBLISH/ASSIST_TASKS）。
  3. 双数据库（hub.db + workflow.db）—— 任务状态统一落 hub.db 的 tasks 表。

设计要点：
  - 任务持久化到 SQLite，进程重启不丢（waiting_human 任务可恢复）。
  - 单后台线程串行消费队列：当前浏览器是全局单实例，串行是正确约束，
    不是性能瓶颈；未来若换多实例浏览器，把 worker 换成线程池即可。
  - 失败分诊用本地确定性规则（不依赖 LLM）：验证码/风控 → 转人工；
    网络/临时错误 → 自动重试；其余 → 判失败并留 error。
  - 语义单一：REST 与 MCP 都通过 submit() 提交、get()/list() 查询，
    不再有 legacy 与 workflow 双路径。
"""

import json
import threading
import time
import uuid

from service.publishing import db


class TaskManager:
    """后台任务队列。线程安全：submit/get/list/resume 可跨线程调用。"""

    # 本地分诊关键词（小写匹配）。确定性规则，不引入 LLM 依赖。
    HUMAN_HINTS = (
        "验证码", "captcha", "风控", "异常请求", "登录已失效",
        "需要重新登录", "滑块", "安全验证", "security check",
        "simulate", "click to verify",
    )
    RETRY_HINTS = (
        "超时", "timeout", "timed out", "connection", "网络",
        "refused", "econnreset", "eof", "429", "503", "504",
        "econnaborted", "broken pipe",
    )
    MAX_ATTEMPTS = 3

    def __init__(self, hub, conn):
        self.hub = hub
        self.conn = conn
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._loop, daemon=True,
                                        name="task-manager")
        self._worker.start()

    # ---------------- 对外接口 ----------------

    def submit(self, kind, article_id=None, platforms=None, account="default",
               draft_only=False, **extra):
        """提交一个任务，立即返回 task_id。"""
        task_id = uuid.uuid4().hex[:10]
        db.create_task(self.conn, task_id, kind, article_id=article_id,
                       platforms=platforms, account=account,
                       draft_only=draft_only)
        # 附带的扩展参数（如 assist 的 url）直接写进 result 初始段
        if extra:
            db.update_task(self.conn, task_id, result=json.dumps(extra,
                                                                 ensure_ascii=False))
        self._wake.set()
        return task_id

    def get(self, task_id):
        """按 task_id 查任务状态。"""
        return db.get_task(self.conn, task_id)

    def list(self, limit=50, kind=None, status=None):
        return db.list_tasks(self.conn, limit=limit, kind=kind, status=status)

    def resume(self, task_id, approved=True):
        """恢复 waiting_human 任务：approved=True 重跑；False 标记放弃。"""
        with self._lock:
            task = db.get_task(self.conn, task_id)
            if not task:
                return {"ok": False, "error": "任务不存在"}
            if task["status"] != "waiting_human":
                return {"ok": False, "error": f"任务当前状态为 {task['status']}，不可恢复"}
            if approved:
                db.update_task(self.conn, task_id,
                               status="pending", error="",
                               message="人工已处理，重新执行")
            else:
                db.update_task(self.conn, task_id,
                               status="failed", message="已放弃",
                               finished_at=time.time())
        if approved:
            self._wake.set()
        return {"ok": True, "status": db.get_task(self.conn, task_id)["status"]}

    def close(self):
        self._stop.set()
        self._wake.set()

    # ---------------- 内部实现 ----------------

    def _loop(self):
        while not self._stop.is_set():
            task = self._next_pending()
            if task is None:
                self._wake.wait(2.0)
                self._wake.clear()
                continue
            self._run_task(task)

    def _next_pending(self):
        with self._lock:
            rows = db.list_tasks(self.conn, limit=10, status="pending")
            if not rows:
                return None
            # 优先跑最老的
            rows.sort(key=lambda t: t["created_at"])
            task = rows[0]
            db.update_task(self.conn, task["task_id"],
                           status="running", updated_at=time.time())
            return task

    def _run_task(self, task):
        task_id = task["task_id"]
        kind = task["kind"]
        attempts = task.get("attempts", 0) + 1
        db.update_task(self.conn, task_id, attempts=attempts,
                       message="执行中…")
        try:
            result = self._dispatch(kind, task)
            db.update_task(self.conn, task_id, status="ok",
                           result=json.dumps(result, ensure_ascii=False),
                           message="完成", finished_at=time.time())
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            action, reason = self._triage(kind, err, attempts)
            if action == "retry":
                db.update_task(self.conn, task_id, status="pending",
                               error=err, message=f"自动重试（第 {attempts} 次）")
                self._wake.set()   # 立即再消费
            elif action == "human":
                db.update_task(self.conn, task_id, status="waiting_human",
                               error=err, message=reason,
                               finished_at=time.time())
            else:
                db.update_task(self.conn, task_id, status="failed",
                               error=err, message=reason,
                               finished_at=time.time())
        finally:
            db.prune_tasks(self.conn)

    def _dispatch(self, kind, task):
        """按任务类型分发到业务层。返回可 JSON 化的结果。"""
        article_id = task.get("article_id")
        platforms = json.loads(task.get("platforms") or "[]")
        account = task.get("account") or "default"
        draft_only = bool(task.get("draft_only"))

        if kind == "publish":
            extra = json.loads(task.get("result") or "{}")
            return self.hub.publish(article_id, platforms, account, draft_only,
                                    settings=extra.get("settings"))
        if kind == "update":
            return self.hub.update(article_id, platforms, account)
        if kind == "sync":
            return self.hub.sync_pending(account)
        if kind == "refresh":
            return self.hub.refresh(platforms[0] if platforms else None,
                                    account, limit=50)
        if kind == "login":
            return self.hub.login(platforms[0] if platforms else None, account)
        if kind == "assist":
            extra = json.loads(task.get("result") or "{}")
            return self.hub.assist_open(platforms[0] if platforms else None,
                                        extra.get("url", ""), account=account)
        raise ValueError(f"未知任务类型: {kind}")

    def _triage(self, kind, err, attempts):
        """确定性失败分诊。返回 (action, reason)。"""
        low = (err or "").lower()
        for h in self.HUMAN_HINTS:
            if h.lower() in low:
                return "human", "命中风控/验证码/登录失效，需要人工处理"
        for h in self.RETRY_HINTS:
            if h.lower() in low:
                if attempts < self.MAX_ATTEMPTS:
                    return "retry", "网络/临时错误，自动重试"
                return "fail", f"重试 {self.MAX_ATTEMPTS} 次仍失败"
        return "fail", "未分类错误"
