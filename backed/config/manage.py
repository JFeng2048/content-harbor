#!/usr/bin/env python3
"""配置管理 CLI（不参与应用启动）

用法（项目根目录）:
  python config/manage.py validate [environment]
  python config/manage.py export [environment]
  python config/manage.py compare <env1> <env2>
  python config/manage.py template <environment>
  python config/manage.py list-environments
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, Any, Optional

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config import ConfigFactory, ConfigManager, Environment


def validate_config(environment: Optional[str] = None) -> Dict[str, Any]:
    """验证配置"""
    try:
        config = ConfigFactory.create_config(environment)
        manager = ConfigManager(config)
        result = manager.validate_config()
        return result
    except Exception as e:
        return {
            "valid": False,
            "errors": [f"配置创建失败: {str(e)}"],
            "warnings": [],
            "info": {}
        }


def export_config(environment: Optional[str] = None, exclude_sensitive: bool = True) -> Dict[str, Any]:
    """导出配置"""
    try:
        config = ConfigFactory.create_config(environment)
        manager = ConfigManager(config)
        return manager.export_config(exclude_sensitive)
    except Exception as e:
        return {"error": f"配置导出失败: {str(e)}"}


def compare_configs(env1: str, env2: str) -> Dict[str, Any]:
    """比较两个环境的配置"""
    try:
        config1 = ConfigFactory.create_config(env1)
        config2 = ConfigFactory.create_config(env2)
        
        manager1 = ConfigManager(config1)
        manager2 = ConfigManager(config2)
        
        export1 = manager1.export_config(exclude_sensitive=True)
        export2 = manager2.export_config(exclude_sensitive=True)
        
        differences = {}
        all_keys = set(export1.keys()) | set(export2.keys())
        
        for key in all_keys:
            val1 = export1.get(key, "NOT_SET")
            val2 = export2.get(key, "NOT_SET")
            
            if val1 != val2:
                differences[key] = {
                    env1: val1,
                    env2: val2
                }
        
        return {
            "environment_1": env1,
            "environment_2": env2,
            "differences": differences,
            "total_differences": len(differences)
        }
    except Exception as e:
        return {"error": f"配置比较失败: {str(e)}"}


def generate_env_template(environment: str) -> str:
    """生成环境变量模板"""
    try:
        config = ConfigFactory.create_config(environment)
        
        template_lines = [
            f"# =============================================================================",
            f"# {environment.upper()}环境配置模板",
            f"# =============================================================================",
            f"",
            f"# 环境设置",
            f"FASTAPI_ENV={environment}",
            f"",
        ]
        
        # 获取配置字典
        config_dict = config.model_dump()
        
        # 按类别组织配置
        categories = {
            "应用配置": ["debug", "log_level", "project_name", "api_version"],
            "数据库配置": ["database_url", "db_pool_size", "db_max_overflow", "db_echo"],
            "Redis配置": ["redis_host", "redis_port", "redis_db", "redis_password"],
            "安全配置": ["secret_key", "jwt_secret_key", "access_token_expire_minutes"],
            "CORS配置": ["cors_origins", "allowed_hosts"],
            "速率限制": ["rate_limit_enabled", "rate_limit_requests_per_minute"],
            "文件上传": ["max_request_size", "max_file_size", "upload_dir"],
        }
        
        for category, keys in categories.items():
            template_lines.append(f"# {category}")
            for key in keys:
                if key in config_dict:
                    value = config_dict[key]
                    # 转换为环境变量格式
                    env_key = key.upper()
                    if isinstance(value, str):
                        template_lines.append(f"{env_key}={value}")
                    elif isinstance(value, (int, float, bool)):
                        template_lines.append(f"{env_key}={str(value).lower()}")
                    elif isinstance(value, list):
                        template_lines.append(f"{env_key}={json.dumps(value)}")
                    else:
                        template_lines.append(f"{env_key}={str(value)}")
            template_lines.append("")
        
        return "\n".join(template_lines)
    except Exception as e:
        return f"# 模板生成失败: {str(e)}"


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法:")
        print("  python config/manage.py validate [environment]")
        print("  python config/manage.py export [environment] [--include-sensitive]")
        print("  python config/manage.py compare <env1> <env2>")
        print("  python config/manage.py template <environment>")
        print("  python config/manage.py list-environments")
        return
    
    command = sys.argv[1]
    
    if command == "validate":
        environment = sys.argv[2] if len(sys.argv) > 2 else None
        result = validate_config(environment)
        
        print(f"配置验证结果 (环境: {result.get('info', {}).get('environment', 'unknown')})")
        print("=" * 50)
        
        if result["valid"]:
            print("✅ 配置验证通过")
        else:
            print("❌ 配置验证失败")
            print("\n错误:")
            for error in result["errors"]:
                print(f"  - {error}")
        
        if result["warnings"]:
            print("\n警告:")
            for warning in result["warnings"]:
                print(f"  - {warning}")
        
        print(f"\n配置信息:")
        for key, value in result.get("info", {}).items():
            print(f"  {key}: {value}")
    
    elif command == "export":
        environment = sys.argv[2] if len(sys.argv) > 2 else None
        include_sensitive = "--include-sensitive" in sys.argv
        
        result = export_config(environment, not include_sensitive)
        
        if "error" in result:
            print(f"❌ {result['error']}")
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
    
    elif command == "compare":
        if len(sys.argv) < 4:
            print("用法: python config/manage.py compare <env1> <env2>")
            return
        
        env1, env2 = sys.argv[2], sys.argv[3]
        result = compare_configs(env1, env2)
        
        if "error" in result:
            print(f"❌ {result['error']}")
        else:
            print(f"配置比较: {env1} vs {env2}")
            print("=" * 50)
            print(f"差异数量: {result['total_differences']}")
            
            if result['differences']:
                print("\n详细差异:")
                for key, values in result['differences'].items():
                    print(f"\n{key}:")
                    print(f"  {env1}: {values[env1]}")
                    print(f"  {env2}: {values[env2]}")
            else:
                print("\n✅ 两个环境配置相同")
    
    elif command == "template":
        if len(sys.argv) < 3:
            print("用法: python config/manage.py template <environment>")
            return
        
        environment = sys.argv[2]
        template = generate_env_template(environment)
        
        # 保存到文件
        filename = f".env.{environment}"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(template)
        
        print(f"✅ 环境变量模板已生成: {filename}")
        print(template)
    
    elif command == "list-environments":
        environments = ConfigFactory.get_available_environments()
        print("可用环境:")
        for env in environments:
            print(f"  - {env}")
    
    else:
        print(f"❌ 未知命令: {command}")


if __name__ == "__main__":
    main()
