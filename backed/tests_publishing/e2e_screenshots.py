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
from patchright.sync_api import sync_playwright

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
            step(
                f"API",
                f"{name}",
                r.status_code == 200,
                f"HTTP {r.status_code} · {dt:.0f}ms",
            )
        except Exception as e:
            step(f"API", f"{name}", False, str(e)[:60])

    n_api = len(requests.get(f"{WEB}/platforms", timeout=5).json())

    # ============ Web UI 全流程（边走边截图） ============
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        pg = br.new_page(viewport={"width": 1440, "height": 900})

        # 1. 打开首页
        t = time.time()
        pg.goto(f"{WEB}/")
        pg.wait_for_selector("header.hdr", timeout=20000)
        dt = time.time() - t
        shoot(pg, "01_首页打开")
        step(
            "UI", "1 打开 Web 管理界面", True, f"加载 {dt:.1f}s · 头部与视图切换已渲染"
        )

        # 2. 平台矩阵渲染（管理视图 → 平台与账号，数量对齐 REST /platforms）
        t = time.time()
        pg.click('.vs-btn:has-text("管理")')
        pg.wait_for_selector('.el-tabs__item:has-text("平台与账号")', timeout=10000)
        pg.click('.el-tabs__item:has-text("平台与账号")')
        pg.wait_for_selector(".acct-card", timeout=10000)
        dt = time.time() - t
        n_cards = pg.locator(".acct-card").count()
        shoot(pg, "02_平台矩阵卡片")
        step(
            "UI",
            "2 平台矩阵渲染",
            n_cards == n_api,
            f"共 {n_cards} 个平台卡片 · REST={n_api} · 响应 {dt:.1f}s",
        )

        # 3. 点掘金「登录」
        t = time.time()
        card = pg.locator('.acct-card:has-text("稀土掘金")')
        card.locator('button:has-text("登录")').click()
        pg.wait_for_function(
            """() => document.body.innerText.includes('等待扫码') ||
               [...document.querySelectorAll('.acct-card .el-tag')]
                   .some(t => t.innerText.includes('在线'))""",
            timeout=15000,
        )
        dt = time.time() - t
        shoot(pg, "03_点击登录_等待扫码")
        step(
            "UI",
            "3 点「登录」→ 进入等待扫码状态",
            True,
            f"响应 {dt:.1f}s · 按钮变「等待扫码…」",
        )

        # 4. mock 自动扫码 → 登录态生效
        t = time.time()
        pg.wait_for_function(
            """() => {
            const c = [...document.querySelectorAll('.acct-card')]
                .find(x => x.innerText.includes('稀土掘金'));
            return !!c && [...c.querySelectorAll('.el-tag')]
                .some(t => t.innerText.includes('在线'));
        }""",
            timeout=120_000,
        )
        dt = time.time() - t
        shoot(pg, "04_登录成功_在线")
        step(
            "UI",
            "4 模拟扫码 → 登录态自动生效",
            True,
            f"从扫码到在线 {dt:.1f}s（含 mock 6s 倒计时）· 无需刷新页面",
        )

        # 5. 切回写作视图，新建文章
        t = time.time()
        pg.click('.vs-btn:has-text("写作")')
        pg.click('button:has-text("新建")')
        pg.wait_for_selector('input[placeholder="文章标题"]', timeout=10000)
        pg.fill('input[placeholder="文章标题"]', "全流程截图测试文章")
        pg.fill(
            '.md-editor [contenteditable="true"]',
            "# 全程截图测试\n\n这篇文章由全程截图测试创建，用来验证程序响应与发布链路："
            "从打开管理界面、点击登录、模拟扫码、新建文档到一键发布，每一步都会留截图作为证据。\n\n"
            "- 步骤一：登录平台并等待扫码完成\n- 步骤二：新建文章并写入正文\n"
            "- 步骤三：勾选平台并发布成功\n\n"
            "发布完成后会刷新页面验证数据是否持久化，确保发布实例与文章状态在服务端真实落库。如果某个平台发布失败，任务记录里会给出失败原因，方便重试或改走人工收尾。",
        )
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

        # 7. 发布（编辑器「发布」→ 弹窗勾平台 → 「发布到 N 个平台」）
        t = time.time()
        pg.click('button:has-text("发布")')
        pg.wait_for_selector(".plat-card", timeout=10000)
        pg.click('.plat-card:has-text("稀土掘金")')
        pg.wait_for_selector(".plat-card.on", timeout=5000)
        shoot(pg, "07_勾选掘金_准备发布")
        pg.click('.el-dialog button:has-text("发布到")')
        pg.wait_for_function(
            """() => [...document.querySelectorAll('.pub-results .res-row')]
            .some(r => r.classList.contains('ok') && r.innerText.includes('juejin'))""",
            timeout=120_000,
        )
        dt = time.time() - t
        shoot(pg, "08_发布成功")
        step(
            "UI",
            "7 发布 → 结果面板 juejin 成功行",
            True,
            f"全流程 {dt:.1f}s（含开浏览器+登录态检查）",
        )

        # 8. 刷新整页 → 发布记录持久化（管理视图 → 发布记录）
        pg.reload()
        pg.wait_for_selector("header.hdr", timeout=20000)
        pg.click('.vs-btn:has-text("管理")')
        pg.wait_for_selector('.el-tabs__item:has-text("发布记录")', timeout=10000)
        pg.click('.el-tabs__item:has-text("发布记录")')
        pg.wait_for_selector(".el-table__row:visible", timeout=15000)
        has_pub = pg.evaluate(
            """() => [...document.querySelectorAll('.el-table__row')].filter(r => r.offsetWidth || r.offsetHeight)
                 .some(r => r.innerText.includes('全流程截图测试文章') &&
                            r.innerText.includes('juejin') &&
                            r.innerText.includes('已发布'))"""
        )
        shoot(pg, "09_刷新后记录仍在")
        step(
            "UI",
            "8 刷新页面 → 发布记录持久化",
            has_pub,
            f"发布记录行含 文章+juejin+已发布（has_pub={has_pub}）",
        )

        br.close()

    # ============ REST 数据一致性 ============
    arts = requests.get(f"{WEB}/articles", timeout=5).json()
    hit = [a for a in arts if a["title"] == "全流程截图测试文章"]
    pubs = (
        requests.get(
            f"{WEB}/publications", params={"article_id": hit[0]["id"]}, timeout=5
        ).json()
        if hit
        else []
    )
    ok = (
        bool(hit)
        and hit[0]["status"] == "published"
        and any(p["post_id"] == "art-2001" and p["status"] == "ok" for p in pubs)
    )
    step(
        "API",
        "REST 数据一致性复核",
        ok,
        f"article.status={hit[0]['status'] if hit else '-'} · publication=art-2001/ok",
    )

    # ============ 汇总 ============
    npass = sum(1 for _, _, ok, _ in results if ok)
    print(f"\n========== 测试汇总 {npass}/{len(results)} 通过 ==========", flush=True)
    for no, name, ok, detail in results:
        print(f"{'✅' if ok else '❌'} {name}  {detail}")
    return 0 if npass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())

