# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。所有值得记录的变更都会列在这里。

## [Unreleased]

### 变更
- **后端结构性重构**：后端迁入 `backed/`（FastAPI 分层：`api` / `service` / `repository` / `models` / `schemas` / `middleware` / `utils`），
  原顶层 `cli.py` / `core/` / `server/` 移除；CLI 重写于 `backed/cli.py`，发布引擎迁至 `backed/service/publishing/`，
  原 REST 业务端点（发布 / 原地更新 / 同步 / AI / 账号）全部保留（`backed/api/hub.py`），
  新增 `/api/v1` 统一 CRUD 资源接口（article / publication / account / job / task）与单元/集成测试骨架。
- 新增 `deplay/` 部署编排（docker-compose / Dockerfile / nginx）与 `AGENT.md` 开发规范；
  本地启动脚本 `start.sh` / `start.bat` / `start.ps1`（仅依赖 uv）。
- Web 管理界面改为按需挂载：`web/` 构建产物落在 `server/static/` 后由后端在根路径提供，
  构建产物不再随仓库提交。

### 修复
- 补回迁移遗漏的 `core/human_click.py`（知乎标签点选依赖），移除未渲染的脚手架模板文件 `core/dependencies.py`。
- 补齐 `api.get_router_info`（`/api/info` 调试接口此前会 500），健康检查品牌名与 `.env.example` 项目名修正。
- 清理误提交的运行时日志（`backed/logs/`、`backed/database/data/observability/`），并补充 `.gitignore`。

## [0.3.0] - 2026-09-25

### 新增
- **51CTO 适配器**：MetaWeblog 账号密码免扫码直发（平台池扩至 10 个）
- **前端「晴空」主题**：暗黑文学风 → 明亮 SaaS 风（飞书蓝主色、白卡片、浅灰底、无衬线），全链路 0 外部请求保持离线可用
- 登录态持久化闭环（登录 → auth.json 快照 → check_auth 恢复 → 发布）经真实账号验证

### 修复
- 掘金：`home_url` 改首页（创作中心被数据中心 IP 风控），发布 goto 容错——改为纯 API 路径，**真发草稿成功**
- CSDN：`check_auth` 假阳性修复（不再导航登录页、列表非空才算登录）
- 知乎：`check_auth` 改为纯 API 判定（`/api/v4/me` 校验）
- config.json 清理无效凭据（避免误用残留测试值）

### 变更
- 简书平台从代码与前端完全移除
- 文档：README 更新至 10 平台、新主题截图、真实发布实测记录

## [0.2.0] - 2026-09-24

### 新增
- Web 管理界面（写作 / 管理双视图，响应式三栏适配）
- 发布面板：平台分类记忆（设置持久化，下次自动带出）
- 合规门禁：AI 内容必须先 `draft_only` 草稿、人工确认后才能上线

### 修复
- 掘金 tag 解析增强（兼容 tag_name/name、tag_id/id 双字段，过滤异常 ID）
- 浏览器实例池（LRU 上限 4），扫码登录前自动释放池实例避免 profile 锁冲突
- SQLite WAL 模式 + busy_timeout，消除并发写锁

## [0.1.0] - 2026-09-23

### 首个可用版本
- 核心架构：任务引擎 + 适配器模式 + 浏览器实例池
- 平台适配器：掘金 / CSDN / 博客园 / 知乎 / 思否 / B站 / 头条 / 开源中国 / 自建博客
- 内置浏览器（patchright 反检测）：8 项指纹伪装 + 登录态持久化 + 验证码三层策略
- MCP Server（13 工具）+ REST API（25 端点）
- AI 写稿：标题抽取、摘要、标签、改写、润色（OpenAI 兼容协议）
- E2E 测试套件：本地 mock 平台 + 全程截图留证
