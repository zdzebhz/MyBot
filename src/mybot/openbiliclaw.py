"""Read-only client for OpenBiliClaw's host-neutral Agent Bridge."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any

from .config import Settings


class BridgeError(RuntimeError):
    """The OpenBiliClaw bridge could not satisfy a read-only request."""


def decode_json_output(raw: str) -> dict[str, Any]:
    """Decode JSON even if a dependency printed harmless log lines."""
    text = raw.strip().lstrip("\ufeff")
    if not text:
        raise BridgeError("OpenBiliClaw 没有返回内容")
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    candidates: list[dict[str, Any]] = []
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            candidates.append(value)
    if candidates:
        for candidate in reversed(candidates):
            if "ok" in candidate:
                return candidate
        return candidates[0]
    raise BridgeError("无法解析 OpenBiliClaw 的 JSON 输出")


def _failure_detail(raw: str) -> str:
    text = raw.strip()
    if "No LLM providers are available" in text:
        return "尚未配置模型提供商；请先运行 " "scripts/initialize-openbiliclaw.ps1。"
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1][-800:] if lines else "没有错误详情"


@dataclass
class OpenBiliClawClient:
    settings: Settings

    def _run(self, command: str, *args: str) -> dict[str, Any]:
        python = self.settings.openbiliclaw_python
        if not python.exists():
            raise BridgeError(f"未找到 OpenBiliClaw Python: {python}")
        if not self.settings.openbiliclaw_root.exists():
            raise BridgeError(
                f"未找到 OpenBiliClaw 目录: {self.settings.openbiliclaw_root}"
            )

        env = os.environ.copy()
        env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        completed = subprocess.run(
            [
                str(python),
                "-m",
                "openbiliclaw.integrations.openclaw.cli",
                command,
                *args,
            ],
            cwd=self.settings.openbiliclaw_root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.settings.bridge_timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            detail = _failure_detail(completed.stderr or completed.stdout)
            raise BridgeError(
                f"OpenBiliClaw {command} 失败"
                f"（退出码 {completed.returncode}）：{detail}"
            )
        payload = decode_json_output(completed.stdout)
        if not payload.get("ok", False):
            reason = payload.get("error") or payload.get("message") or "未知错误"
            raise BridgeError(f"OpenBiliClaw {command} 返回失败: {reason}")
        return payload

    def capabilities(self) -> dict[str, Any]:
        return self._run("capabilities")

    def runtime_status(self) -> dict[str, Any]:
        return self._run("runtime-status")

    def recommend(
        self, platform: str, limit: int, refresh: bool = False
    ) -> list[dict[str, Any]]:
        args = ["--limit", str(limit), "--source-platform", platform]
        if refresh:
            args.append("--refresh-if-needed")
        payload = self._run("recommend", *args)
        data = payload.get("data", {})
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("items", [])
        else:
            items = []
        if not isinstance(items, list):
            raise BridgeError("OpenBiliClaw recommend 返回了意外的数据结构")
        return [item for item in items if isinstance(item, dict)]
