# -*- coding: utf-8 -*-
"""响应式布局回归：小/中/宽三视口下顶栏不溢出、关键控件不换行、页面无横向溢出。

前置：服务已在 :8800（python cli.py serve）。

用法：python tests/e2e_responsive.py
"""

import sys
from pathlib import Path

import requests
from patchright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
WEB = "http://127.0.0.1:8800"

VIEWPORTS = [
    (390, 844, "mobile"),
    (768, 1024, "tablet"),
    (1024, 768, "laptop-sm"),
]

results = []


def step(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}   {detail}", flush=True)


JS_HEADER_AUDIT = """() => {
    const vw = window.innerWidth;
    const out = { vw, docOverflow: document.documentElement.scrollWidth - vw, issues: [] };
    const hdr = document.querySelector('header.hdr');
    if (!hdr) { out.issues.push('header missing'); return out; }
    out.hdrOverflow = hdr.scrollWidth - hdr.clientWidth;

    const linesOf = (el) => {
        const range = document.createRange();
        range.selectNodeContents(el);
        const tops = [...range.getClientRects()]
            .filter(r => r.width > 0 && r.height > 0)
            .map(r => r.top)
            .sort((a, b) => a - b);
        // 字体度量会让同一行的 rect top 相差 1~2px，按 6px 容差聚类成"行"
        let lines = 0, last = -Infinity;
        for (const t of tops) {
            if (t - last > 6) { lines += 1; last = t; }
        }
        return lines;
    };
    const check = (label, el, { mustFit = true, maxLines = 1 } = {}) => {
        if (!el) { out.issues.push(label + ': missing'); return; }
        const st = getComputedStyle(el);
        if (st.display === 'none' || st.visibility === 'hidden') return; // 被设计为隐藏 = 合格
        const r = el.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) return;
        if (mustFit && (r.left < -1 || r.right > vw + 1))
            out.issues.push(`${label}: outside viewport [${Math.round(r.left)},${Math.round(r.right)}] vw=${vw}`);
        const lines = linesOf(el);
        if (lines > maxLines)
            out.issues.push(`${label}: text wrapped to ${lines} lines (box ${Math.round(r.width)}x${Math.round(r.height)})`);
    };

    const newBtn = [...hdr.querySelectorAll('button')].find(b => b.textContent.includes('新建'));
    check('new-btn', newBtn);
    hdr.querySelectorAll('.vs-btn').forEach((b, i) => check('vs-btn-' + i, b));
    check('brand-name', hdr.querySelector('.brand-name'));
    return out;
}"""


def audit(pg, w, h, tag):
    pg.set_viewport_size({"width": w, "height": h})
    pg.goto(f"{WEB}/static/index.html")
    pg.wait_for_selector("header.hdr", timeout=20_000)
    pg.wait_for_timeout(600)
    a = pg.evaluate(JS_HEADER_AUDIT)
    step(
        f"[{tag} {w}x{h}] 顶栏控件均在视口内且不换行",
        not a["issues"],
        "; ".join(a["issues"]) or "clean",
    )
    step(
        f"[{tag} {w}x{h}] 页面无横向溢出",
        a["docOverflow"] <= 1,
        f"scrollWidth-overflow={a['docOverflow']}px",
    )
    step(
        f"[{tag} {w}x{h}] 顶栏内部无溢出",
        a["hdrOverflow"] <= 1,
        f"hdr overflow={a['hdrOverflow']}px",
    )


def main():
    r = requests.get(f"{WEB}/health", timeout=5)
    if not r.ok or not r.json().get("ok"):
        step("0.1 服务在线", False, f"status={r.status_code}")
        return 1
    step("0.1 服务在线", True)

    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        pg = br.new_page(viewport={"width": 390, "height": 844})
        for w, h, tag in VIEWPORTS:
            audit(pg, w, h, tag)
        br.close()

    failed = [n for n, ok, _ in results if not ok]
    print(f"\n=== {len(results) - len(failed)}/{len(results)} passed ===")
    if failed:
        for n in failed:
            print(f"  FAIL {n}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
