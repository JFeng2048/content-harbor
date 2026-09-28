#!/bin/bash

# =============================================================================
# FastAPI安全教学项目 - Docker构建和部署脚本
# =============================================================================

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 输出函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查Docker是否安装
check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker未安装，请先安装Docker"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose未安装，请先安装Docker Compose"
        exit 1
    fi
    
    log_success "Docker环境检查通过"
}

# 检查环境变量文件
check_env_file() {
    if [ ! -f ".env" ]; then
        if [ -f ".env.docker" ]; then
            log_warning ".env文件不存在，从.env.docker复制"
            cp ..venv.docker ..venv
        else
            log_error ".env文件不存在，请先创建配置文件"
            exit 1
        fi
    fi
    log_success "环境配置文件检查通过"
}

# 构建镜像
build_images() {
    local target=${1:-production}
    
    log_info "开始构建Docker镜像 (target: $target)"
    
    docker build \
        --target $target \
        --tag fastapi-security:$target \
        --tag fastapi-security:latest \
        .
    
    log_success "镜像构建完成"
}

# 开发环境部署
deploy_development() {
    log_info "启动开发环境..."
    
    # 构建开发镜像
    build_images development
    
    # 启动开发环境
    docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
    
    log_success "开发环境启动完成"
    log_info "应用访问地址: http://localhost:8000"
    log_info "API文档地址: http://localhost:8000/docs"
    log_info "数据库管理: http://localhost:8080"
    log_info "Redis管理: http://localhost:8081"
}

# 生产环境部署
deploy_production() {
    log_info "启动生产环境..."
    
    # 构建生产镜像
    build_images production
    
    # 启动生产环境
    docker-compose -f docker-compose.yml -f docker-compose.prod.yml --profile production --profile monitoring up -d
    
    log_success "生产环境启动完成"
    log_info "应用访问地址: https://localhost"
    log_info "监控地址: http://localhost:3000 (Grafana)"
    log_info "指标地址: http://localhost:9090 (Prometheus)"
}

# 停止服务
stop_services() {
    local .venv=${1:-all}
    
    log_info "停止服务 (环境: $env)"
    
    case $env in
        dev|development)
            docker-compose -f docker-compose.yml -f docker-compose.dev.yml down
            ;;
        prod|production)
            docker-compose -f docker-compose.yml -f docker-compose.prod.yml down
            ;;
        all)
            docker-compose down
            docker-compose -f docker-compose.yml -f docker-compose.dev.yml down
            docker-compose -f docker-compose.yml -f docker-compose.prod.yml down
            ;;
    esac
    
    log_success "服务已停止"
}

# 清理资源
cleanup() {
    log_info "清理Docker资源..."
    
    # 停止所有服务
    stop_services all
    
    # 删除镜像
    docker rmi fastapi-security:latest fastapi-security:development fastapi-security:production 2>/dev/null || true
    
    # 清理未使用的资源
    docker system prune -f
    
    log_success "清理完成"
}

# 查看日志
view_logs() {
    local service=${1:-fastapi-app}
    local .venv=${2:-development}
    
    log_info "查看服务日志: $service"
    
    case $env in
        dev|development)
            docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs -f $service
            ;;
        prod|production)
            docker-compose -f docker-compose.yml -f docker-compose.prod.yml logs -f $service
            ;;
        *)
            docker-compose logs -f $service
            ;;
    esac
}

# 执行数据库迁移
run_migrations() {
    log_info "执行数据库迁移..."
    
    docker-compose exec fastapi-app python -c "
from core.database import engine
from models import Base
Base.metadata.create_all(bind=engine)
print('数据库迁移完成')
"
    
    log_success "数据库迁移完成"
}

# 运行测试
run_tests() {
    log_info "运行测试..."
    
    docker-compose run --rm fastapi-app python -m pytest tests/ -v --cov=.
    
    log_success "测试完成"
}

# 健康检查
health_check() {
    log_info "执行健康检查..."
    
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if curl -f http://localhost:8000/health >/dev/null 2>&1; then
            log_success "应用健康检查通过"
            return 0
        fi
        
        log_info "等待应用启动... ($attempt/$max_attempts)"
        sleep 2
        attempt=$((attempt + 1))
    done
    
    log_error "应用健康检查失败"
    return 1
}

# 备份数据
backup_data() {
    local backup_dir="./backups/$(date +%Y%m%d_%H%M%S)"
    
    log_info "创建数据备份..."
    mkdir -p "$backup_dir"
    
    # 备份数据库
    docker-compose exec mysql mysqldump -u root -p\$MYSQL_ROOT_PASSWORD fastapi_security > "$backup_dir/database.sql"
    
    # 备份Redis数据
    docker-compose exec redis redis-cli --rdb "$backup_dir/redis.rdb"
    
    # 备份应用日志
    cp -r logs "$backup_dir/" 2>/dev/null || true
    
    log_success "数据备份完成: $backup_dir"
}

# 显示帮助信息
show_help() {
    echo "FastAPI安全教学项目 - Docker部署脚本"
    echo ""
    echo "用法: $0 [命令] [参数]"
    echo ""
    echo "命令:"
    echo "  build [target]          构建Docker镜像 (development|production)"
    echo "  dev                     启动开发环境"
    echo "  prod                    启动生产环境"
    echo "  stop [env]              停止服务 (dev|prod|all)"
    echo "  restart [env]           重启服务"
    echo "  logs [service] [env]    查看服务日志"
    echo "  migrate                 执行数据库迁移"
    echo "  test                    运行测试"
    echo "  health                  健康检查"
    echo "  backup                  备份数据"
    echo "  cleanup                 清理Docker资源"
    echo "  help                    显示帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 dev                  # 启动开发环境"
    echo "  $0 prod                 # 启动生产环境"
    echo "  $0 logs fastapi-app dev # 查看开发环境应用日志"
    echo "  $0 stop prod            # 停止生产环境"
}

# 主函数
main() {
    local command=${1:-help}
    
    # 基础检查
    check_docker
    
    case $command in
        build)
            check_env_file
            build_images ${2:-production}
            ;;
        dev|development)
            check_env_file
            deploy_development
            health_check
            ;;
        prod|production)
            check_env_file
            deploy_production
            health_check
            ;;
        stop)
            stop_services ${2:-all}
            ;;
        restart)
            stop_services ${2:-all}
            sleep 2
            if [ "${2:-all}" = "dev" ] || [ "${2:-all}" = "development" ]; then
                deploy_development
            elif [ "${2:-all}" = "prod" ] || [ "${2:-all}" = "production" ]; then
                deploy_production
            else
                deploy_development
            fi
            ;;
        logs)
            view_logs ${2:-fastapi-app} ${3:-development}
            ;;
        migrate)
            run_migrations
            ;;
        test)
            run_tests
            ;;
        health)
            health_check
            ;;
        backup)
            backup_data
            ;;
        cleanup)
            cleanup
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            log_error "未知命令: $command"
            show_help
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"
