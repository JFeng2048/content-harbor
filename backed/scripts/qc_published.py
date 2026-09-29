# -*- coding: utf-8 -*-
"""发布内容质检：逐篇打开已发布文章，查乱码/错乱/代码块/表格渲染。"""
import sys, time, json, re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from service.publishing.browser import BuiltinBrowser
from service.publishing.adapters.csdn import CSDNAdapter
from service.publishing.adapters.zhihu import ZhihuAdapter

# 乱码特征：替换符 + UTF-8 被当 Latin-1 解的典型序列
MOJIBAKE_PAT = re.compile(
    r"[\ufffd]|æ[-–—]?[˜¯]?|ç[-–—]?|ä¸|å¤|ç›¸|ç»|è¿|è®|é" 
)

def audit_page(page, url, platform, shot):
    """打开文章页，抽取渲染质量指标。"""
    r = {"url": url, "platform": platform, "ok": False}
    try:
        page.goto(url, timeout=60000, wait_until="domcontentloaded")
        time.sleep(5)
        r["http_title"] = page.title()[:60]
        m = page.evaluate("""() => {
            // 主内容容器（各平台不同，取文本量最大的 article 容器）
            const cands = document.querySelectorAll('article, #content_views, '
              + '.Post-RichTextContainer, .RichText, [class*=content]');
            let best = null, bestLen = 0;
            for (const c of cands) {
                const t = (c.innerText||'').trim();
                if (t.length > bestLen) { best = c; bestLen = t.length; }
            }
            if (!best) return null;
            return {
                textLen: bestLen,
                text: best.innerText.slice(0, 400),
                preCount: best.querySelectorAll('pre').length,
                codeCount: best.querySelectorAll('code').length,
                tableCount: best.querySelectorAll('table').length,
                imgCount: best.querySelectorAll('img').length,
                h2h3: best.querySelectorAll('h2,h3').length,
            };
        }""")
        if not m:
            r["error"] = "没找到内容容器"
            return r
        r.update(m)
        # 乱码检测
        text = m.get("text", "")
        hits = MOJIBAKE_PAT.findall(text)
        r["mojibake_hits"] = len(hits)
        r["sample"] = text[:180].replace("\n", "¶")
        # 内容完整性参考：正文长度
        r["ok"] = m["textLen"] > 500 and len(hits) == 0
        page.screenshot(path=f"data/qc_{shot}.png", full_page=False)
        r["shot"] = f"data/qc_{shot}.png"
    except Exception as e:
        r["error"] = f"{type(e).__name__}: {str(e)[:120]}"
    return r

results = []

# ---- CSDN 3 篇 ----
br = BuiltinBrowser("csdn", "default", headless=True)
page = br.start().new_page()
for aid, tag in [("166252941", "csdn1"), ("166254225", "csdn2"), ("166254273", "csdn3")]:
    url = f"https://blog.csdn.net/weixin_56622231/article/details/{aid}"
    print(f"[CSDN] {aid} 检查中…")
    results.append(audit_page(page, url, "csdn", tag))
br.close()

# ---- 知乎 2 篇 ----
br2 = BuiltinBrowser("zhihu", "default", headless=True)
page2 = br2.start().new_page()
za = ZhihuAdapter()
try:
    arts = za.list_articles(page2, limit=3)
    for i, a in enumerate(arts[:2]):
        print(f"[知乎] {a['post_id']} {a['title'][:30]} 检查中…")
        results.append(audit_page(page2, a["url"], "zhihu", f"zh{i+1}"))
except Exception as e:
    print(f"知乎列表失败: {e}")
    results.append({"platform": "zhihu", "error": str(e)[:120]})
br2.close()

print("\n" + "=" * 70)
for r in results:
    print(f"\n● {r.get('platform')} {r.get('url', '')}")
    if r.get("error"):
        print(f"  ✗ 错误: {r['error']}")
        continue
    print(f"  标题: {r['http_title']}")
    print(f"  正文长度: {r['textLen']} 字 | 代码块: {r['preCount']} pre/{r['codeCount']} code | "
          f"表格: {r['tableCount']} | 图片: {r['imgCount']} | 标题层级: {r['h2h3']}")
    print(f"  乱码命中: {r['mojibake_hits']}")
    print(f"  开头样例: {r['sample'][:120]}")
    print(f"  判定: {'✓ 正常' if r['ok'] else '⚠ 需人工查看'}")
