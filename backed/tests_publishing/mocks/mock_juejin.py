# -*- coding: utf-8 -*-
"""模拟掘金平台（E2E 验证用）：登录页 + 模拟扫码 + 创作者中心 + 内容 API。

接口与掘金真实接口同构，跑在 127.0.0.1:9102。
「扫码」= 页面加载 6 秒后自动种 cookie 跳转（等价真人扫码），
页面上也保留按钮供人工点击演示。
"""
from flask import Flask, jsonify, make_response, redirect, request

app = Flask(__name__)

LOGIN_PAGE = """<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>登录 - 掘金（模拟环境）</title>
<style>
  body{font-family:system-ui;background:#f4f5f7;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
  .card{background:#fff;border-radius:12px;padding:36px 44px;box-shadow:0 8px 30px rgba(0,0,0,.08);text-align:center}
  h1{font-size:20px;margin:0 0 6px}
  .sub{color:#86909c;font-size:13px;margin-bottom:22px}
  .qr{width:180px;height:180px;margin:0 auto 18px;border:2px dashed #c9cdd4;border-radius:10px;
      display:flex;align-items:center;justify-content:center;color:#86909c;font-size:13px;
      background:repeating-linear-gradient(45deg,#f7f8fa 0 8px,#fff 8px 16px)}
  button{background:#1e80ff;color:#fff;border:0;border-radius:8px;padding:10px 26px;font-size:14px;cursor:pointer}
  button:hover{background:#0c6ce0}
  .tip{margin-top:14px;color:#86909c;font-size:12px}
</style></head>
<body>
  <div class="card">
    <h1>登录掘金</h1>
    <div class="sub">模拟环境 · 用于验证客户端登录链路</div>
    <div class="qr">二维码占位</div>
    <button id="scan" onclick="location.href='/mock/scan'">模拟扫码成功</button>
    <div class="tip"><span id="cd">6</span> 秒后自动模拟扫码完成（等价真人扫码）</div>
  </div>
  <script>
    let n = 6;
    const t = setInterval(() => {
      n--; document.getElementById('cd').innerText = n;
      if (n <= 0) { clearInterval(t); location.href = '/mock/scan'; }
    }, 1000);
  </script>
</body></html>"""


@app.get("/login")
def login():
    return LOGIN_PAGE


@app.get("/mock/scan")
def scan():
    # 等价于"用户扫完码、平台确认身份"：种下会话 cookie 并跳回创作者中心
    resp = make_response(redirect("/creator/home"))
    resp.set_cookie("mock_session", "mock-uid-1", max_age=86400)
    return resp


@app.get("/creator/home")
def home():
    return """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>创作者中心 - 掘金（模拟）</title></head>
<body style="font-family:system-ui;padding:40px">
  <h1>创作者中心（模拟环境）</h1>
  <p id="who">当前用户：模拟用户 (mock-uid-1)</p>
  <p>登录成功，浏览器窗口可以关闭了。</p>
</body></html>"""


# ---------- 内容 API（与掘金真实接口同构） ----------

@app.get("/api/user_api/v1/user/get")
def user_get():
    if request.cookies.get("mock_session"):
        return jsonify({"err_no": 0, "data": {"user_id": "mock-uid-1", "user_name": "模拟用户"}})
    return jsonify({"err_no": 100, "err_msg": "未登录"})


@app.post("/api/content_api/v1/article_draft/create")
def draft_create():
    if not request.cookies.get("mock_session"):
        return jsonify({"err_no": 100, "err_msg": "未登录"})
    print("[mock] 创建草稿 OK -> draft-1001", flush=True)
    return jsonify({"err_no": 0, "data": {"id": "draft-1001"}})


@app.post("/api/content_api/v1/article/publish")
def publish():
    if not request.cookies.get("mock_session"):
        return jsonify({"err_no": 100, "err_msg": "未登录"})
    print("[mock] 发布文章 OK -> art-2001", flush=True)
    return jsonify({"err_no": 0, "data": {"article_id": "art-2001"}})


@app.get("/api/content_api/v1/article/query_list")
def query_list():
    if not request.cookies.get("mock_session"):
        return jsonify({"err_no": 100, "err_msg": "未登录"})
    return jsonify({"err_no": 0, "data": [
        {"article_id": "art-2001", "title": "模拟登录链路验证文章",
         "article_info": {"status": 2, "view_count": 3, "digg_count": 1, "comment_count": 0}}
    ]})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=9102, threaded=True)
