"""AI每日资讯推送系统 - 主程序"""

import os
import sys

from src.console import configure_stdio_utf8

configure_stdio_utf8()

import argparse
import asyncio
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

# 加载 .env 文件
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from croniter import croniter

from src.config import get_timezone, load_config, merge_sources
from src.fetcher import fetch_all_feeds
from src.llm import (
    check_llm_available,
    generate_immediate_push,
    parse_immediate_push_with_metadata,
    score_batch,
)
from src.processor import html_to_markdown
from src.push import send_to_platforms
from src.sections.github.section import run_github_section
from src.sections.hackernews.section import run_hackernews_section
from src.sections.insights.section import run_insights_section
from src.sections.rss.section import run_rss_section
from src.markdown_utils import parse_frontmatter
from src.pages.cover import enrich_image_metadata
from src.pages.parser import build_sections_manifest
from src.storage import (
    append_entries,
    assemble_with_sentinels,
    cleanup_old_files,
    find_push_for_local_date,
    get_fetch_file,
    get_last_push_file,
    get_notify_file,
    get_push_file,
    load_existing_links,
    load_notified_links,
    load_recent_notify_content,
    load_recent_push_content,
    read_entries,
    save_notify_file,
    save_push_file,
)
from src.run_state import (
    evaluate_daily_health,
    has_digest_skip_for_date,
    read_push_result,
    record_digest_error,
    record_digest_skip,
    record_digest_success,
    record_fetch_error,
    record_fetch_success,
    write_push_result,
)

# push 命令：四段全空跳过时的 exit code（GHA 仍视为 success，但会读 result 文件）
EXIT_DIGEST_SKIPPED = 2


async def notify_llm_errors(stage: str, errors: List[str], config: Dict):
    """发送简单的 LLM 异常通知"""
    if not errors:
        return

    lines = [
        "## LLM异常",
        "",
        f"stage: {stage}",
        f"time: {now_local(config).strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]
    lines.extend(f"- {error}" for error in errors)

    try:
        await send_to_platforms("\n".join(lines), config["push"])
    except Exception as e:
        print(f"⚠️ LLM异常通知发送失败: {e}")


def now_local(config: Dict = None) -> datetime:
    """获取配置时区的当前时间"""
    return datetime.now(get_timezone(config))


def parse_time_to_local(time_str: str, config: Dict = None) -> Optional[datetime]:
    """解析时间字符串为配置时区的datetime"""
    try:
        dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        return dt.astimezone(get_timezone(config))
    except (ValueError, TypeError):
        return None


def calculate_push_times(
    cron_list: List[str], offset_days: int = 0, config: Dict = None
) -> List[datetime]:
    base_date = datetime.now(get_timezone(config)).date() + timedelta(days=offset_days)
    times = []
    for cron in cron_list:
        try:
            minute, hour, _, _, _ = cron.split()
            t = datetime.combine(
                base_date,
                datetime.strptime(f"{hour}:{minute}", "%H:%M").time(),
                tzinfo=get_timezone(config),
            )
            times.append(t)
        except ValueError:
            continue
    return sorted(times)


def _fallback_push_cutoff(now: datetime, config: Dict) -> datetime:
    """无上次 push 时：取本地昨日 push_cron 时刻作为收录边界。"""
    tz = get_timezone(config)
    local_now = now.astimezone(tz)
    hour, minute = 8, 0
    cron_list = config.get("schedule", {}).get("push_cron", ["0 8 * * *"])
    if cron_list:
        try:
            minute_s, hour_s, _, _, _ = cron_list[0].split()
            hour, minute = int(hour_s), int(minute_s)
        except ValueError:
            pass
    today_push = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if local_now >= today_push:
        return today_push - timedelta(days=1)
    return today_push - timedelta(days=2)


def _should_skip_digest(
    config: Dict,
    final_md: str,
    rss_md: str,
    gh_md: str,
    hn_md: str,
    insights_md: str,
) -> bool:
    """四段全空或配置关闭时跳过 digest 落盘与推送。"""
    if not config.get("filter", {}).get("skip_empty_digest", True):
        return False
    if not (final_md or "").strip():
        return True
    rss_count = (rss_md or "").count("###")
    has_other = any(
        s.strip() for s in (gh_md or "", hn_md or "", insights_md or "")
    )
    if rss_count == 0 and not has_other:
        return True
    min_items = config.get("filter", {}).get("digest_min_items", 0)
    if min_items > 0 and rss_count < min_items and not has_other:
        return True
    return False


def collect_entries_for_push(
    last_push_time: Optional[datetime],
    context_days: int = 2,
    min_score: int = 60,
    data_dir: str = "news-data",
    push_window_hours: int = 24,
    exclude_links: Optional[set] = None,
    config: Optional[Dict] = None,
) -> tuple[List[Dict], List[Dict]]:
    """
    收集推送所需的条目，返回 (待推送条目, 上下文条目)

    逻辑：
    1. 获取 context_days 天内的所有条目
    2. 按 min_score 过滤
    3. push_cutoff = max(last_push_time, now - push_window_hours)；无 last_push 时用昨日 push_cron
    4. 晚于 push_cutoff 的 → 待推送条目
    5. 早于 push_cutoff 的 → 上下文条目（用于LLM去重参考）
    """
    tz = get_timezone(config)
    now = datetime.now(tz)

    all_entries = []
    today = now.date()
    for i in range(context_days):
        d = today - timedelta(days=i)
        fetch_file = get_fetch_file(d, data_dir)
        for entry in read_entries(fetch_file):
            all_entries.append(entry)

    print(
        f"📋 收集总条目: {len(all_entries)} 条 , context_days: {context_days}, min_score:{min_score}"
    )

    qualified_entries = [e for e in all_entries if (e.get("score") or 0) >= min_score]
    print(f"📋 过滤后条目: {len(qualified_entries)} 条 ")

    past_window = now - timedelta(hours=push_window_hours)
    if last_push_time:
        push_cutoff = max(last_push_time, past_window)
    else:
        push_cutoff = _fallback_push_cutoff(now, config or {})

    print(f"推送时间边界: {push_cutoff.strftime('%Y-%m-%d %H:%M:%S')}")

    to_push = []
    context = []
    CONTEXT_FIELDS = ("title", "source", "score", "summary", "tags", "published")

    for entry in qualified_entries:
        entry_time = parse_time_to_local(entry.get("fetched_at", ""), config)
        if entry_time and entry_time > push_cutoff:
            to_push.append(entry)
        else:
            context.append({k: entry.get(k) for k in CONTEXT_FIELDS})

    if exclude_links:
        before = len(to_push)
        to_push = [e for e in to_push if e.get("link") not in exclude_links]
        excluded = before - len(to_push)
        if excluded:
            print(f"📋 排除已即时推送链接: {excluded} 条")

    context = sorted(context, key=lambda x: x.get("score", 0), reverse=True)[:50]

    return to_push, context


def _enrich_wecom_items_with_entry_images(
    items: Optional[List[Dict]], entries: List[Dict]
) -> None:
    """为即时热点 wecom_items 补充 picurl（按原文 link 匹配 RSS image_url）。"""
    if not items:
        return
    url_to_image = {
        e["link"]: e["image_url"]
        for e in entries
        if e.get("link") and e.get("image_url")
    }
    for item in items:
        picurl = url_to_image.get(item.get("url", ""), "")
        if picurl:
            item["picurl"] = picurl


async def run_fetch_job(config: Dict):
    print(f"\n{'=' * 50}")
    print(f"🔄 Fetch Job | {now_local().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 50}")

    interval = config["schedule"]["fetch_interval_minutes"]
    lookback = config["schedule"].get("fetch_lookback_minutes", 120)
    lookback = max(lookback, interval)
    threshold = lookback + interval
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=lookback)

    sources = merge_sources(config["sources"])
    print(f"📂 共 {len(sources)} 个订阅源")

    if not sources:
        print("⚠️ 没有可用的订阅源")
        return

    max_workers = config.get("fetch", {}).get("max_workers", 20)
    timeout = config.get("fetch", {}).get("timeout", 30)
    entries = await fetch_all_feeds(
        sources, cutoff, max_workers=max_workers, timeout=timeout
    )
    print(f"📥 抓取到 {len(entries)} 条原始消息")

    if not entries:
        return

    for entry in entries:
        entry["content"] = html_to_markdown(
            entry.get("content", ""), entry.get("link", "")
        )

    fetch_file = get_fetch_file()
    existing_links = load_existing_links(fetch_file, threshold)
    new_entries = [
        e for e in entries if e.get("link") and e["link"] not in existing_links
    ]
    print(f"🆕 新消息 {len(new_entries)} 条 | 链接数：{len(existing_links)}")

    if not new_entries:
        return

    print("🤖 LLM评分中...")
    # 预处理：将所有 datetime 转换为字符串，避免 JSON 序列化错误
    for entry in new_entries:
        if isinstance(entry.get("published"), datetime):
            entry["published"] = (
                entry["published"].astimezone(get_timezone(config)).isoformat()
            )

    scored, score_errors = await score_batch(new_entries, config["llm"])
    if score_errors:
        print(f"⚠️ [score_batch] {len(score_errors)} 个错误: {score_errors[0]}")
        await notify_llm_errors("score_batch", score_errors, config)

    is_new_file = not os.path.exists(fetch_file)
    if is_new_file:
        cleanup_old_files(days=config["filter"]["keep_days"], config=config)

    # 添加 fetched_at 时间戳
    for entry in scored:
        entry["fetched_at"] = now_local(config).isoformat()
        if isinstance(entry.get("published"), datetime):
            entry["published"] = (
                entry["published"].astimezone(get_timezone(config)).isoformat()
            )

    # 批量保存到 JSON 文件（meta.date 使用配置时区）
    meta = {"date": now_local(config).date().isoformat()}
    append_entries(fetch_file, scored, meta)

    print(f"💾 已保存到 {fetch_file}")

    hot_threshold = config["filter"]["hot_threshold"]
    no_content_marker = config["filter"].get("no_content_marker", "[NO_NEW_CONTENT]")
    hot_entries = [e for e in scored if (e.get("score") or 0) >= hot_threshold]
    if hot_entries:
        print(f"🔥 发现 {len(hot_entries)} 条热点消息，即时推送...")

        # 加载近期已推送内容（仅供 LLM 查重，避免风格趋同）
        context_days = config["filter"]["context_days"]
        recent_notify = load_recent_notify_content(context_days)
        recent_push = load_recent_push_content(context_days)
        recent_context = (
            f"=== 近期即时推送 ===\n{recent_notify}\n\n"
            f"=== 近期汇总推送 ===\n{recent_push}"
        )

        push_content, immediate_push_error = await generate_immediate_push(
            hot_entries, config["llm"], recent_push_context=recent_context
        )

        if immediate_push_error:
            print(f"⚠️ [generate_immediate_push] {immediate_push_error}")
            await notify_llm_errors(
                "generate_immediate_push", [immediate_push_error], config
            )

        if not push_content:
            print("⚠️ 即时推送内容生成失败，跳过本次热点推送")
            print(
                f"✅ Fetch Job 完成 | 新消息: {len(scored)} 条 | 热点: {len(hot_entries)} 条"
            )
            return

        # 检查是否有实际内容需要推送
        if no_content_marker in push_content:
            print(f"ℹ️ 无新内容需要推送 (LLM判定为重复内容)")
        else:
            # 提取标题并构建 metadata
            now = now_local(config)
            timestamp = now.strftime("%Y-%m-%d %H:%M")
            content_without_title, metadata = parse_immediate_push_with_metadata(
                push_content, f"🚨 AI Daily 快讯 | {timestamp}"
            )
            _enrich_wecom_items_with_entry_images(
                metadata.get("wecom_items"), hot_entries
            )
            metadata["pushTime"] = now.isoformat()
            push_title = "🚨 AI Daily 快讯 | " + metadata["title"]

            await send_to_platforms(
                content_without_title,
                config["push"],
                push_title,
                metadata=metadata,
            )
            # 保存即时推送内容到 notify 文件（JSON 格式也保留可读摘要）
            notify_body = content_without_title
            if metadata.get("wecom_items"):
                lines = [
                    f"## {it['title']}\n{it.get('description', '')}\n{it.get('url', '')}"
                    for it in metadata["wecom_items"]
                ]
                notify_body = "\n\n".join(lines)
            notify_file = get_notify_file()
            save_notify_file(notify_file, notify_body, metadata)
            print(f"💾 已保存即时推送到 {notify_file}")

    print(f"✅ Fetch Job 完成 | 新消息: {len(scored)} 条 | 热点: {len(hot_entries)} 条")


async def run_push_job(
    config: Dict,
    generate_only: bool = False,
    force: bool = False,
) -> Optional[str]:
    """生成 digest 并可选推送企微。

    Args:
        generate_only: True 时仅生成 push md 落盘，不发送 digest 企微（由后续 wecom 步骤发送）

    Returns:
        成功生成 push 文件时返回路径，无内容或失败时返回 None
    """
    print(f"\n{'=' * 50}")
    print(f"📤 Push Job | {now_local().strftime('%Y-%m-%d %H:%M:%S')}")
    if generate_only:
        print("ℹ️ generate_only 模式：仅生成 push md，不推 digest 企微")
    print(f"{'=' * 50}")

    return await _run_daily_push(
        config, generate_only=generate_only, force=force
    )


async def _run_daily_push(
    config: Dict, generate_only: bool = False, force: bool = False
) -> Optional[str]:
    """每日 push 编排:RSS/GH/HN 并发 → insights 串行 → sentinel 拼装 → 落盘。

    失败语义:
    - RSS 真故障 → 整体抛 RuntimeError
    - GH/HN/insights 失败 → 该段省略 + 告警,其他段照推
    - 四段全空 → 静默跳过（可配置企微通知）
    """
    now = now_local(config)
    today = now.date()

    if not force:
        existing = find_push_for_local_date(today)
        if existing:
            print(f"ℹ️ 今日 digest 已存在: {existing}，跳过重复生成")
            write_push_result("idempotent", existing, "already generated today", config)
            record_digest_success(existing, config)
            return existing
        if has_digest_skip_for_date(today):
            print(f"ℹ️ 今日 digest 已标记为跳过，跳过重复生成")
            write_push_result("skipped", "", "already skipped today", config)
            return None

    rss_result, gh_result, hn_result = await asyncio.gather(
        run_rss_section(config, now),
        run_github_section(config, now),
        run_hackernews_section(config, now),
    )

    # 早报场景:digest 的 metadata 通常会被 insights 段覆盖,
    # 但保留以便在 insights 失败时作为兜底来源(title 关键词 / lead / highlights)
    rss_md, digest_meta, rss_err = rss_result
    gh_md, gh_err = gh_result
    hn_md, hn_err = hn_result

    if gh_err:
        print(f"⚠️ [section_github] {gh_err}")
        await notify_llm_errors("section_github", [gh_err], config)
    if hn_err:
        print(f"⚠️ [section_hackernews] {hn_err}")
        await notify_llm_errors("section_hackernews", [hn_err], config)

    if rss_err and not rss_md:
        print(f"⚠️ [compose_digest] {rss_err}")
        await notify_llm_errors("compose_digest", [rss_err], config)
        raise RuntimeError(f"RSS section failed: {rss_err}")

    insights_md, metadata, insights_err = await run_insights_section(
        rss_md, gh_md, hn_md, config, now
    )
    if insights_err:
        print(f"⚠️ [insights] {insights_err}")
        await notify_llm_errors("insights", [insights_err], config)

    # 如果 insights 失败,优先用 digest metadata 兜底;两者都缺再走默认
    if not metadata:
        date_str = now.strftime("%Y-%m-%d")
        fallback = digest_meta or {}
        digest_title = fallback.get("title", "")

        title = digest_title if digest_title else f"📰 AI Daily 每日精选 | {date_str}"
        metadata = {
            "date": date_str,
            "pushTime": now.isoformat(),
            "title": title,
            "excerpt": "",
            "seotitle": "",
            "seodescription": "",
            "lead": fallback.get("lead", ""),
            "highlights": fallback.get("highlights", []),
            "profile": "morning",
        }
    else:
        metadata.setdefault("pushTime", now.isoformat())

    if digest_meta and digest_meta.get("entry_images"):
        metadata["entry_images"] = digest_meta["entry_images"]

    final = assemble_with_sentinels(
        {
            "rss": rss_md,
            "github": gh_md,
            "hackernews": hn_md,
            "insights": insights_md,
        }
    )

    if _should_skip_digest(config, final, rss_md or "", gh_md or "", hn_md or "", insights_md or ""):
        reason = "四段全空或低于 digest_min_items"
        print(f"ℹ️ 今日无值得推送的内容，跳过 digest（{reason}）")
        record_digest_skip(reason, config)
        write_push_result("skipped", "", reason, config)
        filt = config.get("filter", {})
        if filt.get("notify_on_empty_digest", True):
            await notify_digest_skipped(config, reason)
        return None

    push_file = get_push_file()
    metadata["push_file"] = push_file

    enrich_image_metadata(metadata, rss_md or final)
    metadata["sections"] = build_sections_manifest(
        {
            "rss": rss_md,
            "github": gh_md,
            "hackernews": hn_md,
            "insights": insights_md,
        }
    )

    rss_count = rss_md.count("###") if rss_md else 0
    save_push_file(
        push_file, final, rss_count, rss_count, profile="morning", metadata=metadata
    )
    print(f"💾 已保存日报到 {push_file}")
    record_digest_success(push_file, config)
    write_push_result("generated", push_file, "", config)

    if not generate_only:
        await send_to_platforms(
            final,
            config["push"],
            title="📰 AI Daily 早报 | " + metadata["title"],
            metadata=metadata,
        )
        print(f"✅ 日报 Push Job 完成 | RSS 条目: {rss_count}")
    else:
        print(f"✅ 日报 Push Job 完成（仅生成）| RSS 条目: {rss_count}")
    return push_file


async def send_digest_wecom(
    config: Dict,
    push_file: str,
    full_url: str = "",
) -> bool:
    """在完整版 URL 可访问后发送 digest 企微（news + 全文链接）。"""
    path = Path(push_file)
    if not path.exists():
        print(f"❌ push 文件不存在: {push_file}")
        return False

    with open(path, encoding="utf-8") as f:
        raw = f.read()
    metadata, body = parse_frontmatter(raw)
    if not metadata:
        metadata = {}
    metadata["push_file"] = push_file
    metadata["full_url"] = full_url

    digest_title = metadata.get("title", "AI Daily")
    await send_to_platforms(
        body,
        config["push"],
        title="📰 AI Daily 早报 | " + digest_title,
        metadata=metadata,
    )
    if full_url:
        print(f"✅ digest 企微已推送 | full_url={full_url}")
    else:
        print("✅ digest 企微已推送（无完整版链接，Pages 部署中）")
    return True


async def send_pages_delay_notice(config: Dict) -> None:
    """Pages 未就绪时追加说明 text。"""
    now = now_local(config).strftime("%Y-%m-%d %H:%M")
    text = (
        f"完整版阅读页正在部署，请稍后刷新站点。\n"
        f"时间：{now}"
    )
    wecom_conf = config.get("push", {}).get("wecom", {})
    if not wecom_conf.get("enabled"):
        return
    try:
        from src.push import create_platform

        platform = create_platform("wecom", wecom_conf)
        if platform is None:
            return
        await platform.send_text(text)
    except Exception as exc:
        print(f"⚠️ Pages 延迟说明发送失败: {exc}")


async def notify_digest_skipped(config: Dict, reason: str) -> None:
    """digest 静默跳过时发送可感知 text 通知。"""
    now = now_local(config).strftime("%Y-%m-%d %H:%M")
    text = f"📭 AI Daily 今日无 digest\n原因：{reason}\n时间：{now}"
    wecom_conf = config.get("push", {}).get("wecom", {})
    if not wecom_conf.get("enabled"):
        print(text)
        return
    try:
        from src.push import create_platform

        platform = create_platform("wecom", wecom_conf)
        if platform is None:
            print(text)
            return
        await platform.send_text(text)
        print("ℹ️ 已发送 digest 跳过通知到企微")
    except Exception as exc:
        print(f"⚠️ digest 跳过通知发送失败: {exc}")
        print(text)


async def notify_digest_url_unavailable(config: Dict, full_url: str) -> None:
    """完整版 URL 超时不可访问时发送告警 text（不含全文链接 digest）。"""
    now = now_local(config).strftime("%Y-%m-%d %H:%M")
    text = (
        f"今日精选推送稍有延迟，阅读页暂时无法打开，请稍后再试。\n"
        f"时间：{now}"
    )
    wecom_conf = config.get("push", {}).get("wecom", {})
    if not wecom_conf.get("enabled"):
        print(text)
        return
    try:
        from src.push import create_platform

        platform = create_platform("wecom", wecom_conf)
        if platform is None:
            print(text)
            return
        await platform.send_text(text)
        print("⚠️ 已发送 digest URL 不可用告警到企微")
    except Exception as exc:
        print(f"⚠️ digest URL 不可用告警发送失败: {exc}")
        print(text)


async def fetch_loop(config: Dict):
    """Fetch循环 - 修复时间漂移并支持优雅退出"""
    import time

    interval_seconds = config["schedule"]["fetch_interval_minutes"] * 60
    print(f"🔄 Fetch循环已启动 | 严格间隔: {interval_seconds / 60}分钟")

    while True:
        start_time = time.monotonic()  # 使用 monotonic 避免系统时间修改影响

        try:
            await run_fetch_job(config)
        except asyncio.CancelledError:
            print("⚠️ Fetch循环被外部取消，正在安全退出...")
            break  # 允许外部取消任务
        except Exception as e:
            print(f"❌ Fetch Job 失败: {e}")

        # 计算任务耗时
        elapsed = time.monotonic() - start_time
        # 计算还需要睡多久（如果任务耗时超过间隔，则不睡，立刻进入下一次）
        sleep_time = max(0.0, interval_seconds - elapsed)

        if sleep_time > 0:
            print(f"⏰ 下次抓取: {sleep_time / 60:.1f}分钟后")

        try:
            await asyncio.sleep(sleep_time)
        except asyncio.CancelledError:
            print("⚠️ 睡眠被中断，Fetch循环安全退出...")
            break


async def push_loop(config: Dict):
    """Push循环 - 无状态 croniter + 原生异步睡眠"""
    cron_list = config["schedule"]["push_cron"]
    tz = get_timezone(config)

    # 1. 启动前预校验 cron 表达式，过滤掉无效配置
    valid_crons = []
    for cron in cron_list:
        if croniter.is_valid(cron):
            valid_crons.append(cron)
        else:
            print(f"⚠️ 忽略无效的 cron 表达式: '{cron}'")

    if not valid_crons:
        print("❌ 没有有效的推送时间配置，Push循环退出")
        return

    print(f"📤 Push循环已启动 | 定时: {', '.join(valid_crons)} | 时区: {tz}")

    # 2. 主循环
    while True:
        try:
            now = datetime.now(tz)

            # 💡 核心优化：无状态计算。
            # 每次都基于此刻的真实时间，动态计算所有有效 cron 的下一次时间，取最近的一个。
            # 这样无论 run_push_job 执行多久，或者系统休眠过，永远都不会算错。
            next_push = min(
                croniter(cron, now).get_next(datetime) for cron in valid_crons
            )

            wait_seconds = (next_push - datetime.now(tz)).total_seconds()

            if wait_seconds > 0:
                print(
                    f"⏰ 下次推送: {next_push.strftime('%Y-%m-%d %H:%M:%S')} (等待 {wait_seconds / 60:.1f} 分钟)"
                )

                # 💡 核心优化：直接 Sleep。asyncio 天生支持被 CancelledError 瞬间打断
                await asyncio.sleep(wait_seconds)

            # 到达推送时间，执行推送
            print(f"📤 执行推送: {datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')}")
            await run_push_job(config)

            # 增加 1 秒缓冲：防止 run_push_job 执行过快（不到 1 秒），
            # 导致下一个循环的 now 仍停留在当前秒，croniter 算出重复的时间点。
            await asyncio.sleep(1)

        except asyncio.CancelledError:
            print("⚠️ Push循环收到取消信号，安全退出...")
            break  # 直接 break 退出循环即可
        except Exception as e:
            print(f"❌ Push 循环异常: {e}")
            # 遇到未知异常时休眠 60 秒，防止死循环疯狂报错打满日志
            await asyncio.sleep(60)


async def cmd_publish(config: Dict) -> tuple[int, str, str]:
    """清理旧 push、生成索引并 push 到 GitHub（触发 Pages）。"""
    from src.publish import publish_pages_to_github

    push_keep_days = config.get("filter", {}).get("push_keep_days", 30)
    wecom_config = config.get("push", {}).get("wecom", {})
    try:
        return publish_pages_to_github(
            push_keep_days=push_keep_days,
            wecom_config=wecom_config,
        )
    except subprocess.CalledProcessError as e:
        print(f"❌ 发布失败: {e}")
        return 1, "", ""


def cmd_commit_fetch(config: Dict) -> int:
    """提交 fetch/notify/trending 数据到 git（GHA hourly fetch 真源）。"""
    from src.publish import commit_fetch_to_github

    data_dir = config.get("data_dir", "news-data")
    return commit_fetch_to_github(data_dir=data_dir)


async def cmd_wecom(
    config: Dict,
    push_file: Optional[str] = None,
    skip_wait: bool = False,
    dry_run: bool = False,
    wait_timeout: int = 300,
    wait_interval: int = 10,
) -> int:
    """等待完整版 URL 可访问后发送 digest 企微。"""
    from src.publish import resolve_push_full_url, wait_for_url
    from src.push import set_dry_run

    if dry_run:
        set_dry_run(True)
        print("🔍 dry-run 模式：不实际发送 webhook")

    push_file = push_file or get_last_push_file()
    if not push_file:
        print("ℹ️ 无 push 文件，跳过 digest 企微")
        return 0

    wecom_config = config.get("push", {}).get("wecom", {})
    full_url = resolve_push_full_url(push_file, wecom_config)
    if not full_url:
        print("❌ 未配置 PAGES_BASE_URL / pages_base_url，无法生成完整版链接，跳过 digest 企微")
        await notify_digest_url_unavailable(config, full_url)
        return 1

    if not skip_wait and full_url:
        ok = await wait_for_url(full_url, timeout=wait_timeout, interval=wait_interval)
        if not ok:
            print("⚠️ Pages URL 不可用，降级推送 digest（无完整版链接）")
            try:
                await send_digest_wecom(config, push_file, "")
                await send_pages_delay_notice(config)
                return 0
            except Exception as e:
                print(f"❌ digest 降级推送失败: {e}")
                return 1

    try:
        await send_digest_wecom(config, push_file, full_url or "")
        return 0
    except Exception as e:
        print(f"❌ digest 企微推送失败: {e}")
        return 1


async def cmd_daily(
    config: Dict,
    skip_fetch: bool = False,
    skip_publish: bool = False,
    dry_run: bool = False,
) -> int:
    """一键：fetch → 生成 push md → publish → 等待 URL → 推 digest 企微。"""
    if not skip_fetch:
        code = await cmd_fetch(config)
        if code != 0:
            return code

    from src.push import set_dry_run

    if dry_run:
        set_dry_run(True)
        print("🔍 dry-run 模式：不实际发送 webhook、不 git push")

    push_file = None
    try:
        push_file = await run_push_job(config, generate_only=True)
    except Exception as e:
        print(f"❌ Push 任务失败: {e}")
        return 1

    if not push_file:
        print("ℹ️ 无 digest 内容，跳过后续 publish / 企微")
        return 0

    if dry_run:
        print(f"🔍 [dry-run] 将 publish 并等待 URL 后推送 digest: {push_file}")
        return 0

    if skip_publish:
        return await cmd_wecom(config, push_file=push_file)

    code, _, full_url = await cmd_publish(config)
    if code != 0:
        return code

    if not full_url:
        print("❌ publish 后无完整版 URL，跳过 digest 企微")
        await notify_digest_url_unavailable(config, full_url)
        return 1

    from src.publish import wait_for_url

    ok = await wait_for_url(full_url)
    if not ok:
        print("⚠️ Pages URL 不可用，降级推送 digest（无完整版链接）")
        try:
            await send_digest_wecom(config, push_file, "")
            await send_pages_delay_notice(config)
            return 0
        except Exception as e:
            print(f"❌ digest 降级推送失败: {e}")
            return 1

    try:
        await send_digest_wecom(config, push_file, full_url)
        return 0
    except Exception as e:
        print(f"❌ digest 企微推送失败: {e}")
        return 1


async def cmd_check(config: Dict) -> int:
    """校验 LLM 接口可达性（部署期使用，运行期不再校验）"""
    print("🔍 校验 LLM 接口...")
    try:
        await check_llm_available(config["llm"])
    except Exception as e:
        print(f"❌ LLM 接口不可用: {e}")
        return 1
    print("✅ LLM 接口可用")
    return 0


async def cmd_fetch(config: Dict) -> int:
    """单次抓取（systemd timer 调用）"""
    try:
        await run_fetch_job(config)
        record_fetch_success(config)
        return 0
    except Exception as e:
        print(f"❌ Fetch 任务失败: {e}")
        record_fetch_error(str(e), config)
        return 1


async def cmd_push(
    config: Dict,
    dry_run: bool = False,
    defer_wecom: bool = False,
    force: bool = False,
) -> int:
    """单次推送（systemd timer 调用）。"""
    from src.push import set_dry_run

    if dry_run:
        set_dry_run(True)
        print("🔍 dry-run 模式：不实际发送 webhook")
    try:
        push_file = await run_push_job(
            config, generate_only=defer_wecom, force=force
        )
        result = read_push_result()
        status = result.get("status", "generated" if push_file else "skipped")
        if status == "skipped":
            return EXIT_DIGEST_SKIPPED
        return 0
    except Exception as e:
        print(f"❌ Push 任务失败: {e}")
        record_digest_error(str(e), config)
        write_push_result("error", "", str(e), config)
        return 1


async def cmd_health_check(config: Dict) -> int:
    """检查今日 digest 是否已执行；失败时企微告警。"""
    ok, message = evaluate_daily_health(config)
    print(message)
    if ok:
        return 0
    wecom_conf = config.get("push", {}).get("wecom", {})
    alert_text = f"⚠️ AI Daily 健康检查失败\n{message}"
    if wecom_conf.get("enabled"):
        try:
            from src.push import create_platform

            platform = create_platform("wecom", wecom_conf)
            if platform:
                await platform.send_text(alert_text)
        except Exception as exc:
            print(f"⚠️ 健康检查告警发送失败: {exc}")
    else:
        print(alert_text)
    return 1


async def cmd_notify_skip(config: Dict) -> int:
    """根据 .last-push-result 发送 digest 跳过通知（GHA 专用）。"""
    result = read_push_result()
    if result.get("status") != "skipped":
        print("ℹ️ 最近一次 push 非 skipped，跳过 notify-skip")
        return 0
    reason = result.get("reason") or "无内容"
    await notify_digest_skipped(config, reason)
    return 0


async def cmd_loop(config: Dict) -> int:
    """长跑模式（本地开发/调试用）"""
    print("🔍 检查 LLM 接口可用性...")
    try:
        await check_llm_available(config["llm"])
        print("✅ LLM 接口可用")
    except Exception as e:
        print(f"❌ LLM 接口不可用: {e}")
        return 1
    await asyncio.gather(fetch_loop(config), push_loop(config))
    return 0


async def cmd_rss(config: Dict) -> int:
    """单独跑一次 RSS digest 板块,打印结果不推送"""
    print("📰 RSS Digest 单板块运行")
    try:
        md, meta, err = await run_rss_section(config, now=now_local(config))
    except Exception as e:
        print(f"❌ RSS 板块失败: {e}")
        return 1
    if err:
        print(f"❌ {err}")
        return 1
    if not md:
        print("ℹ️ 本次无内容")
        return 0
    print("\n" + "=" * 60)
    print("📑 metadata:")
    if meta:
        import json as _json

        print(_json.dumps(meta, ensure_ascii=False, indent=2))
    else:
        print("(none)")
    print("=" * 60)
    print(md)
    print("=" * 60)
    return 0


async def cmd_github(config: Dict) -> int:
    """单独跑一次 GitHub trending 板块,打印结果不推送"""
    print("⭐ GitHub Trending 单板块运行")
    try:
        md, err = await run_github_section(config, now=now_local(config))
    except Exception as e:
        print(f"❌ GitHub 板块失败: {e}")
        return 1
    if err:
        print(f"❌ {err}")
        return 1
    if not md:
        print("ℹ️ 本次无内容")
        return 0
    print("\n" + "=" * 60)
    print(md)
    print("=" * 60)
    return 0


async def cmd_hackernews(config: Dict) -> int:
    """单独跑一次 Hacker News 板块,打印结果不推送"""
    print("🟧 Hacker News 单板块运行")
    try:
        md, err = await run_hackernews_section(config, now=now_local(config))
    except Exception as e:
        print(f"❌ Hacker News 板块失败: {e}")
        return 1
    if err:
        print(f"❌ {err}")
        return 1
    if not md:
        print("ℹ️ 本次无内容")
        return 0
    print("\n" + "=" * 60)
    print(md)
    print("=" * 60)
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="daily-news",
        description="AI 每日资讯推送系统",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="校验 LLM 接口可达性")
    sub.add_parser("fetch", help="单次抓取并退出")
    push_parser = sub.add_parser("push", help="单次推送并退出")
    push_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅生成内容并打印推送计划，不实际发送 webhook",
    )
    push_parser.add_argument(
        "--defer-wecom",
        action="store_true",
        help="仅生成 push md，不发送 digest 企微（配合 publish + wecom 使用）",
    )
    push_parser.add_argument(
        "--force",
        action="store_true",
        help="忽略今日已有 digest/skip，强制重新生成",
    )
    daily_parser = sub.add_parser(
        "daily",
        help="一键：fetch + 生成 push + 发布 Pages + 等待 URL + 推 digest 企微",
    )
    daily_parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="跳过 fetch，仅 push + publish + 企微",
    )
    daily_parser.add_argument(
        "--skip-publish",
        action="store_true",
        help="跳过 git push（仅 fetch + 生成 push + 企微，需 URL 已可访问）",
    )
    daily_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="不发送 webhook、不 git push",
    )
    sub.add_parser("publish", help="清理旧 push 并 push 到 GitHub（触发 Pages）")
    sub.add_parser("commit-fetch", help="提交 fetch/notify/trending 数据到 git")
    sub.add_parser("health-check", help="检查今日 digest 是否已执行")
    sub.add_parser(
        "notify-skip",
        help="发送 digest 跳过通知（读取 .last-push-result.json）",
    )
    wecom_parser = sub.add_parser(
        "wecom",
        help="等待完整版 URL 可访问后发送 digest 企微",
    )
    wecom_parser.add_argument(
        "--push-file",
        default="",
        help="指定 push md 路径，默认取 news-data 下最新文件",
    )
    wecom_parser.add_argument(
        "--skip-wait",
        action="store_true",
        help="跳过 URL 轮询（本地调试或 URL 已确认可访问）",
    )
    wecom_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="不实际发送 webhook",
    )
    sub.add_parser("loop", help="长跑模式（开发/调试用）")
    sub.add_parser("rss", help="单独跑一次 RSS Digest 板块（仅打印,不推送）")
    sub.add_parser("github", help="单独跑一次 GitHub Trending 板块（仅打印,不推送）")
    sub.add_parser("hackernews", help="单独跑一次 Hacker News 板块（仅打印,不推送）")
    return parser.parse_args()


def main() -> int:
    print("🚀 AI每日资讯推送系统")
    args = _parse_args()

    try:
        config = load_config()
        print("✅ 配置加载成功")
    except Exception as e:
        print(f"❌ 加载配置失败: {e}")
        return 1

    handlers = {
        "check": cmd_check,
        "fetch": cmd_fetch,
        "loop": cmd_loop,
        "rss": cmd_rss,
        "github": cmd_github,
        "hackernews": cmd_hackernews,
    }

    if args.command == "push":
        return asyncio.run(
            cmd_push(
                config,
                dry_run=getattr(args, "dry_run", False),
                defer_wecom=getattr(args, "defer_wecom", False),
                force=getattr(args, "force", False),
            )
        )

    if args.command == "daily":
        return asyncio.run(
            cmd_daily(
                config,
                skip_fetch=getattr(args, "skip_fetch", False),
                skip_publish=getattr(args, "skip_publish", False),
                dry_run=getattr(args, "dry_run", False),
            )
        )

    if args.command == "publish":
        code, push_file, full_url = asyncio.run(cmd_publish(config))
        if push_file:
            print(f"[info] push_file: {push_file}")
        if full_url:
            print(f"[info] full_url: {full_url}")
        return code

    if args.command == "commit-fetch":
        return cmd_commit_fetch(config)

    if args.command == "health-check":
        return asyncio.run(cmd_health_check(config))

    if args.command == "notify-skip":
        return asyncio.run(cmd_notify_skip(config))

    if args.command == "wecom":
        return asyncio.run(
            cmd_wecom(
                config,
                push_file=getattr(args, "push_file", "") or None,
                skip_wait=getattr(args, "skip_wait", False),
                dry_run=getattr(args, "dry_run", False),
            )
        )

    return asyncio.run(handlers[args.command](config))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n👋 程序已退出")
        sys.exit(0)
