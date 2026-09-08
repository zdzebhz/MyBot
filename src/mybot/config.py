"""Configuration loading for MyBot."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_KEYWORDS = (
    "AI",
    "人工智能",
    "大模型",
    "语言模型",
    "LLM",
    "Agent",
    "智能体",
    "多模态",
    "生成式",
    "机器学习",
    "深度学习",
    "神经网络",
    "机器人",
    "具身智能",
    "OpenAI",
    "ChatGPT",
    "Anthropic",
    "Claude",
    "DeepSeek",
    "Gemini",
    "Qwen",
    "通义千问",
    "MCP",
    "RAG",
)


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    root: Path
    config_path: Path
    platforms: tuple[str, ...]
    keywords: tuple[str, ...]
    max_age_hours: int
    fetch_per_platform: int
    digest_limit: int
    bridge_timeout_seconds: int
    state_file: Path
    openbiliclaw_root: Path
    openbiliclaw_python: Path


def _table(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name, {})
    return value if isinstance(value, dict) else {}


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(os.path.expandvars(str(value))).expanduser()
    return path if path.is_absolute() else root / path


def default_config_path(root: Path | None = None) -> Path:
    root = root or project_root()
    env_path = os.getenv("MYBOT_CONFIG", "").strip()
    return _resolve(root, env_path) if env_path else root / "config" / "mybot.toml"


def load_settings(path: str | Path | None = None) -> Settings:
    root = project_root()
    config_path = _resolve(root, path) if path else default_config_path(root)
    if not config_path.exists():
        example = root / "config" / "mybot.example.toml"
        raise FileNotFoundError(
            f"找不到配置文件 {config_path}。请先复制 {example.name} 为 mybot.toml，"
            "或运行 scripts/setup.ps1。"
        )

    with config_path.open("rb") as handle:
        data = tomllib.load(handle)

    digest = _table(data, "digest")
    runtime = _table(data, "runtime")
    platforms = tuple(str(item).strip().lower() for item in digest.get("platforms", []))
    platforms = tuple(item for item in platforms if item)
    if not platforms:
        raise ValueError("digest.platforms 至少需要一个平台")

    keywords = tuple(
        str(item).strip() for item in digest.get("keywords", DEFAULT_KEYWORDS)
    )
    keywords = tuple(item for item in keywords if item)
    if not keywords:
        raise ValueError("digest.keywords 不能为空")

    ob_root = _resolve(root, runtime.get("openbiliclaw_root", ".runtime/openbiliclaw"))
    default_python = (
        ob_root / ".venv" / "Scripts" / "python.exe"
        if os.name == "nt"
        else ob_root / ".venv" / "bin" / "python"
    )
    python_override = os.getenv("OPENBILICLAW_PYTHON", "").strip()
    python_value = python_override or runtime.get(
        "openbiliclaw_python", str(default_python)
    )

    return Settings(
        root=root,
        config_path=config_path,
        platforms=platforms,
        keywords=keywords,
        max_age_hours=max(1, int(digest.get("max_age_hours", 72))),
        fetch_per_platform=max(1, int(digest.get("fetch_per_platform", 20))),
        digest_limit=max(1, int(digest.get("digest_limit", 10))),
        bridge_timeout_seconds=max(10, int(runtime.get("bridge_timeout_seconds", 180))),
        state_file=_resolve(root, runtime.get("state_file", ".data/mybot/sent.json")),
        openbiliclaw_root=ob_root,
        openbiliclaw_python=_resolve(root, python_value),
    )
