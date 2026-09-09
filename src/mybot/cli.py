"""Command-line entry point for MyBot."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__
from .config import load_settings
from .digest import build_digest, mark_sent, render_json, render_markdown
from .openbiliclaw import BridgeError, OpenBiliClawClient


def _settings_or_exit(config: str | None):
    try:
        return load_settings(config)
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        raise SystemExit(2) from exc


def command_digest(args: argparse.Namespace) -> int:
    settings = _settings_or_exit(args.config)
    if args.commit:
        raise ValueError("--commit 已停用；请使用 send-email")
    result = build_digest(
        settings, refresh=args.refresh, include_seen=args.include_seen
    )
    output = render_json(result) if args.format == "json" else render_markdown(result)
    if args.output:
        path=Path(args.output).resolve()
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(output,encoding="utf-8")
    print(output, end="")
    return 2 if result.all_sources_failed else 0


def _qwenpaw_executable(root: Path) -> Path:
    relative = ("Scripts", "qwenpaw.exe") if os.name == "nt" else ("bin", "qwenpaw")
    return root.joinpath(".runtime", "qwenpaw", *relative)


def command_doctor(args: argparse.Namespace) -> int:
    settings = _settings_or_exit(args.config)
    checks: list[dict[str, str | bool]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    qwenpaw = _qwenpaw_executable(settings.root)
    add("MyBot 配置", settings.config_path.exists(), str(settings.config_path))
    add("uv", shutil.which("uv") is not None, shutil.which("uv") or "未安装")
    add("QwenPaw", qwenpaw.exists(), str(qwenpaw))
    qwen_config = settings.root / ".data" / "qwenpaw" / "config.json"
    qwen_skill = (
        settings.root
        / ".data"
        / "qwenpaw"
        / "workspaces"
        / "default"
        / "skills"
        / "ai-daily-digest"
        / "SKILL.md"
    )
    add("QwenPaw \u521d\u59cb\u5316", qwen_config.exists(), str(qwen_config))
    add("\u65e5\u62a5 Skill", qwen_skill.exists(), str(qwen_skill))
    add(
        "OpenBiliClaw 源码",
        settings.openbiliclaw_root.exists(),
        str(settings.openbiliclaw_root),
    )
    add(
        "OpenBiliClaw 环境",
        settings.openbiliclaw_python.exists(),
        str(settings.openbiliclaw_python),
    )

    if settings.openbiliclaw_python.exists():
        client = OpenBiliClawClient(settings)
        try:
            capabilities = client.capabilities().get("data", {})
            detail = (
                f"capabilities={len(capabilities)}"
                if isinstance(capabilities, dict)
                else "可用"
            )
            add("Agent Bridge", True, detail)
        except (BridgeError, subprocess.TimeoutExpired) as exc:
            add("Agent Bridge", False, str(exc))
        try:
            status = client.runtime_status().get("data", {})
            detail = json.dumps(status, ensure_ascii=False, separators=(",", ":"))[:600]
            add("OpenBiliClaw 初始化", True, detail)
        except (BridgeError, subprocess.TimeoutExpired) as exc:
            add("OpenBiliClaw 初始化", False, str(exc))

    passed = all(bool(item["ok"]) for item in checks)
    if args.json:
        print(
            json.dumps(
                {"ok": passed, "checks": checks},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for item in checks:
            marker = "OK" if item["ok"] else "!!"
            print(f"[{marker}] {item['name']}: {item['detail']}")
    return 0 if passed else 1



def command_collect(args):
    from .radar import collect
    report=collect(_settings_or_exit(args.config),search=not args.cache_only)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 2 if report["errors"] else 0


def command_email(args):
    from .mail import send
    settings=_settings_or_exit(args.config)
    result=build_digest(settings)
    print(json.dumps(send(settings,result),ensure_ascii=False))
    return 0


def command_run(args):
    from .worker import run
    run(_settings_or_exit(args.config),once=args.once)
    return 0


def command_read(args):
    from .pool import mark_read
    from .digest import utc_now
    mark_read(_settings_or_exit(args.config),args.key,utc_now().isoformat())
    print("已标记本地已读")
    return 0


def command_email_setup(args):
    import getpass
    from .mail import credentials
    settings=_settings_or_exit(args.config)
    secret=getpass.getpass("SMTP 授权码（输入不回显，不是 QQ 登录密码）: ")
    if not secret.strip():
        raise ValueError("授权码不能为空")
    path=settings.state_file.parent/"email-secret.json"
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({"password":secret}),encoding="utf-8")
    credentials(settings)
    print("已保存到本机 Git 忽略目录；尚未发送邮件。")
    return 0


def command_email_status(args):
    from . import pool
    from .mail import credentials
    settings=_settings_or_exit(args.config)
    try:
        credentials(settings)
        configured=True
    except (ValueError,OSError):
        configured=False
    with pool.connect(settings) as db:
        rows=[dict(r) for r in db.execute("SELECT id,status,created_at,error FROM outbox ORDER BY created_at DESC LIMIT 10")]
        counts=dict(db.execute("SELECT COUNT(*) AS total,SUM(sent_at IS NOT NULL) AS sent,SUM(read_at IS NOT NULL) AS read FROM items").fetchone())
    print(json.dumps(dict(credentials_present=configured,recipient=settings.email_to,
                         pool=counts,outbox=rows),ensure_ascii=False,indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mybot", description="只读 AI 信息雷达")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--config", help="TOML 配置路径；默认 config/mybot.toml")
    subparsers = parser.add_subparsers(dest="command", required=True)

    digest = subparsers.add_parser("digest", help="从持久 AI 池预览待交付内容")
    digest.add_argument("--format", choices=("markdown", "json"), default="markdown")
    digest.add_argument("--output",help="另存本地预览文件，不标记发送")
    digest.add_argument(
        "--refresh",
        action="store_true",
        help="先采集并审核信息池（遵守上游限速）",
    )
    digest.add_argument(
        "--include-seen",
        action="store_true",
        help="包含已推送过的内容",
    )
    digest.add_argument(
        "--commit",
        action="store_true",
        help="已停用，改用 send-email",
    )
    digest.set_defaults(handler=command_digest)

    collect = subparsers.add_parser("collect", help="采集并积累AI信息池")
    collect.add_argument("--cache-only",action="store_true")
    collect.set_defaults(handler=command_collect)
    email = subparsers.add_parser("send-email",help="通过SMTP交付，成功才标记发送")
    email.set_defaults(handler=command_email)
    setup_email = subparsers.add_parser("configure-email",help="本机安全输入SMTP授权码")
    setup_email.set_defaults(handler=command_email_setup)
    email_status = subparsers.add_parser("email-status",help="查看邮件和池状态，不输出凭据")
    email_status.set_defaults(handler=command_email_status)
    runner = subparsers.add_parser("run",help="持续采集，08:30交付；电脑关机时暂停")
    runner.add_argument("--once",action="store_true")
    runner.set_defaults(handler=command_run)
    read = subparsers.add_parser("mark-read",help="标记本地已读，不调用平台互动")
    read.add_argument("key")
    read.set_defaults(handler=command_read)

    doctor = subparsers.add_parser("doctor", help="检查本地环境和桥接状态")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(handler=command_doctor)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except subprocess.TimeoutExpired as exc:
        print(f"执行超时：{exc}", file=sys.stderr)
        return 2
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"执行错误：{exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("已取消", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
