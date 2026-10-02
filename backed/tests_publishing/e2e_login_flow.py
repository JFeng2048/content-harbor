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
from patchright.sync_api import sync_playwright

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


def goto_accounts(pg):
    """进管理视图 → 平台与账号页签（登录按钮在这里）。"""
    pg.wait_for_selector("header.hdr", timeout=20_000)
    pg.click('.vs-btn:has-text("管理")')
    pg.wait_for_selector('.el-tabs__item:has-text("平台与账号")', timeout=10_000)
    pg.click('.el-tabs__item:has-text("平台与账号")')
    return pg.locator('.acct-card:has-text("稀土掘金")').wait_for(timeout=10_000)


def card_online(js_card="稀土掘金"):
    """账号卡片出现「在线」标签 = 登录态已生效。"""
    return f"""() => {{
        const c = [...document.querySelectorAll('.acct-card')]
            .find(x => x.innerText.includes('{js_card}'));
        return !!c && [...c.querySelectorAll('.el-tag')]
            .some(t => t.innerText.includes('在线'));
    }}"""


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
        goto_accounts(pg)
        step("1.1 Web UI 加载，管理视图平台账号卡片渲染完成", True)

        card = pg.locator('.acct-card:has-text("稀土掘金")')
        card.locator('button:has-text("登录")').click()
        try:
            wait_ui(
                pg,
                """() => document.body.innerText.includes('等待扫码') ||
                [...document.querySelectorAll('.acct-card .el-tag')]
                    .some(t => t.innerText.includes('在线'))""",
                15_000,
            )
            step("1.2 点「登录」→ 按钮变「等待扫码…」（或已完成变在线）", True)
        except Exception as e:
            step("1.2 点「登录」→ 按钮变「等待扫码…」", False, str(e)[:80])
        pg.screenshot(path=str(SHOTS / "1_click_login.png"))

        # ---------- 阶段 2：扫码 → 登录态自动生效（不刷新页面） ----------
        try:
            wait_ui(pg, card_online(), 120_000)
            step("2.1 模拟扫码完成 → 卡片自动变「在线」（登录态已保存）", True)
        except Exception as e:
            step("2.1 模拟扫码完成 → 卡片自动变「在线」", False, str(e)[:80])
        pg.screenshot(path=str(SHOTS / "2_login_success.png"))

    # ---------- 阶段 3：REST 层确认登录态落库 ----------
    accs = requests.get(f"{WEB}/accounts", timeout=5).json()
    jue = [a for a in accs if a.get("platform") == "juejin"]
    ok = bool(jue) and jue[0].get("status") == "logined"
    step(
        "3.1 GET /accounts → juejin/default = logined",
        ok,
        json.dumps(jue, ensure_ascii=False)[:90],
    )

    # ---------- 阶段 4：Web UI 建文档（管理文档） ----------
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        pg = br.new_page(viewport={"width": 1440, "height": 900})
        pg.goto(f"{WEB}/static/index.html")
        pg.wait_for_selector("header.hdr", timeout=20_000)

        pg.click('button:has-text("新建")')
        pg.wait_for_selector('input[placeholder="文章标题"]', timeout=10_000)
        pg.fill('input[placeholder="文章标题"]', "模拟登录链路验证文章")
        pg.fill(
            '.md-editor [contenteditable="true"]',
            "# 模拟登录链路验证文章\n\n这篇文章由 ai-content-hub 端到端模拟流程发布，"
            "用于验证「登录 → 拿到登录态 → 管理文档 → 发布」的完整链路是否真实可用。\n\n"
            "- 步骤一：点击登录，打开平台扫码页\n- 步骤二：完成扫码，登录态自动保存并复用\n"
            "- 步骤三：回到管理界面建文档并一键发布\n\n"
            "发布成功后，发布实例会记录平台返回的文章编号，文章状态也会同步更新，"
            "方便后续原地更新与数据核对。若发布实例返回文章编号，后续可以据此对同一篇文章做原地更新，保持多平台内容一致。",
        )
        pg.click('button:has-text("保存")')
        try:
            pg.wait_for_selector(".el-message--success", timeout=15_000)
            step("4.1 新建文章并保存成功（UI 提示「已保存」）", True)
        except Exception as e:
            step("4.1 新建文章并保存成功", False, str(e)[:80])

        arts = requests.get(f"{WEB}/articles", timeout=5).json()
        hit = [a for a in arts if a.get("title") == "模拟登录链路验证文章"]
        step(
            "4.2 REST /articles 能查到刚建的文章",
            bool(hit),
            f"id={hit[0]['id'] if hit else '-'}",
        )

        # ---------- 阶段 5：发布到掘金（模拟） ----------
        pg.click('button:has-text("发布")')  # 编辑器头部 → 发布弹窗
        pg.wait_for_selector(".plat-card", timeout=10_000)
        pg.click('.plat-card:has-text("稀土掘金")')  # 勾选平台
        pg.wait_for_selector(".plat-card.on", timeout=5_000)
        pg.click('.el-dialog button:has-text("发布到")')  # 弹窗底部「发布到 N 个平台」
        try:
            wait_ui(
                pg,
                """() => [...document.querySelectorAll('.pub-results .res-row')]
                .some(r => r.classList.contains('ok') && r.innerText.includes('juejin'))""",
                120_000,
            )
            step("5.1 发布成功：结果面板出现 juejin 成功行", True)
        except Exception as e:
            step("5.1 发布成功：结果面板出现 juejin 成功行", False, str(e)[:80])
        pg.screenshot(path=str(SHOTS / "3_publish_success.png"))
        br.close()

    # ---------- 阶段 6：数据层确认发布记录 ----------
    art_id = hit[0]["id"] if hit else None
    if art_id:
        pubs = requests.get(
            f"{WEB}/publications", params={"article_id": art_id}, timeout=5
        ).json()
        p0 = next((p for p in pubs if p.get("platform") == "juejin"), {})
        ok = p0.get("post_id") == "art-2001" and p0.get("status") == "ok"
        art = requests.get(f"{WEB}/articles/{art_id}", timeout=5).json()
        ok = ok and art.get("status") == "published"
        step(
            "6.1 发布记录 post_id=art-2001 且文章状态=published",
            ok,
            json.dumps(
                {k: p0.get(k) for k in ("platform", "status", "post_id", "post_url")},
                ensure_ascii=False,
            )
            + f" article.status={art.get('status')}",
        )
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

