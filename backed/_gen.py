"""生成 ai-content-hub 后端的 FastAPI 各表分层代码（基于 skill 模板）。

用法：uv run --with jinja2 python _gen.py
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parent
SKILL_LAYERS = Path(r"E:/code/ncepu_bj/ncepu_ideal-skills/sql-to-fastapi-restfulapi-scaffold/resources/templates/layers")

env = Environment(
    loader=FileSystemLoader(str(SKILL_LAYERS)),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    trim_blocks=False,
    lstrip_blocks=False,
)


def F(name, sa_type, py_type, *, pk=False, not_null=True, unique=False,
      default=None, comment="", is_status=False, max_length=None,
      example='"x"', example_expr="'x'", is_ts=False,
      test_locked="'failed'", test_active="'ok'"):
    return dict(
        name=name, db_name=name, sqlalchemy_type=sa_type, pydantic_type=py_type,
        pk=pk, not_null=not_null, unique=unique, default=default, comment=comment,
        is_status=is_status, max_length=max_length, example=example,
        example_expr=example_expr, is_ts=is_ts,
        test_locked=test_locked, test_active=test_active,
    )


TABLES = [
    dict(
        table_name="article", class_name="Article", comment="文章",
        fields=[
            F("id", "Integer", "int", pk=True, not_null=True, comment="文章ID", example="1", example_expr="1"),
            F("title", "String(512)", "str", not_null=True, comment="标题", example='"示例文章标题"', example_expr="'示例文章标题'"),
            F("content_md", "Text", "str", not_null=True, comment="Markdown正文", example='"# 内容"', example_expr="'# 内容'"),
            F("summary", "Text", "str", not_null=False, comment="摘要", example='"摘要"', example_expr="'摘要'"),
            F("tags", "String(255)", "str", not_null=False, max_length=255, comment="标签(逗号分隔)", example='"AI,Python"', example_expr="'AI,Python'"),
            F("cover", "String(512)", "str", not_null=False, max_length=512, comment="封面图URL", example='"https://x/y.png"', example_expr="'https://x/y.png'"),
            F("status", "String(20)", "str", not_null=True, unique=False, default="'draft'", is_status=True, max_length=20, comment="状态(draft/review/published/archived)", example='"draft"', example_expr="'draft'"),
            F("source", "String(20)", "str", not_null=False, default="'human'", max_length=20, comment="来源(human/ai/import)", example='"human"', example_expr="'human'"),
            F("ai_model", "String(100)", "str", not_null=False, max_length=100, comment="AI模型", example='"deepseek-chat"', example_expr="'deepseek-chat'"),
            F("origin_url", "String(512)", "str", not_null=False, max_length=512, comment="导入来源URL", example='"https://x"', example_expr="'https://x'"),
            F("ext", "Text", "str", not_null=False, default="'{}'", comment="扩展字段JSON", example="'{}'", example_expr="'{}'"),
            F("created_at", "DateTime", "datetime", not_null=False, default="func.now()", comment="创建时间", example='"2026-01-01T00:00:00"', example_expr="'2026-01-01T00:00:00'", is_ts=True),
            F("updated_at", "DateTime", "datetime", not_null=False, default="func.now()", comment="更新时间", example='"2026-01-01T00:00:00"', example_expr="'2026-01-01T00:00:00'", is_ts=True),
        ],
    ),
    dict(
        table_name="publication", class_name="Publication", comment="发布实例",
        fields=[
            F("id", "Integer", "int", pk=True, not_null=True, comment="主键ID", example="1", example_expr="1"),
            F("article_id", "Integer", "int", not_null=True, comment="文章ID", example="1", example_expr="1"),
            F("platform", "String(50)", "str", not_null=True, max_length=50, comment="平台", example='"juejin"', example_expr="'juejin'"),
            F("account", "String(50)", "str", not_null=True, default="'default'", max_length=50, comment="账号", example='"default"', example_expr="_new_account()"),
            F("post_id", "String(255)", "str", not_null=False, max_length=255, comment="平台文章ID", example='"12345"', example_expr="'12345'"),
            F("post_url", "String(1024)", "str", not_null=False, max_length=1024, comment="文章链接", example='"https://x/123"', example_expr="'https://x/123'"),
            F("edit_url", "String(1024)", "str", not_null=False, max_length=1024, comment="编辑页链接", example='"https://x/edit"', example_expr="'https://x/edit'"),
            F("status", "String(20)", "str", not_null=True, default="'pending'", is_status=True, max_length=20, comment="状态(pending/ok/failed)", example='"pending"', example_expr="'pending'"),
            F("draft_only", "Boolean", "bool", not_null=True, default="True", comment="仅草稿", example="True", example_expr="True"),
            F("stats", "Text", "str", not_null=False, default="'{}'", comment="阅读点赞等JSON", example="'{}'", example_expr="'{}'"),
            F("last_error", "Text", "str", not_null=False, comment="错误信息", example='""', example_expr="''"),
            F("content_hash", "String(128)", "str", not_null=False, max_length=128, comment="内容指纹", example='"abc"', example_expr="'abc'"),
            F("published_at", "DateTime", "datetime", not_null=False, comment="发布时间", example='"2026-01-01T00:00:00"', example_expr="'2026-01-01T00:00:00'", is_ts=True),
            F("updated_at", "DateTime", "datetime", not_null=False, default="func.now()", comment="更新时间", example='"2026-01-01T00:00:00"', example_expr="'2026-01-01T00:00:00'", is_ts=True),
        ],
        unique_helpers=[dict(name="account", return_type="str", max_length=50)],
    ),
    dict(
        table_name="account", class_name="Account", comment="平台账号",
        fields=[
            F("id", "Integer", "int", pk=True, not_null=True, comment="主键ID", example="1", example_expr="1"),
            F("platform", "String(50)", "str", not_null=True, max_length=50, comment="平台", example='"juejin"', example_expr="'juejin'"),
            F("name", "String(50)", "str", not_null=True, default="'default'", max_length=50, comment="账号名", example='"default"', example_expr="_new_name()"),
            F("profile_dir", "String(512)", "str", not_null=True, max_length=512, comment="浏览器profile目录", example='"data/profiles/juejin_default"', example_expr="'data/profiles/juejin_default'"),
            F("status", "String(20)", "str", not_null=True, default="'unknown'", is_status=True, max_length=20, comment="状态(unknown/logined/offline)", example='"unknown"', example_expr="'unknown'"),
            F("last_check", "DateTime", "datetime", not_null=False, comment="上次检查时间", example='"2026-01-01T00:00:00"', example_expr="'2026-01-01T00:00:00'", is_ts=True),
        ],
        unique_helpers=[dict(name="name", return_type="str", max_length=50)],
    ),
    dict(
        table_name="job", class_name="Job", comment="任务流水",
        fields=[
            F("id", "Integer", "int", pk=True, not_null=True, comment="主键ID", example="1", example_expr="1"),
            F("type", "String(20)", "str", not_null=True, max_length=20, comment="类型(publish/update/sync/import)", example='"publish"', example_expr="'publish'"),
            F("article_id", "Integer", "int", not_null=False, comment="文章ID", example="1", example_expr="1"),
            F("platform", "String(50)", "str", not_null=False, max_length=50, comment="平台", example='"juejin"', example_expr="'juejin'"),
            F("status", "String(20)", "str", not_null=True, default="'running'", is_status=True, max_length=20, comment="状态(running/ok/failed)", example='"running"', example_expr="'running'"),
            F("message", "Text", "str", not_null=False, comment="消息", example='""', example_expr="''"),
            F("created_at", "DateTime", "datetime", not_null=False, default="func.now()", comment="创建时间", example='"2026-01-01T00:00:00"', example_expr="'2026-01-01T00:00:00'", is_ts=True),
            F("finished_at", "DateTime", "datetime", not_null=False, comment="完成时间", example='"2026-01-01T00:00:00"', example_expr="'2026-01-01T00:00:00'", is_ts=True),
        ],
    ),
    dict(
        table_name="task", class_name="Task", comment="统一任务",
        fields=[
            F("id", "Integer", "int", pk=True, not_null=True, comment="主键ID", example="1", example_expr="1"),
            F("task_id", "String(20)", "str", not_null=True, unique=True, max_length=20, comment="短任务ID", example='"abc1234567"', example_expr="_new_task_id()"),
            F("kind", "String(20)", "str", not_null=True, max_length=20, comment="类型(publish/update/sync/refresh/login/assist)", example='"publish"', example_expr="'publish'"),
            F("article_id", "Integer", "int", not_null=False, comment="文章ID", example="1", example_expr="1"),
            F("platforms", "Text", "str", not_null=False, default="'[]'", comment="平台列表JSON", example="'[\"juejin\"]'", example_expr="'[\"juejin\"]'"),
            F("account", "String(50)", "str", not_null=False, default="'default'", max_length=50, comment="账号", example='"default"', example_expr="'default'"),
            F("draft_only", "Boolean", "bool", not_null=True, default="False", comment="仅草稿", example="False", example_expr="False"),
            F("status", "String(20)", "str", not_null=True, default="'pending'", is_status=True, max_length=20, comment="状态(pending/running/ok/failed/waiting_human)", example='"pending"', example_expr="'pending'"),
            F("message", "Text", "str", not_null=False, comment="消息", example='""', example_expr="''"),
            F("result", "Text", "str", not_null=False, default="'{}'", comment="结果JSON", example="'{}'", example_expr="'{}'"),
            F("error", "Text", "str", not_null=False, comment="错误", example='""', example_expr="''"),
            F("attempts", "Integer", "int", not_null=False, default="0", comment="尝试次数", example="0", example_expr="0"),
            F("created_at", "DateTime", "datetime", not_null=False, default="func.now()", comment="创建时间", example='"2026-01-01T00:00:00"', example_expr="'2026-01-01T00:00:00'", is_ts=True),
            F("updated_at", "DateTime", "datetime", not_null=False, default="func.now()", comment="更新时间", example='"2026-01-01T00:00:00"', example_expr="'2026-01-01T00:00:00'", is_ts=True),
            F("finished_at", "DateTime", "datetime", not_null=False, comment="完成时间", example='"2026-01-01T00:00:00"', example_expr="'2026-01-01T00:00:00'", is_ts=True),
        ],
        unique_helpers=[dict(name="task_id", return_type="str", max_length=20)],
    ),
]


def build_context(t):
    fields = t["fields"]
    # 有 DB 默认值（或自增/函数默认）的字段在 Create Schema 中应为可选，
    # 否则会出现「有默认值却必填」导致的 422。
    _nr = {f["name"]: (f["not_null"] if f["default"] is None else False) for f in fields}
    context = dict(
        table_name=t["table_name"],
        class_name=t["class_name"],
        table_comment=t["comment"],
        resource_singular=t["table_name"],
        resource_path=t["table_name"],
        service_name=f'{t["table_name"]}_service',
        primary_key_param="id",
        primary_key_type="int",
        primary_key_comment="主键ID",
        soft_delete_field=None,
        validators=[],
        sensitive_fields=[],
        foreign_keys=[],
        unique_helper_fields=t.get("unique_helpers", []),
        fields=[
            dict(name=f["name"], db_name=f["db_name"], sqlalchemy_type=f["sqlalchemy_type"],
                 primary_key=f["pk"], foreign_key=None, not_null=_nr[f["name"]],
                 unique=f["unique"], default=f["default"], comment=f["comment"])
            for f in fields
        ],
        non_primary_fields=[
            dict(name=f["name"], pydantic_type=f["pydantic_type"], not_null=_nr[f["name"]],
                 max_length=f["max_length"], ge=None, le=None, comment=f["comment"],
                 example=f["example"], is_status_flag=f["is_status"])
            for f in fields if not f["pk"]
        ],
        all_fields=[
            dict(name=f["name"], pydantic_type=f["pydantic_type"], not_null=_nr[f["name"]], example=f["example"])
            for f in fields
        ],
        status_flag_fields=[
            dict(name=f["name"], pydantic_type=f["pydantic_type"], max_length=f["max_length"],
                 ge=None, le=None, comment=f["comment"], example=f["example"],
                 test_value_locked=f["test_locked"], test_value_active=f["test_active"])
            for f in fields if f["is_status"]
        ],
        create_payload_fields=[
            dict(name=f["name"], example_expr=f["example_expr"])
            for f in fields if not f["pk"] and not f["is_status"] and not f["is_ts"]
        ],
        update_payload_fields=[
            dict(name=f["name"], example_expr=f["example_expr"])
            for f in fields if not f["pk"] and not f["is_status"] and not f["is_ts"]
        ],
    )
    return context


def render_to(rel_path, template_name, context, preprocess_resource=False):
    if preprocess_resource:
        # 修复 skill 模板里的三重花括号 /{{{var}}} -> /{var}
        src = Path(SKILL_LAYERS / template_name).read_text(encoding="utf-8")
        src = src.replace("{{{primary_key_param}}}", "{{ '{' ~ primary_key_param ~ '}' }}")
        tmpl = env.from_string(src)
    else:
        tmpl = env.get_template(template_name)
    content = tmpl.render(**context)
    # 注入 func 供 default=func.now() 使用
    if "func.now()" in content and "import func" not in content:
        content = content.replace(
            "from sqlalchemy.orm import relationship",
            "from sqlalchemy import func\nfrom sqlalchemy.orm import relationship",
        )
    # create 时排除 None，让 DB/Column 默认值生效
    if template_name.startswith("repository"):
        content = content.replace("**data.model_dump())", "**data.model_dump(exclude_none=True))")
    if template_name.startswith("schema"):
        # Pydantic V2：class Config -> model_config = ConfigDict(...)
        content = re.sub(
            r"    class Config:\n        json_schema_extra = \{\n(.*?)\n        \}",
            lambda m: "    model_config = ConfigDict(\n        json_schema_extra={\n" + m.group(1) + "\n        }\n    )",
            content,
            flags=re.DOTALL,
        )
        content = content.replace(
            "from pydantic import BaseModel",
            "from pydantic import BaseModel, ConfigDict",
        )
    out = ROOT / rel_path
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    print("wrote", rel_path)


def main():
    for t in TABLES:
        tn = t["table_name"]
        ctx = build_context(t)
        render_to(f"models/{tn}.py", "model/model_template.py", ctx)
        render_to(f"schemas/{tn}.py", "schema/schema_template.py", ctx)
        render_to(f"repository/{tn}_repository.py", "repository/repository_template.py", ctx)
        render_to(f"service/{tn}_service.py", "service/service_template.py", ctx)
        # resource 包
        render_to(f"api/v1/{tn}/{tn}Resource.py", "resource/resource_template.py", ctx, preprocess_resource=True)
        init_content = (
            f'"""{t["comment"]}API 模块"""\n\n'
            f"from .{tn}Resource import router\n\n"
            f'__all__ = ["router"]\n'
        )
        (ROOT / f"api/v1/{tn}/__init__.py").write_text(init_content, encoding="utf-8")
        print("wrote", f"api/v1/{tn}/__init__.py")
        # 测试
        render_to(f"tests/unit/test_{tn}_service.py", "test/unit/test_service_template.py", ctx)
        render_to(f"tests/integration/api/v1/test_{tn}.py", "test/integration/test_api_template.py", ctx)
    print("ALL DONE")


if __name__ == "__main__":
    main()
