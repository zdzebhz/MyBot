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
    result = build_digest(
        settings, refresh=args.refresh, include_seen=args.include_seen
    )
    output = render_json(result) if args.format == "json" else render_markdown(result)
    print(output, end="")
    if args.commit and result.items and not result.all_sources_failed:
        mark_sent(settings.state_file, result.items, result.generated_at)
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mybot", description="只读 AI 资讯日报")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--config", help="TOML 配置路径；默认 config/mybot.toml")
    subparsers = parser.add_subparsers(dest="command", required=True)

    digest = subparsers.add_parser("digest", help="生成 B 站/小红书 AI 资讯日报")
    digest.add_argument("--format", choices=("markdown", "json"), default="markdown")
    digest.add_argument(
        "--refresh",
        action="store_true",
        help="推荐池不足时触发刷新（更慢）",
    )
    digest.add_argument(
        "--include-seen",
        action="store_true",
        help="包含已推送过的内容",
    )
    digest.add_argument(
        "--commit",
        action="store_true",
        help="成功输出后记入去重账本",
    )
    digest.set_defaults(handler=command_digest)

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
    except BridgeError as exc:
        print(f"桥接错误：{exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("已取消", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
