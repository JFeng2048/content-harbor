# =============================================================================
# FastAPI安全教学项目 - 增强版Docker部署脚本 (PowerShell版)
# 支持监控、性能测试、安全扫描等完整功能栈
# =============================================================================

param(
    [Parameter(Position=0)]
    [string]$Command = "help",
    
    [Parameter(Position=1)]
    [string]$Parameter1 = "",
    
    [Parameter(Position=2)]
    [string]$Parameter2 = "",
    
    [Parameter(Position=3)]
    [string]$Parameter3 = ""
)

# 颜色输出函数
function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Blue
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

# 检查Docker环境
function Test-DockerEnvironment {
    Write-Info "检查Docker环境..."
    
    try {
        $dockerVersion = docker --version
        Write-Success "Docker已安装: $dockerVersion"
    }
    catch {
        Write-Error "Docker未安装，请先安装Docker Desktop"
        exit 1
    }
    
    try {
        $composeVersion = docker-compose --version
        Write-Success "Docker Compose已安装: $composeVersion"
    }
    catch {
        Write-Error "Docker Compose未安装"
        exit 1
    }
    
    Write-Success "Docker环境检查通过"
}

# 检查环境配置文件
function Test-EnvironmentFile {
    Write-Info "检查环境配置文件..."
    
    if (-not (Test-Path ".env")) {
        if (Test-Path ".env.docker") {
            Write-Warning ".env文件不存在，从.env.docker复制"
            Copy-Item ".env.docker" ".env"
        }
        else {
            Write-Error ".env文件不存在，请先创建配置文件"
            exit 1
        }
    }
    
    Write-Success "环境配置文件检查通过"
}

# 构建Docker镜像
function Build-DockerImages {
    param([string]$Target = "production")
    
    Write-Info "开始构建Docker镜像 (target: $Target)"
    
    try {
        docker build --target $Target --tag "fastapi-security:$Target" --tag "fastapi-security:latest" .
        Write-Success "镜像构建完成"
    }
    catch {
        Write-Error "镜像构建失败: $_"
        exit 1
    }
}

# 启动开发环境
function Start-DevelopmentEnvironment {
    Write-Info "启动开发环境..."
    
    Build-DockerImages "development"
    
    try {
        docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
        Write-Success "开发环境启动完成"
        Write-Info "应用访问地址: http://localhost:8000"
        Write-Info "API文档地址: http://localhost:8000/docs"
        Write-Info "数据库管理: http://localhost:8080"
        Write-Info "Redis管理: http://localhost:8081"
    }
    catch {
        Write-Error "开发环境启动失败: $_"
        exit 1
    }
}

# 启动生产环境
function Start-ProductionEnvironment {
    Write-Info "启动生产环境..."
    
    Build-DockerImages "production"
    
    try {
        docker-compose -f docker-compose.yml -f docker-compose.prod.yml --profile production --profile monitoring up -d
        Write-Success "生产环境启动完成"
        Write-Info "应用访问地址: https://localhost"
        Write-Info "监控地址: http://localhost:3000 (Grafana)"
        Write-Info "指标地址: http://localhost:9090 (Prometheus)"
    }
    catch {
        Write-Error "生产环境启动失败: $_"
        exit 1
    }
}

# 启动监控栈
function Start-MonitoringStack {
    Write-Info "启动完整监控栈..."
    docker-compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
    
    if ($LASTEXITCODE -eq 0) {
        Write-Success "监控栈启动成功!"
        Write-Info "访问地址:"
        Write-Info "- Grafana: http://localhost:3000 (admin/admin123)"
        Write-Info "- Prometheus: http://localhost:9090"
        Write-Info "- Kibana: http://localhost:5601"
        Write-Info "- Jaeger: http://localhost:16686"
        Write-Info "- cAdvisor: http://localhost:8080"
    } else {
        Write-Error "监控栈启动失败"
        exit 1
    }
}

# 运行性能测试
function Start-PerformanceTest {
    param(
        [string]$Tool = "k6"
    )
    
    Write-Info "运行性能测试 ($Tool)..."
    
    # 确保测试目录存在
    $testDir = "tests/performance"
    if (!(Test-Path $testDir)) {
        New-Item -ItemType Directory -Path $testDir -Force
        Write-Info "创建性能测试目录: $testDir"
    }
    
    switch ($Tool.ToLower()) {
        "k6" {
            docker-compose -f docker-compose.yml -f docker-compose.performance.yml run --rm k6
        }
        "artillery" {
            docker-compose -f docker-compose.yml -f docker-compose.performance.yml run --rm artillery
        }
        "jmeter" {
            docker-compose -f docker-compose.yml -f docker-compose.performance.yml run --rm jmeter
        }
        default {
            Write-Error "不支持的性能测试工具: $Tool"
            Write-Info "支持的工具: k6, artillery, jmeter"
            exit 1
        }
    }
    
    if ($LASTEXITCODE -eq 0) {
        Write-Success "性能测试完成！结果保存在 $testDir/results/"
    } else {
        Write-Error "性能测试失败"
        exit 1
    }
}

# 运行安全扫描
function Start-SecurityScan {
    param(
        [string]$Tool = "all"
    )
    
    Write-Info "运行安全扫描 ($Tool)..."
    
    # 确保测试目录存在
    $testDir = "tests/security"
    if (!(Test-Path $testDir)) {
        New-Item -ItemType Directory -Path $testDir -Force
        Write-Info "创建安全测试目录: $testDir"
    }
    
    # 创建各工具的结果目录
    $tools = @("zap", "trivy", "bandit", "safety", "snyk", "nuclei", "sqlmap", "docker-bench")
    foreach ($toolName in $tools) {
        $toolDir = "$testDir/$toolName"
        if (!(Test-Path $toolDir)) {
            New-Item -ItemType Directory -Path $toolDir -Force
        }
    }
    
    if ($Tool.ToLower() -eq "all") {
        Write-Info "运行所有安全扫描工具..."
        docker-compose -f docker-compose.yml -f docker-compose.security.yml --profile security up --abort-on-container-exit
    } else {
        switch ($Tool.ToLower()) {
            "zap" {
                docker-compose -f docker-compose.yml -f docker-compose.security.yml run --rm zap
            }
            "trivy" {
                docker-compose -f docker-compose.yml -f docker-compose.security.yml run --rm trivy
            }
            "bandit" {
                docker-compose -f docker-compose.yml -f docker-compose.security.yml run --rm bandit
            }
            "safety" {
                docker-compose -f docker-compose.yml -f docker-compose.security.yml run --rm safety
            }
            "nuclei" {
                docker-compose -f docker-compose.yml -f docker-compose.security.yml run --rm nuclei
            }
            default {
                Write-Error "不支持的安全扫描工具: $Tool"
                Write-Info "支持的工具: all, zap, trivy, bandit, safety, nuclei"
                exit 1
            }
        }
    }
    
    if ($LASTEXITCODE -eq 0) {
        Write-Success "安全扫描完成！结果保存在 $testDir/"
    } else {
        Write-Error "安全扫描失败"
        exit 1
    }
}

# 生成安全报告摘要
function Get-SecurityReport {
    Write-Info "生成安全报告摘要..."
    
    $reportDir = "tests/security"
    $summaryFile = "$reportDir/security-summary.txt"
    
    "=============================================================================`n" | Out-File -FilePath $summaryFile -Encoding UTF8
    "FastAPI安全教学项目 - 安全扫描报告摘要`n" | Out-File -FilePath $summaryFile -Append -Encoding UTF8
    "生成时间: $(Get-Date)`n" | Out-File -FilePath $summaryFile -Append -Encoding UTF8
    "=============================================================================`n" | Out-File -FilePath $summaryFile -Append -Encoding UTF8
    
    # 检查各工具的报告文件
    $tools = @{
        "OWASP ZAP" = "$reportDir/zap/zap-report.json"
        "Trivy" = "$reportDir/trivy/trivy-report.json"
        "Bandit" = "$reportDir/bandit/bandit-report.json"
        "Safety" = "$reportDir/safety/safety-report.json"
        "Nuclei" = "$reportDir/nuclei/nuclei-report.json"
    }
    
    foreach ($tool in $tools.GetEnumerator()) {
        "[$($tool.Key)]`n" | Out-File -FilePath $summaryFile -Append -Encoding UTF8
        if (Test-Path $tool.Value) {
            "报告文件: $($tool.Value)`n" | Out-File -FilePath $summaryFile -Append -Encoding UTF8
            $fileSize = (Get-Item $tool.Value).Length
            "文件大小: $fileSize 字节`n" | Out-File -FilePath $summaryFile -Append -Encoding UTF8
        } else {
            "报告文件: 未找到`n" | Out-File -FilePath $summaryFile -Append -Encoding UTF8
        }
        "`n" | Out-File -FilePath $summaryFile -Append -Encoding UTF8
    }
    
    Write-Success "安全报告摘要已生成: $summaryFile"
}

# 清理测试数据
function Clear-TestData {
    Write-Info "清理测试数据..."
    
    $testDirs = @("tests/performance/results", "tests/security")
    
    foreach ($dir in $testDirs) {
        if (Test-Path $dir) {
            Remove-Item -Path $dir -Recurse -Force
            Write-Success "已清理: $dir"
        }
    }
}

# 健康检查增强版
function Test-SystemHealth {
    Write-Info "执行系统健康检查..."
    
    # 检查容器状态
    $containers = docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    Write-Info "容器状态:"
    Write-Host $containers
    
    # 检查服务端点
    $endpoints = @{
        "FastAPI应用" = "http://localhost:8000/health"
        "Grafana" = "http://localhost:3000/api/health"
        "Prometheus" = "http://localhost:9090/-/healthy"
        "Kibana" = "http://localhost:5601/api/status"
    }
      Write-Info "`n服务端点检查:"
    foreach ($endpoint in $endpoints.GetEnumerator()) {
        try {
            Invoke-RestMethod -Uri $endpoint.Value -TimeoutSec 5 -ErrorAction SilentlyContinue | Out-Null
            Write-Success "$($endpoint.Key): ✓ 正常"
        } catch {
            Write-Warning "$($endpoint.Key): ✗ 异常或未启动"
        }
    }
    
    # 检查资源使用情况
    Write-Info "`n资源使用情况:"
    docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}"
}

# 停止服务
function Stop-Services {
    param([string]$Environment = "all")
    
    Write-Info "停止服务 (环境: $Environment)"
    
    try {
        switch ($Environment) {
            { $_ -in "dev", "development" } {
                docker-compose -f docker-compose.yml -f docker-compose.dev.yml down
            }
            { $_ -in "prod", "production" } {
                docker-compose -f docker-compose.yml -f docker-compose.prod.yml down
            }
            "all" {
                docker-compose down
                docker-compose -f docker-compose.yml -f docker-compose.dev.yml down
                docker-compose -f docker-compose.yml -f docker-compose.prod.yml down
            }
        }
        Write-Success "服务已停止"
    }
    catch {
        Write-Error "停止服务失败: $_"
    }
}

# 查看日志
function Show-ServiceLogs {
    param(
        [string]$Service = "fastapi-app",
        [string]$Environment = "development"
    )
    
    Write-Info "查看服务日志: $Service"
    
    try {
        switch ($Environment) {
            { $_ -in "dev", "development" } {
                docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs -f $Service
            }
            { $_ -in "prod", "production" } {
                docker-compose -f docker-compose.yml -f docker-compose.prod.yml logs -f $Service
            }
            default {
                docker-compose logs -f $Service
            }
        }
    }
    catch {
        Write-Error "查看日志失败: $_"
    }
}

# 健康检查
function Test-ApplicationHealth {
    Write-Info "执行健康检查..."
    
    $maxAttempts = 30
    $attempt = 1
    
    while ($attempt -le $maxAttempts) {
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -eq 200) {
                Write-Success "应用健康检查通过"
                return $true
            }
        }
        catch {
            # 忽略错误，继续尝试
        }
        
        Write-Info "等待应用启动... ($attempt/$maxAttempts)"
        Start-Sleep -Seconds 2
        $attempt++
    }
    
    Write-Error "应用健康检查失败"
    return $false
}

# 运行测试
function Invoke-Tests {
    Write-Info "运行测试..."
    
    try {
        docker-compose run --rm fastapi-app python -m pytest tests/ -v --cov=.
        Write-Success "测试完成"
    }
    catch {
        Write-Error "测试失败: $_"
    }
}

# 清理资源
function Clear-DockerResources {
    Write-Info "清理Docker资源..."
    
    try {
        Stop-Services "all"
        
        # 删除镜像
        docker rmi fastapi-security:latest fastapi-security:development fastapi-security:production 2>$null
        
        # 清理未使用的资源
        docker system prune -f
        
        Write-Success "清理完成"
    }
    catch {
        Write-Error "清理失败: $_"
    }
}

# 备份数据
function Backup-ApplicationData {
    $backupDir = "./backups/$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    
    Write-Info "创建数据备份..."
    
    try {
        New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
        
        # 备份数据库
        docker-compose exec mysql mysqldump -u root -p$env:MYSQL_ROOT_PASSWORD fastapi_security > "$backupDir/database.sql"
        
        # 备份应用日志
        if (Test-Path "logs") {
            Copy-Item "logs" "$backupDir/" -Recurse
        }
        
        Write-Success "数据备份完成: $backupDir"
    }
    catch {
        Write-Error "备份失败: $_"
    }
}

# 显示帮助信息
function Show-Help {
    Write-Host "FastAPI安全教学项目 - 增强版Docker部署脚本 (PowerShell版)" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "用法: .\deploy\docker-deploy.ps1 [命令] [参数]" -ForegroundColor White
    Write-Host ""
    Write-Host "基础命令:" -ForegroundColor Green
    Write-Host "  build [target]          构建Docker镜像 (development|production)" -ForegroundColor Gray
    Write-Host "  dev                     启动开发环境" -ForegroundColor Gray
    Write-Host "  prod                    启动生产环境" -ForegroundColor Gray
    Write-Host "  stop [env]              停止服务 (dev|prod|all)" -ForegroundColor Gray
    Write-Host "  restart [env]           重启服务" -ForegroundColor Gray
    Write-Host "  logs [service] [env]    查看服务日志" -ForegroundColor Gray
    Write-Host ""
    Write-Host "监控和测试:" -ForegroundColor Green
    Write-Host "  monitoring              启动完整监控栈 (Prometheus+Grafana+ELK+Jaeger)" -ForegroundColor Gray
    Write-Host "  performance [tool]      运行性能测试 (k6|artillery|jmeter)" -ForegroundColor Gray
    Write-Host "  security [tool]         运行安全扫描 (all|zap|trivy|bandit|safety|nuclei)" -ForegroundColor Gray
    Write-Host "  security-report         生成安全报告摘要" -ForegroundColor Gray
    Write-Host "  health                  系统健康检查" -ForegroundColor Gray
    Write-Host ""
    Write-Host "维护命令:" -ForegroundColor Green
    Write-Host "  test                    运行单元测试" -ForegroundColor Gray
    Write-Host "  backup                  备份数据" -ForegroundColor Gray
    Write-Host "  cleanup                 清理Docker资源" -ForegroundColor Gray
    Write-Host "  clean-test              清理测试数据" -ForegroundColor Gray
    Write-Host "  help                    显示帮助信息" -ForegroundColor Gray
    Write-Host ""
    Write-Host "示例:" -ForegroundColor White
    Write-Host "  .\deploy\docker-deploy.ps1 dev                    # 启动开发环境" -ForegroundColor Yellow
    Write-Host "  .\deploy\docker-deploy.ps1 monitoring             # 启动监控栈" -ForegroundColor Yellow
    Write-Host "  .\deploy\docker-deploy.ps1 performance k6         # 使用K6进行性能测试" -ForegroundColor Yellow
    Write-Host "  .\deploy\docker-deploy.ps1 security all           # 运行所有安全扫描" -ForegroundColor Yellow
    Write-Host "  .\deploy\docker-deploy.ps1 logs fastapi-app dev   # 查看开发环境应用日志" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "监控访问地址:" -ForegroundColor White
    Write-Host "  - FastAPI应用: http://localhost:8000" -ForegroundColor Cyan
    Write-Host "  - Grafana: http://localhost:3000 (admin/admin123)" -ForegroundColor Cyan
    Write-Host "  - Prometheus: http://localhost:9090" -ForegroundColor Cyan
    Write-Host "  - Kibana: http://localhost:5601" -ForegroundColor Cyan
    Write-Host "  - Jaeger: http://localhost:16686" -ForegroundColor Cyan
}

# 主执行逻辑
function Main {
    # 基础检查
    Test-DockerEnvironment
    
    switch ($Command.ToLower()) {
        "build" {
            Test-EnvironmentFile
            Build-DockerImages $(if ($Parameter1) { $Parameter1 } else { "production" })
        }
        { $_ -in "dev", "development" } {
            Test-EnvironmentFile
            Start-DevelopmentEnvironment
            Test-ApplicationHealth
        }
        { $_ -in "prod", "production" } {
            Test-EnvironmentFile
            Start-ProductionEnvironment
            Test-ApplicationHealth
        }
        "monitoring" {
            Test-EnvironmentFile
            Start-MonitoringStack
        }
        "performance" {
            Test-EnvironmentFile
            $tool = if ($Parameter1) { $Parameter1 } else { "k6" }
            Start-PerformanceTest $tool
        }
        "security" {
            Test-EnvironmentFile
            $tool = if ($Parameter1) { $Parameter1 } else { "all" }
            Start-SecurityScan $tool
        }
        "security-report" {
            Get-SecurityReport
        }
        "stop" {
            Stop-Services $(if ($Parameter1) { $Parameter1 } else { "all" })
        }
        "restart" {
            $env = if ($Parameter1) { $Parameter1 } else { "all" }
            Stop-Services $env
            Start-Sleep -Seconds 2
            if ($env -in "dev", "development") {
                Start-DevelopmentEnvironment
            }
            elseif ($env -in "prod", "production") {
                Start-ProductionEnvironment
            }
            else {
                Start-DevelopmentEnvironment
            }
        }
        "logs" {
            $service = if ($Parameter1) { $Parameter1 } else { "fastapi-app" }
            $env = if ($Parameter2) { $Parameter2 } else { "development" }
            Show-ServiceLogs $service $env
        }
        "test" {
            Invoke-Tests
        }
        "health" {
            Test-SystemHealth
        }
        "backup" {
            Backup-ApplicationData
        }
        "cleanup" {
            Clear-DockerResources
        }
        "clean-test" {
            Clear-TestData
        }
        { $_ -in "help", "--help", "-h" } {
            Show-Help
        }
        default {
            Write-Error "未知命令: $Command"
            Show-Help
            exit 1
        }
    }
}

# 执行主函数
Main
