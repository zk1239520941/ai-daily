"""RSS 板块:沿用现有 collect_entries_for_push + compose_digest 流程

迁移自 src/main.py::run_push_job 中 RSS digest 部分,行为保持一致。
"""

from datetime import datetime
from typing import Dict, Optional, Tuple

from src.llm import compose_digest, parse_digest_with_metadata
from src.storage import (
    extract_push_time,
    get_last_push_file,
    load_notified_links,
    load_recent_push_content,
)


async def run_rss_section(
    config: Dict, now: Optional[datetime] = None
) -> Tuple[str, Optional[Dict], Optional[str]]:
    """生成 RSS digest markdown 段(不含 sentinel)。

    返回:
        (markdown_body, metadata, error)
        - 无新内容时返回 ("", None, None)
        - compose_digest 失败时返回 ("", None, error_message)
    """
    from src.main import collect_entries_for_push

    last_push_file = get_last_push_file()
    last_push_time = extract_push_time(last_push_file) if last_push_file else None

    filt = config["filter"]
    min_score = filt["min_score"]
    context_days = filt["context_days"]
    push_window_hours = filt.get("push_window_hours", 24)
    no_content_marker = filt.get("no_content_marker", "[NO_NEW_CONTENT]")

    exclude_links = None
    if filt.get("exclude_notified_links_from_digest", True):
        exclude_links = load_notified_links(context_days)

    to_push, context = collect_entries_for_push(
        last_push_time=last_push_time,
        context_days=context_days,
        min_score=min_score,
        push_window_hours=push_window_hours,
        exclude_links=exclude_links,
        config=config,
    )

    if not to_push:
        print("ℹ️ RSS: 无新消息")
        return "", None, None

    push_context_days = filt.get("push_context_days", 5)
    recent = load_recent_push_content(push_context_days)

    try:
        raw = await compose_digest(
            to_push, context, config["llm"], recent_push_context=recent
        )
    except Exception as e:
        msg = f"compose_digest 失败: {e}"
        print(f"⚠️ RSS: {msg}")
        return "", None, msg

    if no_content_marker in (raw or ""):
        print("ℹ️ RSS: LLM 判定无新内容")
        return "", None, None

    date_str = (now or datetime.now()).strftime("%Y-%m-%d")
    body, metadata = parse_digest_with_metadata(raw or "", date_str)

    if not body or not metadata:
        print("ℹ️ RSS: 解析后无有效条目")
        return "", None, None

    entry_images = {
        e["link"]: e["image_url"]
        for e in to_push
        if e.get("link") and e.get("image_url")
    }
    if entry_images:
        metadata["entry_images"] = entry_images

    return body, metadata, None
