"""AI radar delivery rendering; collection and state live in radar/pool."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .config import Settings
from .openbiliclaw import BridgeError, OpenBiliClawClient

UTC = timezone.utc
URL_RE = re.compile(r"^https?://", re.IGNORECASE)
PUBLIC_FIELDS = (
    "bvid",
    "title",
    "source_platform",
    "author_name",
    "up_name",
    "published_at",
    "published_label",
    "content_type",
    "content_url",
    "reason",
    "topic_label",
    "confidence",
    "duration",
    "view_count",
    "like_count",
    "favorite_count",
    "comment_count",
    "cover_url",
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        stamp = float(value)
        if stamp > 10_000_000_000:
            stamp /= 1000
        try:
            return datetime.fromtimestamp(stamp, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if text.isdigit():
        return parse_datetime(int(text))
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def item_key(item: dict[str, Any]) -> str:
    for field in ("item_key", "content_url", "content_id", "bvid", "recommendation_id"):
        value = str(item.get(field, "") or "").strip()
        if value:
            return value
    raw = "\x1f".join(
        str(item.get(field, "") or "")
        for field in ("source_platform", "title", "author_name", "up_name")
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _contains_keyword(text: str, keyword: str) -> bool:
    haystack = text.casefold()
    needle = keyword.casefold()
    if keyword.isascii() and keyword.isalnum() and len(keyword) <= 3:
        return (
            re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack)
            is not None
        )
    return needle in haystack


def keyword_score(
    item: dict[str, Any], keywords: Iterable[str]
) -> tuple[int, list[str]]:
    fields = (
        ("title", 8),
        ("topic_label", 5),
        ("reason", 3),
        ("expression", 2),
        ("body_text", 1),
    )
    score, matches = 0, []
    for keyword in keywords:
        needle, matched = keyword.casefold(), False
        for field, weight in fields:
            text = str(item.get(field, "") or "")
            if _contains_keyword(text, needle):
                score += weight
                matched = True
        if matched:
            matches.append(keyword)
    return score, matches


def _number(item: dict[str, Any], name: str) -> float:
    try:
        return float(item.get(name, 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def rank_items(
    items: Iterable[dict[str, Any]],
    settings: Settings,
    sent_keys: set[str],
    *,
    include_seen: bool = False,
    now: datetime | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    from .radar import rank
    return rank(items, settings, sent_keys, include_seen, now)


def load_sent(path: Path) -> dict[str, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    values = payload.get("sent", {}) if isinstance(payload, dict) else {}
    return (
        {str(key): str(value) for key, value in values.items()}
        if isinstance(values, dict)
        else {}
    )


def mark_sent(
    path: Path,
    items: Iterable[dict[str, Any]],
    now: datetime | None = None,
) -> None:
    now, sent = now or utc_now(), load_sent(path)
    kept = dict(sent)
    kept.update({item_key(item): now.isoformat() for item in items})
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(
            {"schema_version": 1, "sent": kept},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


@dataclass(frozen=True)
class DigestResult:
    generated_at: datetime
    items: list[dict[str, Any]]
    errors: dict[str, str]
    stats: dict[str, int]

    @property
    def all_sources_failed(self) -> bool:
        return bool(self.errors) and self.stats.get("received", 0) == 0


def build_digest(
    settings: Settings,
    *,
    refresh: bool = False,
    include_seen: bool = False,
    client: OpenBiliClawClient | None = None,
    now: datetime | None = None,
) -> DigestResult:
    from .radar import build
    return build(settings, refresh, include_seen, client, now)


def public_item(item: dict[str, Any]) -> dict[str, Any]:
    result = {key: item[key] for key in PUBLIC_FIELDS if key in item}
    result.update(
        mybot_key=item.get("_mybot_key", item_key(item)),
        matched_keywords=item.get("_mybot_matches", []),
        relevance_score=item.get("_mybot_score", 0),
        category=item.get("_mybot_category", "other"),
        score_parts=item.get("_mybot_score_parts", {}),
        first_discovered_at=item.get("first_discovered_at", ""),
    )
    return result


def render_json(result: DigestResult) -> str:
    return (
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": result.generated_at.isoformat(),
                "read_only": True,
                "items": [public_item(item) for item in result.items],
                "errors": result.errors,
                "stats": result.stats,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )


def render_markdown(result: DigestResult) -> str:
    date_label = result.generated_at.astimezone().strftime("%Y-%m-%d %H:%M")
    lines = [f"# AI 信息雷达（{date_label}）", "",
             "这是最近发现、尚未标记看过或推送的一批 AI 内容。旧作品也可能是新发现。",
             "推荐依据为标题/简介的模型判断，未核验全文及创作者的事实主张。", ""]
    if not result.items:
        lines += ["信息池中暂无未读、未推送的合格 AI 内容。", ""]
    for index, item in enumerate(result.items, 1):
        title = str(item.get("title") or "未命名内容").strip()
        url = str(item.get("content_url") or "").strip()
        title_text = f"[{title}]({url})" if URL_RE.match(url) else title
        author = item.get("author_name") or item.get("up_name") or "未知作者"
        published = (
            item.get("published_label") or (parse_datetime(item.get("published_at")).isoformat() if parse_datetime(item.get("published_at")) else "时间未知")
        )
        lines += [
            f"## {index}. {title_text}",
            "",
            f"- 来源：{item.get('source_platform') or '未知平台'} · {author}",
            f"- 发布时间：{published}",
            f"- 首次发现：{item.get('first_discovered_at', '本轮')} · 类型：{item.get('_mybot_category', 'other')}",
            f"- 雷达评分：{item.get('_mybot_score', 0)}（启发式排序，非事实核验）",
        ]
        if item.get("_mybot_matches"):
            lines.append(f"- 命中：{', '.join(item['_mybot_matches'][:8])}")
        reason = str(item.get("reason") or item.get("expression") or "").strip()
        if reason:
            lines.append(f"- 推荐理由：{reason}")
        lines.append("")
    if result.errors:
        lines += ["## 采集提示", ""]
        lines += [f"- {platform}：{error}" for platform, error in result.errors.items()]
        lines.append("")
    lines.append(
        "> 安全说明：本日报只读取公开/已授权内容，" "不会点赞、评论、关注或发帖。"
    )
    return "\n".join(lines).rstrip() + "\n"
