# E2E 测试套件

全部测试基于**本地模拟平台**（Flask mock），不需要真实平台账号，也不会对外发任何请求。
mock 的接口/页面元素与真实平台同构（掘金内容 API、知乎 Draft.js 编辑器结构），
验证的是适配器的**真实代码路径**（选择器、接口调用、跳转判定），只是把目标域名换成 127.0.0.1。

## 文件说明

```
tests/
├── mocks/
│   ├── mock_juejin.py          # 模拟掘金：登录页+扫码+内容 API        :9102
│   ├── mock_zhihu.py           # 模拟知乎：登录页+Draft.js 编辑器      :9103
│   └── mock_openai.py          # 模拟 OpenAI 兼容接口（AI 写稿联调）   :9101
├── run_patched_server.py       # Web 服务 :8800（掘金适配器指向 mock）
├── run_patched_server_zhihu.py # Web 服务 :8800（知乎适配器指向 mock）
├── e2e_login_flow.py           # 掘金 6 阶段：登录→扫码→在线→建文档→发布→落库
├── e2e_screenshots.py          # 掘金全程截图版：REST 计时 + UI 每步截图 + 持久化
├── e2e_zhihu.py                # 知乎 API 级 4 步冒烟
└── e2e_zhihu_screenshots.py    # 知乎全程截图版（编辑器注入 → /p/{id} 跳转）
```

## 跑法（掘金）

```bash
pip install -r requirements.txt && playwright install chromium

python tests/mocks/mock_juejin.py &            # 模拟掘金 :9102
python tests/run_patched_server.py &           # Web 服务 :8800
python tests/e2e_login_flow.py                 # 流程断言版
python tests/e2e_screenshots.py [截图目录]      # 截图留证版（默认 tests/shots）
```

## 跑法（知乎）

```bash
python tests/mocks/mock_zhihu.py &             # 模拟知乎 :9103
python tests/run_patched_server_zhihu.py &     # Web 服务 :8800
python tests/e2e_zhihu.py                      # API 级冒烟（不走 Web UI）
python tests/e2e_zhihu_screenshots.py [截图目录]
```

## 跑法（AI 写稿离线联调）

```bash
python tests/mocks/mock_openai.py &
# config.json 里把 openai_base_url 改成 http://127.0.0.1:9101/v1
```

## 原理与边界

- **运行时 patch**：测试通过改适配器类属性（`login_url`/`home_url`/`DOMAIN`）和模块级
  常量（`jj.API`）把流量指向 mock，`server.api` 导入前完成 patch，产品代码零改动。
- **mock 扫码**：登录页 6 秒倒计时自动「扫码」= 种 cookie + 跳转，等价真人扫码链路；
  也保留手动按钮供演示。
- **测不到的**：真实平台的风控、签名（如知乎 x-zse-96）、改版差异——这些只能拿真号
  跑一次 `python cli.py login <平台>` 验证。真机登录后登录态落在 `data/profiles/`，
  与 mock 测试互不干扰。
