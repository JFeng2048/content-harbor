# -*- coding: utf-8 -*-
"""本地 mock OpenAI 兼容服务（127.0.0.1:9101）：只为离线验证 AI 写稿链路，不对外。

用法：python tests/mocks/mock_openai.py &
然后把 config.json 的 openai_base_url 指到 http://127.0.0.1:9101/v1 即可。
"""
from flask import Flask, request, jsonify

app = Flask(__name__)


@app.post("/v1/chat/completions")
def completions():
    body = request.get_json(force=True) or {}
    user = ""
    for m in body.get("messages", []):
        if m.get("role") == "user":
            user = m.get("content", "")
    # 按任务类型分派（注意顺序：先判摘要/标签，文章 prompt 里含字面「标题：」不能当判据）
    if "摘要" in user:
        content = "本文讲反爬策略：反检测、登录态持久化、人工兜底三层。"
    elif "推荐" in user and "标签" in user:
        content = "自动化,反爬虫,Playwright,风控"
    elif "改写" in user:
        content = "## 改写后\n\n这是按指令改写后的内容，结构更口语。"
    else:
        content = ("标题：Mock 标题-反爬策略实践\n\n"
                   "## 问题\n\n自动化发布常被风控拦截。\n\n"
                   "## 方案\n\n```python\npage.add_init_script(stealth_js)\n```\n\n"
                   "## 踩坑\n\n无头 UA 与指纹不一致会被识别。\n\n## 结论\n\n反检测+登录态持久化。")
    return jsonify({
        "id": "mock-1", "object": "chat.completion", "model": body.get("model", "mock"),
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=9101, threaded=True)
