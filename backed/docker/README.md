# Docker（项目基线 BASELINE）

空项目首次脚手架时从本目录完整复制到目标项目 `docker/`。

| 文件 | 说明 |
|------|------|
| `Dockerfile` | 应用镜像（多阶段） |
| `docker-compose.yml` | **app + MySQL**；**Redis** 为 `--profile redis` 可选项 |

启动（在目标项目根目录）：

```bash
docker compose -f docker/docker-compose.yml up --build
REDIS_HOST=redis docker compose -f docker/docker-compose.yml --profile redis up --build
```

说明：
- MySQL 初始化脚本默认挂载 `database/` 下的 SQL dump（见 compose 内路径）。
- 若目标项目尚无 dump：将用户 SQL 导出为对应文件，或暂时注释该 volume。
- 进阶 Nginx / 监控 / 日志配置见同级骨架中的 `deploy/`（非默认 compose 栈）。
