# AGENT.md

面向 AI 编程助手的项目说明：本仓库是一个 **AI 内容中台**，后端采用 FastAPI，按「资源驱动」分层架构自动生成。

---

## 1. 目录结构（根）

```
.
├── backed/            # 后端（FastAPI），主要开发目录
├── deplay/            # 部署编排（docker-compose / Dockerfile / 运维配置）
├── docs/              # 产品 / 架构文档
├── web/               # 前端（Vue3 + Vite）
├── start.sh / start.bat / start.ps1   # 本地启动脚本（仅依赖 uv）
├── README.md          # 项目说明
└── AGENT.md           # 本文件
```

> 根目录只保留上述目录与文件；旧版 `core/`、`server/`、`tests/`、`scripts/` 已被移除。

---

## 2. 后端 `backed/` 分层

```
backed/
├── start.py            # 入口：uvicorn start:app
├── app/               # 应用装配（factory / config / middleware / routes / exceptions）
├── api/v1/<资源>/      # Resource 层：路由 + 请求校验 + 调用 Service
├── service/           # 业务逻辑层（*Service）
├── repository/        # 数据访问层（*Repository）
├── models/            # ORM 模型（SQLAlchemy）
├── schemas/           # Pydantic 模型（请求/响应）
├── config/            # 多环境配置（config_unified + factory）
├── core/              # 基础设施：database / cache / queue / security / permissions
├── middleware/        # 速率限制 / 审计 / 安全头
├── utils/             # 通用工具：logger / auth / custom_exceptions / audit
└── tests/             # 单元 + 集成测试
```

### 数据流

```
HTTP → api/v1/<resource>Resource → <Resource>Service → <Resource>Repository → SQLAlchemy Session
```

依赖注入（FastAPI `Depends`）：
- 路由层只依赖 `service`（通过 `from service import get_<resource>_service` 注入）。
- `service/__init__.py` 内集中定义 `get_*_service` 工厂（注入 `AsyncSession`）。
- `repository` 通过 `core.database.get_async_session` 获取会话。
- **不要在 Resource 层直接注入 Repository。**

---

## 3. 资源约定（务必遵守）

每个业务表 = 一组文件，命名以 **单数表名** 为前缀：

| 层 | 文件 | 关键类 |
|----|------|--------|
| Model | `models/<singular>.py` | `<Class>`（继承 `BaseModel` + `TimestampMixin`） |
| Schema | `schemas/<singular>.py` | `<Class>Create / Update / StatusUpdate / Response` |
| Repo | `repository/<singular>_repository.py` | `<Class>Repository` |
| Service | `service/<singular>_service.py` | `<Class>Service` |
| Resource | `api/v1/<singular>/<singular>Resource.py` | `<Class>Resource`（含 `router`） |

RESTful 端点（前缀 `/api/v1/<singular>`，由 `api/v1/__init__.py` 聚合）：

- `GET    /`                 列表（分页 `?page=&size=`，返回 `PaginationResponse`）
- `POST   /`                 创建（201，`SuccessResponse`）
- `GET    /{id}`             详情（404 当不存在）
- `PUT    /{id}`             全量更新
- `DELETE /{id}`             **物理删除**（默认，返回 204）
- `PATCH  /{id}/status`      仅更新枚举状态字段（`*StatusUpdate` schema）
- `POST   /{id}/restore`     仅当 `soft_delete=True` 时启用（本项目默认物理删除，未启用）

### 响应信封

所有业务接口统一返回：

- 成功：`SuccessResponse[T]`（`success=true, code=200, message, data`）
- 列表：`PaginationResponse[T]`（`data.items / data.total / meta`）
- 异常：`appschemas/response.py` 中的 `error_response` + `utils.custom_exceptions`

### 状态字段约定

- 状态字段以枚举约束（如 `article.status` ∈ `draft/published/archived`）。
- 创建时**不**传状态（使用 DB 默认值）；状态变更走 `PATCH /{id}/status`。
- `Update` schema 中状态字段被排除（避免全量更新误改状态）。

---

## 4. 数据库

- **默认 SQLite**（`sqlite+aiosqlite:///./data/hub.db`），本地零依赖即可启动。
- 生产可切 MySQL：设置 `DATABASE_URL=mysql+aiomysql://...`。
- 应用启动时（`app/factory.py` lifespan）自动 `Base.metadata.create_all` 建表（无迁移文件，轻量）。
- 表名使用**单数**（与 `core/database.Base` 元数据同源，便于 `create_all`）。

---

## 5. 认证

`core/permissions.get_current_active_user`：
- 单用户 / 自托管场景，**默认不做强制登录**。
- 若 `config` 中设置 `api_token`，则要求请求头 `X-API-Token` 与之匹配。
- 多用户 / SSO 场景可后续引入用户模型与 JWT 替换本模块。

---

## 6. 配置与环境

- 唯一配置源：`config/config_unified.py`（`BaseConfig` + 各环境子类），通过 `config/__init__.py` 导出 `settings`。
- 选择环境：`FASTAPI_ENV` ∈ `development / testing / docker / staging / production`。
- 读取方式：`from config import settings`（扁平字段，如 `settings.database_url`）。
- 敏感配置走环境变量 / `.env`（`config/__init__.py` 已对非法布尔环境变量做清理，避免 pydantic 校验失败）。

---

## 7. 本地运行

```bash
# 方式一：启动脚本（无语言依赖，仅依赖 uv）
./start.sh          # Linux / macOS
start.bat           # Windows cmd
start.ps1           # PowerShell

# 方式二：直接 uv
cd backed
uv sync
uv run uvicorn start:app --host 0.0.0.0 --port 8000 --reload
```

访问：http://localhost:8000/docs

---

## 8. 测试

```bash
cd backed
uv run pytest -q
```

- `tests/unit/`：各层单测（部分占位，标记 `skip`）。
- `tests/integration/api/v1/`：端到端 CRUD（使用 SQLite 测试库，由 `tests/conftest.py` 建表）。

---

## 9. 新增一个业务表（扩展示例）

代码由 `sql-to-fastapi-restfulapi-scaffold` 技能模板驱动，生成器位于 `backed/_gen.py`：

1. 在 `_gen.py` 的 `TABLES` 中追加一个表定义（字段、类型、约束、状态字段、示例值）。
2. 执行 `uv run --with jinja2 python _gen.py` 生成 model/schema/repository/service/resource/tests。
3. 在 `service/__init__.py` 追加 `get_<singular>_service` 工厂。
4. 在 `api/v1/__init__.py` 注册 `include_router(<singular>_router)`，`models/__init__.py` 追加模型导入。
5. `uv run pytest` 验证。

> 表名保持单数；状态字段统一走 `PATCH /status`；物理删除默认开启。

---

## 10. 部署

见 `deplay/`：

```bash
cd deplay
cp .env.example .env
docker compose up -d --build                # 后端 + MySQL + Redis
docker compose --profile web up -d --build  # 含前端（nginx 反代 /api）
```

---

## 11. 注意事项 / 坑

- **不要**在 `core/__init__.py` 再放服务工厂（已统一到 `service/__init__.py`）。
- **不要**新增第二套 `settings.py`；统一用 `config.settings`。
- 集成测试依赖 `tests/conftest.py` 在 session 级建表；新增表后需在 `models/__init__.py` 导出，否则 `create_all` 不会建该表。
- 日志写入 `backed/logs/` 与 `backed/logs/audit/`，目录需存在（已建，且被 `.gitignore` 忽略）。
