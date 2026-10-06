# -*- coding: utf-8 -*-
"""掘金登录探针：定位 check_auth 假阳性 + 验证会话落盘。

时间线取证发现：登录任务 11:05:19 报 success，但登录窗口期间
profile 的 Cookies 文件零写入——check_auth 在无会话时也返回了 True。

本探针：
  1. 有头打开登录页，不扫码先采样 4 轮原始 user/get 响应（验证假阳性）
  2. 提示扫码，继续轮询，直到出现 sessionid cookie（判据收紧）
  3. 关闭后复查 profile：Cookies mtime + headless 复验 check_auth

用法: .venv/Scripts/python.exe scripts/login_probe_juejin.py
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from service.publishing.browser import BuiltinBrowser

ROOT = Path(__file__).resolve().parent.parent
COOKIES_DB = ROOT / 'data' / 'profiles' / 'juejin_default' / 'Default' / 'Network' / 'Cookies'

RAW_JS = """async () => {
  try {
    const r = await fetch('https://api.juejin.cn/user_api/v1/user/get?aid=2608',
                          {credentials: 'include'});
    const t = await r.text();
    return {status: r.status, text: t.slice(0, 200)};
  } catch (e) { return {status: -1, text: String(e)}; }
}"""


def cookie_names(ctx):
    try:
        return [c['name'] for c in ctx.cookies('https://juejin.cn')]
    except Exception:
        return []


def sample(page, ctx, tag):
    raw = page.evaluate(RAW_JS)
    names = cookie_names(ctx)
    has_sess = 'sessionid' in names
    try:
        data = json.loads(raw['text'])
        uid = ((data.get('data') or {}).get('user_id')) or ''
    except Exception:
        uid = '(解析失败)'
    print(f'[{tag}] HTTP {raw["status"]} user_id={uid!r} '
          f'sessionid={"有" if has_sess else "无"} cookies={names}')
    return has_sess, uid, raw


def main():
    print(f'Cookies mtime 起点: '
          f'{time.strftime("%H:%M:%S", time.localtime(COOKIES_DB.stat().st_mtime))}'
          if COOKIES_DB.exists() else 'Cookies 文件不存在')

    br = BuiltinBrowser('juejin', 'default', headless=False)
    ctx = br.start()
    page = ctx.new_page()
    page.goto('https://juejin.cn/login', timeout=60000, wait_until='domcontentloaded')
    time.sleep(4)

    print('\n=== 阶段1：未扫码采样（这里若 True = 假阳性实锤）===')
    false_positive = False
    for i in range(4):
        has_sess, uid, _ = sample(page, ctx, f'未扫码#{i + 1}')
        if uid and not has_sess:
            false_positive = True
        if has_sess:
            break
        time.sleep(3)

    print('\n>>> 请在弹出的浏览器里扫码登录掘金（最多等 120 秒）<<<')
    deadline = time.time() + 120
    got_session = False
    while time.time() < deadline:
        has_sess, uid, raw = sample(page, ctx, '轮询')
        if has_sess and uid:
            got_session = True
            break
        time.sleep(3)

    br.close()
    time.sleep(1)

    mtime = (time.strftime('%H:%M:%S', time.localtime(COOKIES_DB.stat().st_mtime))
             if COOKIES_DB.exists() else 'N/A')
    print(f'\n关闭后 Cookies mtime: {mtime} '
          f'（起点之后有更新 = 新会话已落盘）')
    print(f'假阳性(无sessionid却返回user_id): {"实锤 ✗" if false_positive else "未复现"}')
    print(f'扫码拿到 sessionid: {"是 ✓" if got_session else "否 ✗"}')

    # headless 复验
    br2 = BuiltinBrowser('juejin', 'default', headless=True)
    page2 = br2.start().new_page()
    try:
        page2.goto('https://juejin.cn/creator/home', timeout=60000,
                   wait_until='domcontentloaded')
        time.sleep(3)
        from service.publishing.adapters.juejin import JuejinAdapter
        print(f'headless 复验 check_auth: {JuejinAdapter().check_auth(page2)}')
    finally:
        br2.close()


if __name__ == '__main__':
    main()
