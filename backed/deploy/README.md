# deploy（进阶运维配置 · 基线）

本目录随脚手架一并复制，供生产/教学演示使用，**不是**起步 `docker compose` 的必跑依赖。

| 内容 | 作用 |
|------|------|
| `nginx.conf` / `nginx-prod.conf` | 反向代理、限流、TLS 示例 |
| `mysql.cnf` / `mysql-prod.cnf` | MySQL 调优 |
| `redis.conf` | Redis 内存与持久化 |
| `prometheus.yml` / `alert_rules.yml` | 监控与告警 |
| `grafana/provisioning/` | Grafana 数据源自动配置 |
| `logstash/` | 日志采集管道（ELK） |
| `supervisor.conf` | 非容器场景进程守护 |
| `docker-deploy.sh` / `.ps1` | 历史一键脚本（可能引用旧 compose 文件名，使用前请对照当前 `docker/docker-compose.yml`） |

日常起步请优先：`docker compose -f docker/docker-compose.yml up --build`。
