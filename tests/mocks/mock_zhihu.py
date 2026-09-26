# -*- coding: utf-8 -*-
"""模拟知乎（E2E 验证知乎适配器 UI 逻辑）：/signin 登录 → /write 编辑器 → 发布跳 /p/{id}。

编辑器元素与知乎真实结构对齐：
- 标题 textarea placeholder 含「请输入标题」（ZhihuAdapter.TITLE_SEL）
- 正文 div[data-contents="true"]（Draft.js 根节点，ZhihuAdapter.EDITOR_SEL）
"""

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

app = FastAPI()

PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>登录 - 知乎（模拟）</title>
<style>body{font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh;background:#f4f5f7}
.card{background:#fff;border-radius:12px;padding:40px 50px;text-align:center;box-shadow:0 8px 30px rgba(0,0,0,.08)}
button{background:#0066ff;color:#fff;border:0;border-radius:8px;padding:10px 26px;cursor:pointer}</style></head>
<body><div class="card"><h1>登录知乎（模拟环境）</h1>
<p>二维码占位</p><button onclick="location='/mock/scan'">模拟扫码成功</button>
<p><span id="cd">6</span> 秒后自动模拟扫码</p></div>
<script>let n=6;const t=setInterval(()=>{n--;document.getElementById('cd').innerText=n;
if(n<=0){clearInterval(t);location='/mock/scan';}},1000);</script></body></html>"""

WRITE_PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>写文章 - 知乎（模拟）</title>
<style>body{font-family:system-ui;padding:30px;max-width:800px;margin:0 auto}
textarea{width:100%;font-size:22px;padding:10px;border:0;border-bottom:1px solid #ddd;outline:none}
[data-contents]{min-height:300px;border:1px solid #eee;padding:16px;border-radius:8px;outline:none}
button{background:#0066ff;color:#fff;border:0;border-radius:6px;padding:8px 24px;float:right;cursor:pointer}</style></head>
<body>
  <textarea class="Input" placeholder="请输入标题（最多 100 个字）"></textarea>
  <div data-contents="true" contenteditable="true"><p data-first-line>正文编辑器（模拟 Draft.js）</p></div>
  <button onclick="location='/mock/publish'">发布</button>
</body></html>"""


@app.get("/signin", response_class=HTMLResponse)
async def signin():
    return PAGE


@app.get("/mock/scan")
async def scan():
    resp = RedirectResponse("/write", status_code=302)
    resp.set_cookie("zhihu_session", "mock-zh-1", max_age=86400)
    return resp


@app.get("/write", response_class=HTMLResponse)
async def write(request: Request):
    if not request.cookies.get("zhihu_session"):
        return RedirectResponse("/signin", status_code=302)
    return WRITE_PAGE


@app.get("/mock/publish")
async def publish(request: Request):
    if not request.cookies.get("zhihu_session"):
        return JSONResponse({"error": "未登录"})
    print("[mock-zhihu] 发布 OK -> zz001234", flush=True)
    return RedirectResponse("/p/zz001234", status_code=302)


@app.get("/p/zz001234", response_class=HTMLResponse)
async def article():
    return """<!doctype html><html><head><meta charset="utf-8">
<title>模拟文章 - 知乎</title></head><body style="font-family:system-ui;padding:40px">
<h1>模拟文章已发布 (zz001234)</h1></body></html>"""


@app.get("/api/v4/me")
async def me(request: Request):
    if request.cookies.get("zhihu_session"):
        return JSONResponse(
            {"id": "mock-zh-1", "url_token": "mock-zh-user", "name": "模拟用户"}
        )
    return JSONResponse({"error": "请登录"}, status_code=401)


@app.get("/api/ping")
async def ping(request: Request):
    return JSONResponse(
        {"ok": True, "cookies": request.cookies.get("zhihu_session", "") != ""}
    )


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=9103, log_level="warning")
