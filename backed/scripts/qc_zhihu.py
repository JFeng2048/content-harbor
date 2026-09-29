# -*- coding: utf-8 -*-
"""知乎已发文章质检（独立脚本，无导入副作用）。"""
import sys, time, re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from service.publishing.browser import BuiltinBrowser

MOJIBAKE_PAT = re.compile(r"[\ufffd]|æ[-–—]?[˜¯]?|ç[-–—]?|ä¸|å¤|ç›¸|ç»|è¿|è®")

br = BuiltinBrowser("zhihu", "default", headless=True)
page = br.start().new_page()

for i, pid in enumerate(["2085187720285000343", "2085190746425115644"]):
    url = f"https://zhuanlan.zhihu.com/p/{pid}"
    print(f"\n[知乎] {pid}")
    try:
        page.goto(url, timeout=60000, wait_until="domcontentloaded")
        time.sleep(5)
        print(f"  页面标题: {page.title()[:60]}")
        m = page.evaluate("""() => {
            const cands = document.querySelectorAll('.Post-RichTextContainer, .RichText, article');
            let best = null, bestLen = 0;
            for (const c of cands) {
                const t = (c.innerText||'').trim();
                if (t.length > bestLen) { best = c; bestLen = t.length; }
            }
            if (!best) return null;
            return {textLen: bestLen, text: best.innerText.slice(0, 300),
                preCount: best.querySelectorAll('pre').length,
                codeCount: best.querySelectorAll('code').length,
                tableCount: best.querySelectorAll('table').length,
                h2h3: best.querySelectorAll('h2,h3').length};
        }""")
        if not m:
            print("  ✗ 没找到内容容器（可能被登录墙/删除）")
            page.screenshot(path=f"data/qc_zhihu{i+1}.png")
            continue
        hits = MOJIBAKE_PAT.findall(m["text"])
        print(f"  正文长度: {m['textLen']} 字 | 代码块: {m['preCount']} pre/{m['codeCount']} code | "
              f"表格: {m['tableCount']} | 标题层级: {m['h2h3']}")
        print(f"  乱码命中: {len(hits)}")
        print(f"  开头样例: {m['text'][:150]}".replace(chr(10), "¶"))
        print(f"  判定: {'✓ 正常' if m['textLen'] > 500 and not hits else '⚠ 需人工看'}")
        page.screenshot(path=f"data/qc_zhihu{i+1}.png")
    except Exception as e:
        print(f"  ✗ {type(e).__name__}: {str(e)[:120]}")
br.close()
