# -*- coding: utf-8 -*-
"""端到端模拟验证（掘金）：点「登录」→ 跳平台扫码 → 登录态自动生效 → 建文档 → 发布成功。

前置：
  python tests/mocks/mock_juejin.py &        # 模拟掘金 :9102
  python tests/run_patched_server.py &       # Web 服务 :8800（掘金适配器指向 mock）

用法：python tests/e2e_login_flow.py
"""
import json
import sys
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

WEB = "http://127.0.0.1:8800"
MOCK = "http://127.0.0.1:9102"
SHOTS = ROOT / "tests" / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)

results = []


def step(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}   {detail}", flush=True)


def wait_ui(pg, js, timeout=120_000):
    pg.wait_for_function(js, timeout=timeout)


def main():
    # ---------- 阶段 0：前置健康检查 ----------
    r = requests.get(f"{MOCK}/api/user_api/v1/user/get", timeout=5).json()
    step("0.1 模拟平台在线且处于未登录态", not (r.get("data") or {}).get("user_id"))

    r = requests.get(f"{WEB}/platforms", timeout=5)
    ids = [p["id"] for p in r.json()] if r.ok else []
    step("0.2 Web 服务在线且注册了掘金适配器", "juejin" in ids, f"platforms={ids}")

    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        pg = br.new_page(viewport={"width": 1440, "height": 900})

        # ---------- 阶段 1：Web UI 点「登录」 ----------
        pg.goto(f"{WEB}/static/index.html")
        pg.wait_for_selector(".plat-card", timeout=20_000)
        step("1.1 Web UI 加载，平台卡片渲染完成", True)

        card = pg.locator('.plat-card:has-text("稀土掘金")')
        card.locator(".login-btn").click()
        try:
            pg.wait_for_selector(".login-hint", timeout=10_000)
            wait_ui(pg, "() => document.body.innerText.includes('等待扫码')", 10_000)
            step("1.2 点「登录」→ 按钮变「等待扫码…」+ 弹出引导提示", True,
                 pg.locator(".login-hint").inner_text()[:48])
        except Exception as e:
            step("1.2 点「登录」→ 按钮变「等待扫码…」", False, str(e)[:80])
        pg.screenshot(path=str(SHOTS / "1_click_login.png"))

        # ---------- 阶段 2：扫码 → 登录态自动生效（不刷新页面） ----------
        try:
            wait_ui(pg, """() => {
                const tags = [...document.querySelectorAll('.el-tag--success')].map(x => x.innerText);
                return tags.some(x => x.includes('在线')) &&
                       document.body.innerText.includes('juejin / default');
            }""", 120_000)
            step("2.1 模拟扫码完成 → UI 自动变「在线」（登录态已保存）", True)
        except Exception as e:
            step("2.1 模拟扫码完成 → UI 自动变「在线」", False, str(e)[:80])
        pg.screenshot(path=str(SHOTS / "2_login_success.png"))

    # ---------- 阶段 3：REST 层确认登录态落库 ----------
    accs = requests.get(f"{WEB}/accounts", timeout=5).json()
    jue = [a for a in accs if a.get("platform") == "juejin"]
    ok = bool(jue) and jue[0].get("status") == "logined"
    step("3.1 GET /accounts → juejin/default = logined", ok,
         json.dumps(jue, ensure_ascii=False)[:90])

    # ---------- 阶段 4：Web UI 建文档（管理文档） ----------
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        pg = br.new_page(viewport={"width": 1440, "height": 900})
        pg.goto(f"{WEB}/static/index.html")
        pg.wait_for_selector(".plat-card", timeout=20_000)

        pg.click('button:has-text("新建")')
        pg.fill('input[placeholder="文章标题"]', "模拟登录链路验证文章")
        pg.fill('textarea[placeholder*="Markdown"]',
                "# 你好，掘金（模拟）\n\n这篇文章由 ai-content-hub 端到端模拟流程发布，"
                "用于验证「登录 → 拿到登录态 → 管理文档 → 发布」全链路。\n\n- 步骤一：点击登录\n- 步骤二：扫码\n- 步骤三：发布")
        pg.click('button:has-text("保存")')
        try:
            pg.wait_for_selector(".el-message--success", timeout=15_000)
            step("4.1 新建文章并保存成功（UI 提示「已保存」）", True)
        except Exception as e:
            step("4.1 新建文章并保存成功", False, str(e)[:80])

        arts = requests.get(f"{WEB}/articles", timeout=5).json()
        hit = [a for a in arts if a.get("title") == "模拟登录链路验证文章"]
        step("4.2 REST /articles 能查到刚建的文章", bool(hit), f"id={hit[0]['id'] if hit else '-'}")

        # ---------- 阶段 5：发布到掘金（模拟） ----------
        pg.click('.plat-card:has-text("稀土掘金")')          # 勾选平台
        pg.wait_for_selector(".plat-card.on", timeout=5_000)
        pg.click('button:has-text("发布")')
        try:
            wait_ui(pg, """() => {
                const txt = document.body.innerText;
                return txt.includes('art-2001') && txt.includes('已同步');
            }""", 120_000)
            step("5.1 发布成功：发布实例表出现 art-2001 / 已同步", True)
        except Exception as e:
            step("5.1 发布成功：发布实例表出现 art-2001 / 已同步", False, str(e)[:80])
        pg.screenshot(path=str(SHOTS / "3_publish_success.png"))
        br.close()

    # ---------- 阶段 6：数据层确认发布记录 ----------
    art_id = hit[0]["id"] if hit else None
    if art_id:
        pubs = requests.get(f"{WEB}/publications", params={"article_id": art_id},
                            timeout=5).json()
        p0 = next((p for p in pubs if p.get("platform") == "juejin"), {})
        ok = p0.get("post_id") == "art-2001" and p0.get("status") == "ok"
        art = requests.get(f"{WEB}/articles/{art_id}", timeout=5).json()
        ok = ok and art.get("status") == "published"
        step("6.1 发布记录 post_id=art-2001 且文章状态=published", ok,
             json.dumps({k: p0.get(k) for k in ("platform", "status", "post_id", "post_url")},
                        ensure_ascii=False) + f" article.status={art.get('status')}")
    else:
        step("6.1 GET /articles/{id} → 发布记录", False, "文章不存在")

    # ---------- 汇总 ----------
    print("\n========== E2E 结果汇总 ==========", flush=True)
    npass = sum(1 for _, ok, _ in results if ok)
    for name, ok, detail in results:
        print(f"{'✅' if ok else '❌'} {name}  {detail}")
    print(f"合计 {npass}/{len(results)} 通过", flush=True)
    return 0 if npass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
