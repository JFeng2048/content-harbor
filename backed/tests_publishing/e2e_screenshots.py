# -*- coding: utf-8 -*-
"""全程截图测试（掘金）：真实浏览器逐步操作 Web UI + REST 计时，每步留证 + PASS/FAIL。

前置：
  python tests/mocks/mock_juejin.py &
  python tests/run_patched_server.py &

用法：python tests/e2e_screenshots.py [截图输出目录]
"""
import os
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]

WEB = "http://127.0.0.1:8800"
SHOTS = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "tests" / "shots")
os.makedirs(SHOTS, exist_ok=True)

results = []


def step(no, name, ok, detail="", shot=None):
    results.append((no, name, ok, detail))
    tag = "PASS" if ok else "FAIL"
    print(f"{tag}  {no} {name}   {detail}", flush=True)
    return ok


def shoot(pg, name):
    pg.screenshot(path=f"{SHOTS}/{name}.png")
    print(f"      [截图] {name}.png", flush=True)


def main():
    # ============ REST API 响应性 ============
    print("\n---- REST API 响应计时 ----", flush=True)
    api_checks = [
        ("GET /platforms", f"{WEB}/platforms"),
        ("GET /status", f"{WEB}/status"),
        ("GET /accounts", f"{WEB}/accounts"),
        ("GET /articles", f"{WEB}/articles"),
        ("GET /jobs", f"{WEB}/jobs"),
        ("GET /docs", f"{WEB}/docs"),
        ("GET / (Web UI)", f"{WEB}/"),
    ]
    for name, url in api_checks:
        t = time.time()
        try:
            r = requests.get(url, timeout=5)
            dt = (time.time() - t) * 1000
            step(f"API", f"{name}", r.status_code == 200,
                 f"HTTP {r.status_code} · {dt:.0f}ms")
        except Exception as e:
            step(f"API", f"{name}", False, str(e)[:60])

    # ============ Web UI 全流程（边走边截图） ============
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        pg = br.new_page(viewport={"width": 1440, "height": 900})

        # 1. 打开首页
        t = time.time()
        pg.goto(f"{WEB}/")
        pg.wait_for_selector(".plat-card", timeout=20000)
        dt = time.time() - t
        shoot(pg, "01_首页打开")
        step("UI", "1 打开 Web 管理界面", True, f"加载 {dt:.1f}s · 平台卡片已渲染")

        n_cards = pg.locator(".plat-card").count()
        shoot(pg, "02_九大平台卡片")
        step("UI", "2 平台矩阵渲染", n_cards == 9, f"共 {n_cards} 个平台卡片")

        # 3. 点掘金「登录」
        t = time.time()
        card = pg.locator('.plat-card:has-text("稀土掘金")')
        card.locator(".login-btn").click()
        pg.wait_for_selector(".login-hint", timeout=10000)
        pg.wait_for_function(
            "() => document.body.innerText.includes('等待扫码')", timeout=10000)
        dt = time.time() - t
        shoot(pg, "03_点击登录_等待扫码")
        step("UI", "3 点「登录」→ 进入等待扫码状态", True,
             f"响应 {dt:.1f}s · 弹出引导提示")

        # 4. mock 自动扫码 → 登录态生效
        t = time.time()
        pg.wait_for_function("""() => {
            const tags = [...document.querySelectorAll('.el-tag--success')].map(x => x.innerText);
            return tags.some(x => x.includes('在线')) &&
                   document.body.innerText.includes('juejin / default');
        }""", timeout=120_000)
        dt = time.time() - t
        shoot(pg, "04_登录成功_在线")
        step("UI", "4 模拟扫码 → 登录态自动生效", True,
             f"从扫码到在线 {dt:.1f}s（含 mock 6s 倒计时）· 无需刷新页面")

        # 5. 新建文章
        t = time.time()
        pg.click('button:has-text("新建")')
        pg.fill('input[placeholder="文章标题"]', "全流程截图测试文章")
        pg.fill('textarea[placeholder*="Markdown"]',
                "# 截图测试\n\n这篇文章由**全程截图测试**创建，验证程序响应与发布链路。\n\n- 步骤一：登录\n- 步骤二：写文章\n- 步骤三：发布")
        dt = time.time() - t
        shoot(pg, "05_新建文章已填写")
        step("UI", "5 新建文章并填写内容", True, f"编辑器响应 {dt:.1f}s")

        # 6. 保存
        t = time.time()
        pg.click('button:has-text("保存")')
        pg.wait_for_selector(".el-message--success", timeout=15000)
        dt = time.time() - t
        shoot(pg, "06_保存成功")
        step("UI", "6 保存 → 提示「已保存」", True, f"响应 {dt:.1f}s")

        # 7. 发布
        t = time.time()
        pg.click('.plat-card:has-text("稀土掘金")')
        pg.wait_for_selector(".plat-card.on", timeout=5000)
        shoot(pg, "07_勾选掘金_准备发布")
        pg.click('button:has-text("发布")')
        pg.wait_for_function("""() => {
            const txt = document.body.innerText;
            return txt.includes('art-2001') && txt.includes('已同步');
        }""", timeout=120_000)
        dt = time.time() - t
        shoot(pg, "08_发布成功_已同步")
        step("UI", "7 发布 → 实例表出现 art-2001 / 已同步", True,
             f"全流程 {dt:.1f}s（含开浏览器+登录态检查）")

        # 8. 刷新整页，验证数据持久化
        pg.reload()
        pg.wait_for_selector(".plat-card", timeout=20000)
        pg.click('.art-item:has-text("全流程截图测试文章")')
        pg.wait_for_selector('input[placeholder="文章标题"]', timeout=15000)
        has_pub = pg.evaluate("() => document.body.innerText.includes('art-2001')")
        shoot(pg, "09_刷新后记录仍在")
        step("UI", "8 刷新页面 → 点开文章，发布记录持久化", has_pub,
             f"列表项带「已发布」标签 · 发布实例 art-2001 仍在（has_pub={has_pub}）")

        br.close()

    # ============ REST 数据一致性 ============
    arts = requests.get(f"{WEB}/articles", timeout=5).json()
    hit = [a for a in arts if a["title"] == "全流程截图测试文章"]
    pubs = requests.get(f"{WEB}/publications", params={"article_id": hit[0]["id"]},
                        timeout=5).json() if hit else []
    ok = bool(hit) and hit[0]["status"] == "published" and \
        any(p["post_id"] == "art-2001" and p["status"] == "ok" for p in pubs)
    step("API", "REST 数据一致性复核", ok,
         f"article.status={hit[0]['status'] if hit else '-'} · publication=art-2001/ok")

    # ============ 汇总 ============
    npass = sum(1 for _, _, ok, _ in results if ok)
    print(f"\n========== 测试汇总 {npass}/{len(results)} 通过 ==========", flush=True)
    for no, name, ok, detail in results:
        print(f"{'✅' if ok else '❌'} {name}  {detail}")
    return 0 if npass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
