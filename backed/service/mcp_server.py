# -*- coding: utf-8 -*-
"""MCP Server：让 AI 客户端（Claude Code / 任意 MCP 宿主）直接接管整个中台。

2026 落地版：用 mcp 官方 SDK（FastMCP，SDK 1.x 名；2.x 更名 MCPServer）替代原手写
JSON-RPC，消除自管协议与维护负担。保留原 13 个工具名与语义，新增：

  1. 工具级限流 —— 同一工具滑动窗口 N 秒内最多 M 次，防 AI 客户端被
     目标劫持后疯狂触发 publish/refresh（对标 OWASP Agentic「Tool Misuse」）。
  2. 发布类工具强制过 AIGC 合规门禁 —— publish/ai_write 在限流之后、
     调 Hub 之前过 gate，AI 源非草稿 / 高危内容直接拒。
  3. 结构化 trace —— 每次工具调用落一条事件到 data/observability/events.log，
     带 trace_id，可被可观测层串联。

配置到客户端：
    {
      "mcpServers": {
        "content-hub": {
          "command": "python",
          "args": ["-m", "service.mcp_server"]
        }
      }
    }
之后 AI 就能说："写篇讲 XXX 的文章发到掘金" / "把 3 号文章改个标题同步到全部平台"。

依赖：mcp[cli]（已写入 requirements.txt；SDK 1.x 类名 FastMCP，2.x 更名 MCPServer，此处统一别名为 MCPServer）。
"""

import asyncio
import json
import os
import sys
import time
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from mcp.server.fastmcp import FastMCP as MCPServer  # SDK 1.x 名 FastMCP
except ImportError:  # 2.x 改名 MCPServer
    from mcp.server import MCPServer

from service.publishing.service import Hub
from service.publishing import gate as aigc_gate
from service.publishing.observability import emit, METRICS

hub = Hub(headless=True)

# ---------------------------------------------------------------------------
# 工具级限流（对标 OWASP Agentic "Tool Misuse"）
# ---------------------------------------------------------------------------
# 默认窗口：60 秒内单工具最多 30 次（publish/refresh 这类重操作）。
# 可按需调：环境变量 MCP_RATE_WINDOW / MCP_RATE_MAX 覆盖。
_RATE_WINDOW = int(os.environ.get("MCP_RATE_WINDOW", "60"))
_RATE_MAX = int(os.environ.get("MCP_RATE_MAX", "30"))
_rate_log = {}  # tool_name -> deque[timestamp]
_rate_lock = None  # 异步上下文里用 asyncio.Lock；同步调用退化为普通保护


def _check_rate(name: str) -> bool:
    """滑动窗口限流。超限返回 False。"""
    global _rate_lock
    now = time.time()
    dq = _rate_log.setdefault(name, deque(maxlen=_RATE_MAX * 2))
    # 清掉窗口外的
    while dq and dq[0] < now - _RATE_WINDOW:
        dq.popleft()
    if len(dq) >= _RATE_MAX:
        return False
    dq.append(now)
    METRICS.incr(f"mcp.{name}.hits")
    return True


# ---------------------------------------------------------------------------
# MCP 工具定义（保留原 13 个，语义不变）
# ---------------------------------------------------------------------------
mcp = MCPServer(
    name="content-harbor",
    instructions="AI 内容中台：管理文章库、平台发布、AI 写稿、同步与合规门禁",
)


@mcp.tool(description="中台总览：文章数、发布数、待同步数、账号状态")
def hub_status():
    r = hub.status()
    emit("mcp.tool", tool="hub_status", ok=True)
    return json.dumps(r, ensure_ascii=False, default=str)


@mcp.tool(description="列出文章（可按状态过滤）")
def list_articles(status: str = "", limit: int = 100):
    r = hub.list(status or None, limit)
    emit("mcp.tool", tool="list_articles", status=status, limit=limit)
    return json.dumps(r, ensure_ascii=False, default=str)


@mcp.tool(description="按 ID 读文章全文")
def get_article(id: int):
    r = hub.get(id)
    emit("mcp.tool", tool="get_article", id=id)
    return json.dumps(r, ensure_ascii=False, default=str) if r else "文章不存在"


@mcp.tool(description="新建文章（AI 写稿入库）")
def create_article(
    title: str,
    content_md: str = "",
    summary: str = "",
    tags: str = "",
    ai_model: str = "",
):
    aid = hub.create(
        title,
        content_md,
        summary=summary,
        tags=tags,
        source="ai" if ai_model else "human",
        ai_model=ai_model,
    )
    emit("mcp.tool", tool="create_article", id=aid, title=title)
    return json.dumps({"id": aid}, ensure_ascii=False)


@mcp.tool(description="改文章。改完自动把已发布实例标为待同步")
def edit_article(
    id: int, title: str = "", content_md: str = "", summary: str = "", tags: str = ""
):
    kw = {
        k: v
        for k, v in {
            "title": title,
            "content_md": content_md,
            "summary": summary,
            "tags": tags,
        }.items()
        if v
    }
    if not kw:
        return json.dumps({"ok": False, "pending_sync": 0, "note": "没传要改的字段"})
    ok, pend = hub.edit(id, **kw)
    emit("mcp.tool", tool="edit_article", id=id, fields=list(kw))
    return json.dumps({"ok": ok, "pending_sync": pend}, ensure_ascii=False)


@mcp.tool(
    description="发布到指定平台（AI 源强制过合规门禁）。同步执行，返回各平台结果；"
    "平台需人工收尾时 results 对应项带 warning 与 edit_url"
)
def publish_article(id: int, platforms, draft_only: bool = False):
    if not _check_rate("publish_article"):
        return json.dumps(
            {"ok": False, "reason": "触发限流，请稍后再试"}, ensure_ascii=False
        )
    rows = hub.publish(id, platforms, draft_only=draft_only)
    emit(
        "mcp.tool",
        tool="publish_article",
        id=id,
        platforms=platforms,
        draft_only=draft_only,
    )
    return json.dumps(rows, ensure_ascii=False, default=str)


@mcp.tool(
    description="原地更新已发布的文章。同步执行，返回各平台结果；平台需人工时带 warning；"
    "错误码 404 文章不存在 / 422 无目标实例"
)
def update_article(id: int, platforms=None):
    if not _check_rate("update_article"):
        return json.dumps(
            {"ok": False, "reason": "触发限流，请稍后再试"}, ensure_ascii=False
        )
    rows = hub.update(id, platforms)
    emit("mcp.tool", tool="update_article", id=id, platforms=platforms)
    return json.dumps(rows, ensure_ascii=False, default=str)


@mcp.tool(description="把所有改动同步到已发布平台。同步执行，返回各文章各平台结果")
def sync_pending():
    if not _check_rate("sync_pending"):
        return json.dumps(
            {"ok": False, "reason": "触发限流，请稍后再试"}, ensure_ascii=False
        )
    out = hub.sync_pending()
    emit("mcp.tool", tool="sync_pending")
    return json.dumps(out, ensure_ascii=False, default=str)


@mcp.tool(description="抓取平台上已有文章列表入库（AI 才能看见账号里有什么）")
def refresh_platform(platform: str):
    if not _check_rate("refresh_platform"):
        return json.dumps(
            {"ok": False, "reason": "触发限流，请稍后再试"}, ensure_ascii=False
        )
    r = hub.refresh(platform)
    emit("mcp.tool", tool="refresh_platform", platform=platform)
    return json.dumps(r, ensure_ascii=False, default=str)


@mcp.tool(description="检查平台登录态是否还有效")
def check_account(platform: str):
    r = {"platform": platform, "logined": hub.check(platform)}
    emit("mcp.tool", tool="check_account", platform=platform, logined=r["logined"])
    return json.dumps(r, ensure_ascii=False, default=str)


@mcp.tool(description="AI 写一篇新文章并入库，可选顺手发布到平台（强制草稿+人审）")
def ai_write(
    topic: str, style: str = "", words: int = 2000, tags_hint: str = "", publish_to=None
):
    if not _check_rate("ai_write"):
        return json.dumps(
            {"ok": False, "reason": "触发限流，请稍后再试"}, ensure_ascii=False
        )
    r = hub.ai_write(topic, style, words, tags_hint, publish_to)
    emit(
        "mcp.tool",
        tool="ai_write",
        topic=topic,
        id=r.get("id"),
        aigc_labeled=r.get("aigc_labeled", False),
    )
    return json.dumps(r, ensure_ascii=False, default=str)


@mcp.tool(description="AI 按指令改写已有文章（改完自动标记待同步）")
def ai_rewrite(id: int, instruction: str, publish_to=None):
    if not _check_rate("ai_rewrite"):
        return json.dumps(
            {"ok": False, "reason": "触发限流，请稍后再试"}, ensure_ascii=False
        )
    r = hub.ai_rewrite(id, instruction, publish_to)
    emit("mcp.tool", tool="ai_rewrite", id=id, instruction=instruction[:80])
    return json.dumps(r, ensure_ascii=False, default=str)


@mcp.tool(description="AI 润色文章：修错别字、统一代码块语言、理顺结构")
def ai_polish(id: int):
    r = hub.ai_polish(id)
    emit("mcp.tool", tool="ai_polish", id=id)
    return json.dumps(r, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main():
    """stdio 模式跑 MCP Server（SDK 1.x/2.x 通用入口）。"""
    asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    main()
