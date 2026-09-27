# ARCHITECTURE.md — AI 内容中台架构文档

> **唯一真理源**：所有代码源于本文档、服务于本文档；任何影响架构/接口/数据模型/依赖的代码变更，
> 必须立即回写对应章节 + Changelog。文档与代码脱节 = 架构失败。

| 项 | 值 |
|---|---|
| 版本 | 0.3.0（工作流引擎引入） |
| 日期 | 2026-09-22 |
| 状态 | M1 实施中（绞杀者增量迁移第 1 模块） |

---

## 1. 系统概览

AI 内容中台：**写作 → 合规 → 多平台发布 → 验证 → 人机协作收尾** 的一站式管线。

- 用户：站长本人（写作/发布），AI Agent（REST/MCP 无人值守调用）
- 平台适配：CSDN / 知乎 / 掘金 / 博客园 / B站 / 头条 / 开源中国 / SegmentFault / 自建博客(WordPress/Typecho)
- 技术栈：Python 3.13 + FastAPI + SQLite + Playwright（反检测浏览器）+ Vue3/Element Plus

## 2. 现状架构基线（as-is，2026-09-21）

```
┌─────────────────────────────────────────────────────────┐
│  Vue3 前端（写作视图 / 管理视图 / 发布向导）                │
├─────────────────────────────────────────────────────────┤
│  FastAPI (server/api.py, 559行)                          │
│  文章CRUD · 发布(同步+异步任务) · 登录任务 · pending-human │
├─────────────────────────────────────────────────────────┤
│  Hub 上帝类 (core/service.py, 577行)                      │
│  publish(): 写死顺序循环 ─ 逐平台 adapter.publish         │
│  update()/sync_pending()/refresh()/ai_write()            │
├──────────────────┬──────────────────────────────────────┤
│ 适配器层          │ 基础设施                              │
│ core/adapters/*  │ browser.py(实例池+反检测+验证码策略)    │
│ 9个平台,经实测    │ db.py(SQLite) · ai.py(OpenAI兼容)     │
│ ✅ 值钱,保留      │ gate.py(AIGC合规) · observability.py  │
└──────────────────┴──────────────────────────────────────┘
```

### 已知问题（本次重构动机）

| # | 问题 | 位置 | 影响 |
|---|---|---|---|
| P1 | publish 是写死顺序循环，无分支无决策 | service.py:440-486 | 无法按结果分流，"agent 驱动"名不副实 |
| P2 | 重试硬编码 `for attempt in (1,2)`，仅覆盖浏览器崩溃 | service.py:322 | 业务性失败（风控/超时）不会重试 |
| P3 | human-in-loop 只是 `pending_human` 特例 | service.py:456-458 | 无通用"暂停-等人-恢复"机制，掘金草稿外的场景接不住 |
| P4 | 失败无智能分诊：只有 ok/failed 两态 | service.py:472-479 | 失败后要么人肉重试要么放弃 |
| P5 | 根目录 ~30 个 probe_/delete_/dump_*.py 调试残渣 | 项目根 | 工程卫生差 |

## 3. 目标架构（to-be）

**绞杀者增量**：适配器层与 Hub 核心方法原样保留；新增工作流引擎层（LangGraph）接管发布编排；
旧路径保留可回退，前端逐步切流。

```
┌────────────────────────────────────────────────────────────┐
│ Vue3 前端（后续 M2：管理视图增加 Run 详情/恢复入口）           │
├────────────────────────────────────────────────────────────┤
│ FastAPI                                                    │
│ 旧端点全部保留 · 新增 /runs 系列（启动/查询/恢复）             │
├────────────────────────────────────────────────────────────┤
│ 🆕 工作流引擎层 workflows/                                   │
│   graph.py  发布工作流图（LangGraph StateGraph）             │
│   nodes.py  确定性节点 + LLM 决策节点                        │
│   state.py  PublishState 状态模型                           │
│   runner.py RunManager（线程执行/断点恢复/SQLite 持久化）      │
├────────────────────────────────────────────────────────────┤
│ Hub（瘦身为"工具箱"）· 适配器层（原样保留）· 基础设施（原样）   │
└────────────────────────────────────────────────────────────┘
```

### 3.1 发布工作流图拓扑

```
START
  → load_article      [确定性] 载入文章+预检（标题非空，缺失→终止）
  → compliance_gate   [确定性] 复用 core.gate（AIGC 闸门，拒绝→终止）
  → next_platform     [路由]   平台队列弹一个；空→aggregate
  → ensure_login      [确定性] 登录态检查；未登录→该平台记 failed(原因)→next_platform
  → publish_platform  [确定性] Hub.publish_single（外包原循环体）；dry_run 时合成结果
  → verify_publish    [确定性] GET post_url 验证可达+标题命中；draft_only/dry_run 跳过
  → triage            [LLM]    成功→done；失败→分诊 retry/human/skip
      ├─ retry   (attempts<上限) → publish_platform（回边）
      ├─ human   → wait_human [interrupt 挂起等人] → (恢复后) → verify_publish
      └─ skip/done                → next_platform
  → aggregate         [确定性] 收敛文章状态 + 写 run 摘要 + 触发前端可查
END
```

### 3.2 决策点与自主度（ADR-002 落地）

| 决策点 | 归属 | 规则 |
|---|---|---|
| 平台选择 | 人工指定（M3 可选交给 LLM 推荐） | API 入参 platforms，缺省不猜 |
| 内容按平台适配 | M3 可选节点，config 开关 | 默认关（当前各适配器已内置格式处理） |
| 失败分诊 retry/human/skip | **LLM**（triage 节点） | heuristic 兜底（网络类→重试，配置类→human，其他→skip）；LLM 不可用时走兜底 |
| AI 内容正式上线 | 人工（既有合规闸门） | AI 源强制 draft_only，不因工作流改变 |

### 3.3 状态模型（PublishState 核心字段）

| 字段 | 类型 | 说明 |
|---|---|---|
| run_id / article_id | str / int | 运行标识与文章 |
| platforms_queue | list[str] | 待发平台队列（next_platform 弹出） |
| current_platform | str | 当前处理平台 |
| draft_only / dry_run / account | bool/bool/str | 发布选项 |
| article / gate | dict | 载入的文章与闸门结果 |
| results | list[dict]（append reducer） | 每平台终态：platform/ok/status/post_id/post_url/error/attempts/triage |
| attempts | int | 当前平台已尝试次数（上限 config workflow.retry_limit，默认 2） |
| decisions | list[dict] | LLM 分诊决策留痕（决策+理由），审计用 |

### 3.4 运行模型与存储

- **Run**：一次发布工作流执行。状态机：`running → waiting_human → running → done | failed`
- **Checkpoint**：LangGraph SqliteSaver，每节点后落盘；进程崩溃可从最近 checkpoint 恢复
- **存储隔离（ADR-004）**：`data/workflow.db`（runs 元数据表 + checkpoint 表）独立于 `data/hub.db`，
  互不干扰迁移；runs 元数据表 `workflow_runs(id, article_id, title, platforms, status, result_json, created_at, updated_at)`
- **线程模型**：每 run 一个后台线程（复用 api.py 已验证的任务线程模式）；同 run 串行，跨 run 并发受
  Hub 实例池（POOL_MAX=4）与 per-key 互斥自然限流

### 3.5 UpdateState（update 图状态模型，M5/ADR-007）

字段级定义与 PublishState 同名契约表见 **docs/design/m5-architecture.md §4.2/§4.3**（逐字规格）；update 图拓扑见同文件 §3.1/§3.3。要点：新增 current_pub/target_pubs（实例行是原地更新的钥匙），无 draft_only；summary 无 pending_human 且不翻转 articles.status（legacy update 同语义）。

## 4. 架构决策记录（ADR）

| ADR | 决策 | 备选 | 理由 | 后果 |
|---|---|---|---|---|
| 001 | LangGraph 作工作流引擎 | 自研状态机 / Pydantic AI | 内置 checkpoint 断点续跑 + interrupt/Command 人机协作原语，直接解决 P2/P3；与现有 Python 栈零摩擦 | +1 依赖（langgraph + langgraph-checkpoint-sqlite） |
| 002 | 编排为主，关键决策交 LLM | 全自主 / 纯编排 | 发布不可逆，Playwright 步骤保持确定性；LLM 只在分诊/（可选）平台推荐/内容适配做决策 | LLM 仅在 triage 引入延迟（一次 chat，失败走 heuristic 兜底） |
| 003 | 绞杀者增量迁移 | 整体重写 | 9 个适配器经实测是核心资产；旧端点全保留可随时回退 | 过渡期双路径并存，M4 收尾收敛 |
| 004 | 工作流存储独立 `data/workflow.db` | 复用 hub.db | checkpoint 表结构与 hub schema 隔离，hub 迁移不受影响 | 备份需含两个 db 文件 |
| 005 | 内建 dry_run 模式 | 无 | 冒烟测试不打真实平台；也是用户"预演发布"的产品能力 | 节点需感知 dry_run 分支 |
| 006 | LLM 通道复用 core.ai.chat() | 引入 langchain-chat-models | OpenAI 兼容协议已通（agnes-3.0-flash），换模型零代码；避免重依赖 | 无流式/工具调用高级特性（分诊场景不需要） |
| 007 | update 独立图 + UpdateState + runner kind 路由（M5） | 单图 op 路由 / 扩展 PublishState | 不污染生产验证的 publish 资产；回退=update 图整文件弃用 | 双 State 同名字段靠契约表守护（R7） |
| 008 | sync 编排层一文一 run 扇出；refresh 永久 legacy（M5） | sync 独立跨文章图 / 全量接入 | 失败/挂起按篇隔离；零新增图成本 | 跨文章进度由客户端聚合（count+run_ids） | 
| 009 | update 门禁 draft_only=True 豁免层4、保留层1+层3（M5） | 无门禁（缺口延续）/ 全量门禁（堵死 ai_rewrite→sync） | 堵住 AI 改写内容经 update 直推线上实例的高危词缺口 | 层4 update 语境知情弱化；每次更新多一次审查耗时 |

## 5. 模块拆解与实施顺序（S3）

| 模块 | 内容 | 验收标准 | 状态 |
|---|---|---|---|
| **M1 引擎基座** | workflows/ 四文件 + Hub.publish_single 抽取 + /runs 端点 + dry_run 冒烟 | dry_run 发布 2 平台：图跑通、results 全 ok、run 落库可查、旧 /publish 端点行为不变 | ✅ 2026-09-22 完成（冒烟 3 案全过：dry_run 双平台 / 重试回边 attempts=2 / 验证码挂起→resume 恢复） |
| M2 人机协作闭环 | wait_human interrupt/resume 全链路联调 + 管理视图 Run 详情/恢复入口 + 发布向导切流引擎 + 登录态快照/check 修复 | 掘金草稿场景：run 挂起→前端可见→恢复→verify 通过→run done | ✅ 2026-09-22 完成：四场景冒烟 7 断言全过；真实掘金 E2E 挂起验证（run `2b5965ada02a`，draft_confirm，草稿 7687899083843256347，前端挂起卡片截图验收）；恢复→verify→done 腿由冒烟 C 证明，真实恢复=用户完成平台发布后点「已处理，恢复」（run 正挂起等该操作） |
| M3 Agent 决策增强 | LLM 分诊实测调优 +（可选）平台推荐 agent + 按平台内容适配开关 | 分诊决策留痕可审计；各开关默认关 | ✅ 2026-09-22：LLM 分诊生产实测（greenlet 事件正确归因）、decisions 留痕+审计弹窗、MCP publish 切流引擎；可选项（平台推荐/内容适配）按 YAGNI 未实装=天然默认关 |
| M4 收尾治理 | 根目录调试脚本归档 scripts/debug/ + legacy 路径标注 deprecated + 文档回写 | 根目录仅剩入口脚本；Changelog 完整 | ✅ 2026-09-22：根目录仅剩 cli.py（42 调试+6 工具归档）；发布主路径已切流并带 strangler 注释（update/sync/refresh 留作正式 legacy 路径，见 AUDIT 遗留表）；Changelog 0.3.0→0.3.3 完整 |
| M5 切流收尾 | update/sync 接入工作流引擎（update 专图+UpdateState+runner kind 路由；sync 编排层一文一 run 扇出；refresh 永久 legacy 裁定）+ 前端切流（编辑器「同步更新」/挂起卡片「内置浏览器打开」assist/「抓取文章入库」） | S1–S6 冒烟全绿 + legacy/引擎双跑 DB 对账一致（R1/R3 门禁） | ✅ 2026-09-22 完成（smoke_update 六案全绿 + publish 回归九断言全绿 + 端点真验 + 前端构建；规格见 docs/design/m5-architecture.md） |

## 6. 目录结构（增量）

```
content-harbor/
├── ARCHITECTURE.md          # 本文（唯一真理源）
├── workflows/               # 🆕 工作流引擎层
│   ├── __init__.py
│   ├── state.py             # PublishState
│   ├── nodes.py             # 节点实现（确定性 + LLM）
│   ├── graph.py             # 图构建
│   └── runner.py            # RunManager
├── core/                    # 适配器/浏览器/DB/AI/合规（保留）
├── server/api.py            # + /runs 系列端点（旧端点全保留）
├── web/                     # Vue3 前端（M2 接 Run 详情）
└── scripts/debug/           # M4：调试残渣归档处
```

## 7. 风险与回滚

| 风险 | 缓解 |
|---|---|
| 新引擎发布出错 | 旧 /publish 端点与 Hub.publish() 原样保留，config `workflow.enabled=false` 一键回退 |
| LangGraph API 版本漂移 | M1 锁定当前版本；核心 API（StateGraph/interrupt/Command/SqliteSaver）均为稳定面 |
| LLM 分诊误判 | heuristic 兜底 + decisions 留痕 + 重试上限，最坏退化为现状行为 |
| 双 DB 备份遗漏 | Changelog 与 README 提示；M4 在备份脚本（如有）中补 workflow.db |

## 8. Changelog

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-09-22 | 0.3.5 | **前端切流 + 平台接管**：编辑器新增「同步更新」按钮（update/workflow 切流，900s 轮询，仅启动失败回退 legacy 防双发）；挂起卡片「内置浏览器打开」（/accounts/{pf}/assist 带登录态有头接管——人工步骤不出站、不重登录，任务模式 900s）；平台与账号页「抓取文章入库」（refresh 进管理列表）；assist url 校验 422 / GET 405 已验；**MCP stdio E2E 十断言**（list_tools 13 工具/读写/账号/update 无目标 legacy 回退/sync 无 pending），content-hub 已接入 ~/.workbuddy/mcp.json。element-plus 懒加载维持缓办（触发条件=感知卡顿） |
| 2026-09-22 | 0.3.4 | **M5 切流收尾（绞杀者第二刀）**：workflows 新增 UpdateState + build_update_nodes + build_update_graph（update 专图：无 verify 节点、门禁 ADR-009、间隔 delay_article）；runner kind 泛化（start(kind=)/resume 读 meta 行选图/双图字典；workflow_runs 加 kind 列+idx_runs_kind 幂等迁移，autocommit 防 S5 并行提交竞态）；api 新增 /articles/{aid}/update/workflow 与 /sync/pending/workflow（一文一 run，failed[] 按篇隔离）、/runs 加 kind/article_id 过滤；MCP update_article/sync_pending 切流（deadline 900s，仅启动失败回退防双发）；Hub 抽取 update_single（legacy update 循环体逐行搬移，双跑 DB 对账一致）。冒烟：smoke_update S1–S6 全绿 + publish 回归全绿 |
| 2026-09-22 | 0.3.3 | **全量存量检测+优化**（详表见 `AUDIT.md`）：①playwright **进程级共享驱动单例** `_get_shared_pw` + **专属浏览器线程** `browser_thread_run`（greenlet/循环状态单线程化，根治 `inside the asyncio loop` 500 与 greenlet 跨线程发布失败，三轮三平台 9/9）；②登录快照四层永续保障（profile→auth.json 原子写→check/关窗自动保鲜→启动合回，csdn/zhihu/juejin 三份齐备且持续保鲜）；③check 落平台域+沉降重试+per-key 互斥；④hub.js 补 ElMessageBox 导入；⑤atexit 死代码移正；⑥MCP publish 切流引擎（回退仅限启动失败，防双发）；⑦DB 补 articles/jobs 共 3 索引；⑧根目录 48 残渣归档 scripts/（仅剩 cli.py）。M3/M4 收官 |
| 2026-09-22 | 0.3.2 | **核心三修复 + 真实掘金 E2E 挂起验收**：①登录态快照（`BuiltinBrowser.export_auth/_import_auth`，登录成功即由 Python 同步写 `data/profiles/*.auth.json`，开浏览器自动合回——修"扫码成功、关窗丢态"）；②`service.check` 补 goto 平台域（about:blank 上 SameSite cookie 全被拦 → 永远假"未登录"的根因）+ check 加 per-key 互斥（B3 漏洞）+ `_check_auth_settled` 沉降重试；③`_with_adapter` 对 greenlet 跨线程冲突（Cannot switch to a different thread）drop+重建重试。真实 E2E：/publish/workflow 发掘金 → 草稿 7687899083843256347 → `draft_confirm` 挂起（run `2b5965ada02a`），前端挂起卡片/运行记录截图验收；LLM 分诊生产首秀（greenlet 错误被正确归因留痕） |
| 2026-09-22 | 0.3.1 | **M2 人机协作闭环**：wait_human 升级双场景（draft_confirm 草稿确认→翻转发布实例+去验证 / recover 故障恢复→回发布节点重试），恢复动作三向路由 `wait_action: publish\|verify\|next`；triage 对 pending_human 草稿路由到挂起而非跳过；runner.list() 返回 human_task/summary、_finish 异常路径保留 result_json；前端：发布向导切流 /publish/workflow（仅启动失败回退 legacy，防双发）、管理视图挂起卡片（打开平台/已处理恢复/放弃/详情）+「运行记录」标签页（run 全史+分诊决策审计弹窗）、30s 轮询新挂起弹常驻通知。冒烟四场景 7 断言全过 + HTTP dry_run run 验收 |
| 2026-09-22 | 0.3.0 | **M1 落地**：新增 workflows/（state/nodes/graph/runner）LangGraph 引擎层；service.py 抽取 publish_single 发布原语（legacy 循环与工作流共用）；api.py 新增 /articles/{aid}/publish/workflow + /runs{,/{id},/{id}/resume}；requirements.txt 增 langgraph 1.2.12 / langgraph-checkpoint-sqlite 3.1.1；冒烟脚本 scripts/smoke_workflow.py + smoke_hitl.py（dry_run 双平台、重试回边、interrupt/resume 三案全过）。M2/M3/M4 待做 |
| 2026-09-21 | 0.2.0 | 前端双视图改版（写作/管理 + 发布向导）；/pending-human 端点 |
| 2026-09-19 | 0.1.0 | 项目创立：文章库 × 内置浏览器 × 平台适配器 |

## 0.4.0 重构记录（refactor-v1 分支，2026-09-24）

以上 ADR（001/003/004 等）为 **0.3.x 历史决策**，已在重构中推翻，保留供追溯。

### 推翻了什么

| 旧方案 | 问题 | 新方案 |
|---|---|---|
| LangGraph 工作流引擎（workflows/ 870 行） | 一个"遍历平台+重试+等人"的循环被包装成双状态图，复杂度与功能不匹配 | `core/tasks.py` TaskManager：~100 行统一任务引擎，SQLite tasks 表持久化 + 单后台线程 + 确定性失败分诊 |
| 三个内存任务字典（LOGIN/PUBLISH/ASSIST_TASKS） | 复制粘贴三份轮询逻辑，进程重启即丢 | 全部收敛到 TaskManager.submit()/get()/list()/resume() |
| 双数据库（hub.db + workflow.db） | 备份需两文件，状态割裂 | 任务状态统一落 hub.db 的 tasks 表 |
| playwright + 手写 STEALTH_JS（120 行 JS hack） | JS patch 天花板低，JA3/TLS 指纹抹不掉 | patchright（反检测 fork，内置 TLS/自动化痕迹处理），删除全部 LAUNCH_ARGS hack |
| REST/MCP 双入口各自实现发布语义 | 维护两套，行为漂移 | 共用 service 层：REST 走任务引擎（异步），MCP 直接同步调 hub 方法 |

### 现在的统一语义

- **REST**：`POST /articles/{id}/publish|update`、`POST /sync/pending`、`POST /accounts/{p}/login|assist`、`POST /refresh/{p}` 全部返回 `{task_id}` → `GET /tasks/{task_id}` 轮询 → `POST /tasks/{task_id}/resume` 恢复。
- **MCP**：`publish_article` / `update_article` / `sync_pending` 同步执行，直接返回各平台结果行。
- 旧 `/runs`、`/publish/workflow`、`/login/status`、`/assist/status` 端点已删除（404），前端已全部切到 `/tasks`。

### 数据层

- `meta.schema_version` + `MIGRATIONS` 增量迁移（v2: publications.content_hash）。
- publications.content_hash：更新前比对内容指纹，内容没变不空发。
