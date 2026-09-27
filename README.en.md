# Harbor · Self-hosted AI Content Hub

> **Write once, publish everywhere.** Your articles live in your own database; an AI (or any script) manages the full lifecycle — write, edit, publish, update, and list across 10 Chinese tech platforms.

<p>
  <img alt="license" src="https://img.shields.io/badge/license-MIT-green">
  <img alt="python" src="https://img.shields.io/badge/python-3.10%2B-blue">
  <img alt="platforms" src="https://img.shields.io/badge/platforms-10-blueviolet">
  <img alt="mcp" src="https://img.shields.io/badge/AI-MCP-orange">
</p>

## Highlights

- **One-click multi-platform publishing** — Juejin / CSDN / Cnblogs / Zhihu / SegmentFault / Bilibili / Toutiao / OSChina / 51CTO / your own blog (WordPress/Typecho).
- **In-place update, not re-post** — edits reopen each platform's editor and modify the original article; URL, comments and likes stay intact.
- **AI takes full control** — built-in MCP Server + REST API; Claude or any script can create, publish, fetch and update articles.
- **Fully self-hosted** — article DB, login sessions and browser profiles all live on your machine. No third-party SaaS.
- **Captcha-free channels** — Cnblogs / 51CTO / self-hosted blogs use the MetaWeblog XML-RPC protocol: configure credentials once, no browser, no verification.
- **Built-in anti-detection browser** — persistent per-platform profiles, scan a QR code once and stay logged in.

## Quick Start

```bash
git clone https://gitcode.com/badhope/content-harbor.git
cd content-harbor
pip install -r requirements.txt
python3 -m patchright install chromium

cp config.example.json config.json

# Scan QR once (on a machine with a display)
python cli.py --headed login --platform juejin

# Start the web UI at http://127.0.0.1:8800
python cli.py serve
```

## Supported Platforms (10)

| Platform | Method | Publish | Update | List |
|---|---|---|---|---|
| Juejin (稀土掘金) | browser + API | ✅ | ✅ | ✅ |
| CSDN | browser | ✅ | ✅ | ✅ |
| Cnblogs (博客园) | MetaWeblog | ✅ | ✅ | ✅ |
| 51CTO | MetaWeblog | ✅ | ✅ | ✅ |
| Self-hosted blog | MetaWeblog | ✅ | ✅ | ✅ |
| Zhihu (知乎) | browser UI | ✅ | ✅ | — |
| SegmentFault (思否) | API + UI | ✅ | ✅ | — |
| Bilibili column | creator API | ✅ draft | ✅ draft | — |
| Toutiao (头条号) | browser UI | ✅ | — | — |
| OSChina (开源中国) | browser UI | ✅ | — | — |

## Architecture

```
AI / scripts  ── MCP or REST ──>  business layer (articles / publications / jobs)
                                        │
                          built-in Chromium, one persistent profile per platform
                                        │
                          adapters: juejin / csdn / cnblogs / zhihu / sf / bilibili /
                          toutiao / oschina / 51cto / metaweblog
                                        │
                          publish · list · in-place update
```

## Docs

- [README (中文)](README.md) — full documentation in Chinese
- [ARCHITECTURE.md](ARCHITECTURE.md) — design details
- [PLATFORM_CONNECTION.md](PLATFORM_CONNECTION.md) — per-platform integration notes
- [docs/PLATFORM_PUBLISH_GUIDE.md](docs/PLATFORM_PUBLISH_GUIDE.md) — publish workflow per platform

## License

[MIT](LICENSE) © 2026 badhope
