# -*- coding: utf-8 -*-
"""命令行入口：基于 click 重写。

- 业务命令复用发布引擎 ``service.publishing.service.Hub``；
- ``serve`` 子命令复用 FastAPI 应用 ``api.hub:app`` 起服务，不再自建 HTTP 服务。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import click
from service.publishing.service import Hub


def _hub(headed: bool) -> Hub:
    """按全局 --headed 选项构造 Hub。"""
    return Hub(headless=not headed)


def _echo_json(obj) -> None:
    click.echo(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


@click.group(help="AI 内容中台命令行")
@click.option("--headed", is_flag=True, help="显示浏览器窗口（登录/排错时用）")
@click.pass_context
def cli(ctx: click.Context, headed: bool) -> None:
    ctx.ensure_object(dict)
    ctx.obj["headed"] = headed


@cli.command(help="扫码/过验证登录（首次必须，之后长期有效）")
@click.option("--platform", required=True)
@click.option("--account", default="default")
@click.option("--timeout", type=int, default=600, help="等登录的秒数")
@click.option("--on-captcha", type=click.Choice(["handoff", "skip", "abort"]),
              default="handoff", help="遇到验证码：handoff=暂停交人工 / skip=跳过 / abort=直接放弃")
@click.pass_context
def login(ctx, platform, account, timeout, on_captcha):
    ok, msg = _hub(ctx.obj["headed"]).login(platform, account, timeout, on_captcha)
    click.echo(("✓ " if ok else "✗ ") + msg)


@cli.command(help="检查平台登录态")
@click.option("--platform", required=True)
@click.option("--account", default="default")
@click.pass_context
def check(ctx, platform, account):
    ok = _hub(ctx.obj["headed"]).check(platform, account)
    click.echo("✓ 已登录" if ok else "✗ 未登录，跑 login")


@cli.command(help="清除登录态（删 profile+cookie 快照，需重新扫码）")
@click.option("--platform", required=True)
@click.option("--account", default="default")
@click.pass_context
def logout(ctx, platform, account):
    r = _hub(ctx.obj["headed"]).logout(platform, account)
    click.echo(f"已清除 {platform} 登录态，删除: {r['removed'] or '无文件'}")


@cli.command(help="查看平台接入说明与验证码处理方式")
@click.option("--platform", required=True)
@click.pass_context
def diagnose(ctx, platform):
    _echo_json(_hub(ctx.obj["headed"]).diagnose(platform))


@cli.command(help="打开页面就地处理验证码（半自动+人工）")
@click.option("--platform", required=True)
@click.option("--account", default="default")
@click.option("--wait", type=int, default=180, help="等人工的秒数")
@click.pass_context
def solve_captcha(ctx, platform, account, wait):
    _echo_json(_hub(ctx.obj["headed"]).solve_captcha(platform, account, wait))


@cli.command(help="浏览器登录博客园并自动抠出 MetaWeblog 令牌写进 config.json")
@click.option("--username", required=True, help="博客园登录用户名/邮箱")
@click.option("--password", required=True, help="登录密码")
@click.option("--account", default="default")
@click.option("--timeout", type=int, default=600)
@click.option("--on-captcha", type=click.Choice(["handoff", "abort"]), default="handoff")
@click.pass_context
def bootstrap_cnblogs(ctx, username, password, account, timeout, on_captcha):
    r = _hub(ctx.obj["headed"]).bootstrap_cnblogs(
        username, password, account, timeout, on_captcha)
    _echo_json(r)


@cli.command(help="导入本地 Markdown")
@click.option("--path", required=True)
@click.option("--tags", default="")
@click.pass_context
def import_md(ctx, path, tags):
    click.echo("导入成功，文章 ID = " + str(_hub(ctx.obj["headed"]).import_md(path, tags=tags)))


@cli.command(help="新建文章")
@click.option("--title", required=True)
@click.option("--content", default="")
@click.option("--tags", default="")
@click.pass_context
def create(ctx, title, content, tags):
    aid = _hub(ctx.obj["headed"]).create(title, content, tags=tags, source="human")
    click.echo("文章 ID = " + str(aid))


@cli.command(help="发布到平台（逗号分隔，如 juejin,csdn）")
@click.option("--id", type=int, required=True)
@click.option("--platforms", required=True, help="逗号分隔的平台名")
@click.option("--draft", is_flag=True, help="只发草稿箱")
@click.pass_context
def publish(ctx, id, platforms, draft):
    rows = _hub(ctx.obj["headed"]).publish(id, platforms.split(","), draft_only=draft)
    _echo_json(rows)


@cli.command(help="原地更新已发布文章")
@click.option("--id", type=int, required=True)
@click.option("--platforms", default="", help="留空表示全部已发布平台")
@click.pass_context
def update(ctx, id, platforms):
    plats = platforms.split(",") if platforms else None
    _echo_json(_hub(ctx.obj["headed"]).update(id, plats))


@cli.command(help="把所有改动同步到已发布平台")
@click.pass_context
def sync(ctx):
    _echo_json(_hub(ctx.obj["headed"]).sync_pending())


@cli.command(help="抓取平台上已有文章列表入库")
@click.option("--platform", required=True)
@click.pass_context
def refresh(ctx, platform):
    _echo_json(_hub(ctx.obj["headed"]).refresh(platform))


@cli.command("ai-write", help="AI 写一篇并入库")
@click.option("--topic", required=True)
@click.option("--style", default="")
@click.option("--words", type=int, default=2000)
@click.option("--tags", default="", help="给 AI 的标签提示")
@click.option("--publish", default="", help="写完顺手发到这些平台，逗号分隔")
@click.pass_context
def ai_write(ctx, topic, style, words, tags, publish):
    pub = publish.split(",") if publish else None
    _echo_json(_hub(ctx.obj["headed"]).ai_write(topic, style, words, tags, pub))


@cli.command("ai-rewrite", help="AI 改写已有文章")
@click.option("--id", type=int, required=True)
@click.option("--instruction", required=True)
@click.option("--publish", default="")
@click.pass_context
def ai_rewrite(ctx, id, instruction, publish):
    pub = publish.split(",") if publish else None
    _echo_json(_hub(ctx.obj["headed"]).ai_rewrite(id, instruction, pub))


@cli.command("ai-polish", help="AI 润色文章")
@click.option("--id", type=int, required=True)
@click.pass_context
def ai_polish(ctx, id):
    _echo_json(_hub(ctx.obj["headed"]).ai_polish(id))


@cli.command(help="中台总览：文章数、发布数、待同步数、账号状态")
@click.pass_context
def status(ctx):
    _echo_json(_hub(ctx.obj["headed"]).status())


@cli.command(help="启动 REST API 服务（复用 api.hub 的 FastAPI app）")
@click.option("--host", default="127.0.0.1")
@click.option("--port", type=int, default=8800)
def serve(host, port):
    import uvicorn
    from api.hub import app
    uvicorn.run(app, host=host, port=port, reload=False)


if __name__ == "__main__":
    cli()
