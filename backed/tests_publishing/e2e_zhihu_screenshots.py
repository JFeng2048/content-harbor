# -*- coding: utf-8 -*-
"""全程截图测试（知乎）：Web UI 点登录 → 模拟扫码 → 在线 → 建文章 → 发布 → zz001234 落库。

知乎适配器走 UI 发布链路（Draft.js 编辑器注入 + 点发布 → URL 跳 /p/{id}），
mock 编辑器元素与知乎真实结构对齐，验证的是适配器真实选择器逻辑。

前置：
  python tests/mocks/mock_zhihu.py &
  python tests/run_patched_server_zhihu.py &

用法：python tests/e2e_zhihu_screenshots.py [截图输出目录]
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


def step(no, name, ok, detail=""):
    results.append((no, name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {no} {name}   {detail}", flush=True)


def shoot(pg, name):
    pg.screenshot(path=f"{SHOTS}/{name}.png")
    print(f"      [截图] {name}.png", flush=True)


def main():
    # ============ REST API 健康检查 ============
    print("\n---- REST API 健康检查 ----", flush=True)
    r = requests.get(f"{WEB}/platforms", timeout=5)
    ids = [p["id"] for p in r.json()]
    step("API", "服务在线且注册了知乎适配器", r.ok and "zhihu" in ids, f"platforms={ids}")

    # ============ Web UI 全流程 ============
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        pg = br.new_page(viewport={"width": 1440, "height": 900})

        # 1. 打开首页
        t = time.time()
        pg.goto(f"{WEB}/")
        pg.wait_for_selector(".plat-card", timeout=20000)
        dt = time.time() - t
        shoot(pg, "01_首页打开")
        step("UI", "1 打开 Web 管理界面", True, f"加载 {dt:.1f}s")

        # 2. 点知乎「登录」
        t = time.time()
        card = pg.locator('.plat-card:has-text("知乎")')
        card.locator(".login-btn").click()
        pg.wait_for_selector(".login-hint", timeout=10000)
        pg.wait_for_function(
            "() => document.body.innerText.includes('等待扫码')", timeout=10000)
        dt = time.time() - t
        shoot(pg, "02_点击知乎登录_等待扫码")
        step("UI", "2 点知乎「登录」→ 等待扫码", True, f"响应 {dt:.1f}s")

        # 3. mock 自动扫码（6s）→ 登录态生效
        t = time.time()
        pg.wait_for_function("""() => {
            const tags = [...document.querySelectorAll('.el-tag--success')].map(x => x.innerText);
            return tags.some(x => x.includes('在线')) &&
                   document.body.innerText.includes('zhihu / default');
        }""", timeout=120_000)
        dt = time.time() - t
        shoot(pg, "03_知乎登录成功_在线")
        step("UI", "3 模拟扫码 → 知乎登录态生效", True,
             f"从扫码到在线 {dt:.1f}s（含 mock 6s 倒计时）· 无需刷新页面")

        # 4. 新建文章
        t = time.time()
        pg.click('button:has-text("新建")')
        pg.fill('input[placeholder="文章标题"]', "知乎截图流程测试文章")
        pg.fill('textarea[placeholder*="Markdown"]',
                "# 你好知乎\n\n这篇由 **ai-content-hub** 全程截图测试发布，"
                "验证知乎适配器的 Draft.js 编辑器注入链路。\n\n- 登录\n- 编辑器注入\n- 发布跳转")
        dt = time.time() - t
        shoot(pg, "04_新建知乎文章已填写")
        step("UI", "4 新建文章并填写 Markdown", True, f"编辑器响应 {dt:.1f}s")

        # 5. 保存
        t = time.time()
        pg.click('button:has-text("保存")')
        pg.wait_for_selector(".el-message--success", timeout=15000)
        dt = time.time() - t
        shoot(pg, "05_保存成功")
        step("UI", "5 保存 → 提示「已保存」", True, f"响应 {dt:.1f}s")

        # 6. 勾选知乎并发布（适配器：填标题 → HTML 粘进 Draft.js → 点发布 → 等 /p/ 跳转）
        t = time.time()
        pg.click('.plat-card:has-text("知乎")')
        pg.wait_for_selector(".plat-card.on", timeout=5000)
        shoot(pg, "06_勾选知乎_准备发布")
        pg.click('button:has-text("发布")')
        pg.wait_for_function("""() => {
            const txt = document.body.innerText;
            return txt.includes('zz001234') && txt.includes('已同步');
        }""", timeout=120_000)
        dt = time.time() - t
        shoot(pg, "07_发布成功_已同步")
        step("UI", "6 发布 → post_id=zz001234 / 已同步", True,
             f"全流程 {dt:.1f}s（标题填充+HTML注入+点发布+等跳转）")

        # 7. 刷新整页，验证持久化
        pg.reload()
        pg.wait_for_selector(".plat-card", timeout=20000)
        pg.click('.art-item:has-text("知乎截图流程测试文章")')
        pg.wait_for_selector('input[placeholder="文章标题"]', timeout=15000)
        has_pub = pg.evaluate("() => document.body.innerText.includes('zz001234')")
        shoot(pg, "08_刷新后记录仍在")
        step("UI", "7 刷新页面 → 发布记录持久化", has_pub,
             f"发布实例 zz001234 仍在（has_pub={has_pub}）")

        br.close()

    # ============ REST 数据一致性 ============
    arts = requests.get(f"{WEB}/articles", timeout=5).json()
    hit = [a for a in arts if a["title"] == "知乎截图流程测试文章"]
    pubs = requests.get(f"{WEB}/publications", params={"article_id": hit[0]["id"]},
                        timeout=5).json() if hit else []
    ok = bool(hit) and hit[0]["status"] == "published" and \
        any(p["post_id"] == "zz001234" and p["status"] == "ok" for p in pubs)
    step("API", "REST 数据一致性复核", ok,
         f"article.status={hit[0]['status'] if hit else '-'} · publication=zz001234/ok")

    # ============ 汇总 ============
    npass = sum(1 for _, _, ok, _ in results if ok)
    print(f"\n========== 知乎截图测试汇总 {npass}/{len(results)} 通过 ==========", flush=True)
    for no, name, ok, detail in results:
        print(f"{'✅' if ok else '❌'} {name}  {detail}")
    return 0 if npass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
