# 部署（deplay）

本目录包含 AI 内容中台的部署编排与运维配置。

## 目录结构

- `docker-compose.yml` —— 服务编排：backend / mysql / redis（web 为可选 profile）
- `Dockerfile` —— 后端镜像（基于 uv 管理依赖）
- `Dockerfile.web` —— 前端镜像（node 构建 + nginx 反代 `/api`）
- `.env.example` —— 部署环境变量示例（复制为 `.env` 使用）
- `nginx.conf` / `nginx-prod.conf` —— 反向代理示例
- `mysql.cnf` / `mysql-prod.cnf`、`redis.conf` —— 数据库配置
- `prometheus.yml`、`alert_rules.yml`、`grafana/`、`logstash/` —— 监控与日志

## 快速启动

```bash
cd deplay
cp .env.example .env
docker compose up -d --build                 # 后端 + 依赖
docker compose --profile web up -d --build    # 含前端
```

访问：

- 后端 API 文档：http://localhost:8000/docs
- 前端（启用 web 时）：http://localhost:3000

## 仅本地运行（无需 Docker）

在项目根目录执行对应脚本：

```bash
./start.sh      # Linux / macOS
start.bat       # Windows cmd
start.ps1       # PowerShell
```
