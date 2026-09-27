# -*- coding: utf-8 -*-
"""AI 写稿模块：文章从哪来。

走 OpenAI 兼容协议，所以 DeepSeek / 通义 / 豆包 / Kimi / 智谱 / 本地 Ollama
全都能用——换家只改环境变量，代码一行不动。

配置（环境变量或 config.json）：
    AI_API_KEY    必填
    AI_BASE_URL   默认 https://api.deepseek.com/v1
    AI_MODEL      默认 deepseek-chat
"""

import json
import os
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / "config.json"

DEFAULT_BASE = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"
TIMEOUT = 180

# 写作风格档案：改这个文件就改了全平台产出风格，不用动代码。
# 覆盖方式：环境变量 WRITING_STYLE_FILE 指向另一份档案。
STYLE_FILE = ROOT / "docs" / "writing-style.md"
STYLE_MARK = "【写作风格档案】"
# 篇幅兜底：AI 返回正文短于 要求字数 × 该比例 时自动续写一轮（只续一轮，
# 防止无止境拉长；比例 0.6 是"明显偷工"与"风格偏短但合格"的分界）。
MIN_COMPLETENESS_RATIO = 0.6
MAX_EXPAND_ROUNDS = 1


def _cfg(key, default=None):
    return os.environ.get(key) or _file_cfg().get(key) or default


def _load_dotenv():
    """零依赖 .env 加载：项目根 .env 里的 KEY=VALUE 作为最底层兜底。
    不覆盖已存在的真实环境变量，不覆盖 config.json 已解析的值。"""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _file_cfg():
    _load_dotenv()
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


class AIError(Exception):
    pass


SYSTEM_WRITE = """你是资深技术作者，写给中文开发者看。
要求：
1. 有观点、有细节，不写正确的废话
2. 代码块必须标语言，能跑
3. 结构清晰：问题 → 方案 → 踩坑 → 结论
4. 口语化，别端着，但别用感叹号堆情绪
5. 直接输出 Markdown 正文，不要包裹 ```markdown 代码块
"""


def style_file() -> Path:
    """风格档案路径：环境变量优先，其次 docs/writing-style.md。"""
    env = os.environ.get("WRITING_STYLE_FILE", "").strip()
    return Path(env) if env else STYLE_FILE


def load_style() -> str:
    """读写作风格档案。文件不存在/读失败一律降级为空串（不让风格配置拖垮写稿）。"""
    p = style_file()
    # aqg: top-level boundary —— 风格档案是可选增强，读失败（编码/权限/路径含
    # 非法字符）不能连带写稿失败，降级为"无档案"继续，属刻意边界
    try:
        return p.read_text(encoding="utf-8").strip() if p.exists() else ""
    except Exception:
        return ""


def system_write(extra_style: str = "") -> str:
    """system 提示 = 基础要求 + 风格档案 + 单次调用的追加要求（追加不覆盖）。"""
    parts = [SYSTEM_WRITE.strip()]
    style = load_style()
    if style:
        parts.append("%s\n%s" % (STYLE_MARK, style))
    if extra_style and extra_style.strip():
        parts.append("【本次追加要求】\n%s" % extra_style.strip())
    return "\n\n".join(parts)


def chat(messages, model=None, temperature=0.7, max_tokens=4096):
    api_key = _cfg("AI_API_KEY")
    if not api_key:
        raise AIError("没配 AI_API_KEY。export AI_API_KEY=xxx 或写进 config.json")

    base = _cfg("AI_BASE_URL", DEFAULT_BASE).rstrip("/")
    model = model or _cfg("AI_MODEL", DEFAULT_MODEL)

    try:
        r = requests.post(f"{base}/chat/completions",
                          headers={"Authorization": f"Bearer {api_key}",
                                   "Content-Type": "application/json"},
                          json={"model": model, "messages": messages,
                                "temperature": temperature,
                                "max_tokens": max_tokens},
                          timeout=TIMEOUT)
    except Exception as e:
        raise AIError(f"调不通 AI 接口（{base}）：{e}")

    if r.status_code != 200:
        raise AIError(f"AI 接口返回 {r.status_code}: {r.text[:200]}")

    data = r.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        raise AIError(f"返回结构异常: {json.dumps(data, ensure_ascii=False)[:200]}")


def _split_title(raw: str, topic: str):
    """拆出「标题：」行。AI 没按格式输出时，标题退回 topic、正文整段保留。"""
    if "标题：" not in raw:
        return topic, raw
    _, _, rest = raw.partition("标题：")
    line, _, body = rest.partition("\n")
    return (line.strip() or topic), body.lstrip("\n")


def write_article(topic, style="", words=2000, tags_hint="", model=None):
    """写一篇完整的文章，返回结构化结果，可直接入库。

    篇幅兜底：正文明显短于要求时自动续写一轮（MAX_EXPAND_ROUNDS），
    避免"要 2000 字结果给 600 字"的半成品流进发布链路。
    """
    prompt = f"""写主题为「{topic}」的技术文章，目标 {words} 字左右。
{f'建议涉及：{tags_hint}' if tags_hint else ''}

先输出一行标题（以「标题：」开头），然后空一行，再输出 Markdown 正文。"""
    raw = chat([{"role": "system", "content": system_write(style)},
                {"role": "user", "content": prompt}], model=model)
    title, body = _split_title(raw, topic)

    floor = int(words * MIN_COMPLETENESS_RATIO)
    for _ in range(MAX_EXPAND_ROUNDS):
        if len(body.strip()) >= floor:
            break
        more = chat([
            {"role": "system", "content": system_write(style)},
            {"role": "user", "content":
                f"继续扩写下面这篇文章，补足到 {words} 字左右。只输出新增的 Markdown "
                f"正文段落，不要重复已有内容，不要输出标题行。\n\n---\n\n{body[:6000]}"},
        ], model=model)
        if not more.strip():
            break
        body = body.rstrip() + "\n\n" + more.strip()

    return {"title": title, "content_md": body,
            "summary": summarize(body, model=model),
            "tags": suggest_tags(title, body, model=model),
            "source": "ai", "ai_model": model or _cfg("AI_MODEL", DEFAULT_MODEL),
            "style_source": str(style_file()) if load_style() else ""}


def rewrite(content_md, instruction, model=None):
    """按指令改写，比如"改成更口语""补充一个踩坑章节"。"""
    return chat([{"role": "system", "content": system_write()},
                 {"role": "user", "content": f"按这个要求改写下面这篇文章：{instruction}\n\n---\n\n{content_md}"}],
                model=model)


def polish(content_md, model=None):
    """润色：修错别字、顺语句、统一代码块语言标识，不改原意。"""
    return rewrite(content_md, "润色：修错别字和病句、统一代码块语言标识、理顺结构，不要改变原意和篇幅",
                   model=model)


def summarize(content_md, model=None):
    """生成 50-150 字摘要，各平台发布时用。"""
    try:
        return chat([{"role": "user", "content":
            f"为下面这篇文章写一段 50-150 字的摘要，突出价值，不要复述标题：\n\n{content_md[:6000]}"}],
            max_tokens=300, model=model)
    except Exception:
        return content_md[:100].replace("\n", " ")


def suggest_tags(title, content_md, model=None):
    """推荐 3-5 个标签，逗号分隔。"""
    try:
        raw = chat([{"role": "user", "content":
            f"为这篇文章推荐 3-5 个中文技术标签，只输出逗号分隔的标签，不要解释：\n"
            f"标题：{title}\n\n{content_md[:3000]}"}], max_tokens=100, model=model)
        tags = [t.strip() for t in raw.replace("，", ",").split(",") if t.strip()]
        return ",".join(tags[:5])
    except Exception:
        return ""


def is_ready():
    return bool(_cfg("AI_API_KEY"))
