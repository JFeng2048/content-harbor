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


def write_article(topic, style="", words=2000, tags_hint="", model=None):
    """写一篇完整的文章，返回结构化结果，可直接入库。"""
    prompt = f"""写主题为「{topic}」的技术文章，目标 {words} 字左右。
{f'风格要求：{style}' if style else ''}
{f'建议涉及：{tags_hint}' if tags_hint else ''}

先输出一行标题（以「标题：」开头），然后空一行，再输出 Markdown 正文。"""
    raw = chat([{"role": "system", "content": SYSTEM_WRITE},
                {"role": "user", "content": prompt}], model=model)

    title, body = topic, raw
    if "标题：" in raw:
        head, _, rest = raw.partition("标题：")
        line, _, body = rest.partition("\n")
        title = line.strip() or topic
        body = body.lstrip("\n")
    return {"title": title, "content_md": body,
            "summary": summarize(body, model=model),
            "tags": suggest_tags(title, body, model=model),
            "source": "ai", "ai_model": model or _cfg("AI_MODEL", DEFAULT_MODEL)}


def rewrite(content_md, instruction, model=None):
    """按指令改写，比如"改成更口语""补充一个踩坑章节"。"""
    return chat([{"role": "system", "content": SYSTEM_WRITE},
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
