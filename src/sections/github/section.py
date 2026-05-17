"""GitHub Trending 板块入口。

流程:trending 抓取 → history 过滤 → 候选写回 history → deep-dive → LLM 总结
"""

from datetime import datetime
from typing import Dict, Optional, Tuple

from src.config import get_timezone
from src.sections.github.repo_enricher import enrich_repos
from src.sections.github.trending_scraper import (
    fetch_trending_page,
    parse_trending_html,
)
from src.storage import load_trending_history


async def run_github_section(
    config: Dict, now: Optional[datetime] = None
) -> Tuple[str, Optional[str]]:
    cfg = config.get("sections", {}).get("github_trending", {})
    if not cfg.get("enabled", False):
        return "", None

    # 延迟 import,Task 11 才提供 summarize_github_trending
    from src.llm import summarize_github_trending

    today = (now or datetime.now(get_timezone())).date()
    keep_days = config["filter"]["keep_days"]
    timeout = cfg.get("request_timeout", 10)
    max_deep_dive = cfg.get("max_deep_dive", 10)
    readme_max_chars = cfg.get("readme_max_chars", 3000)
    history_path = cfg.get("history_file", "news-data/trending-history.json")
    token_env = cfg.get("tokenName", "GITHUB_TOKEN")

    # 1. 抓取
    try:
        html = await fetch_trending_page(timeout=timeout)
    except Exception as e:
        return "", f"GH 抓取失败: {e}"

    all_repos = parse_trending_html(html)
    if not all_repos:
        return "", None

    # 2. history 加载 + 清理
    history = load_trending_history(history_path)
    history.cleanup(today=today, keep_days=keep_days)

    # 3. 候选筛选(按 spec §4.3 语义)
    candidates = []
    for repo in all_repos:
        if repo["url"] in history:
            history.touch(repo["url"], today)
        else:
            candidates.append(repo)

    # 4. 候选写回 history + 持久化
    for repo in candidates:
        history.touch(repo["url"], today)
    history.save()

    if not candidates:
        return "", None
    if len(candidates) > max_deep_dive:
        candidates = candidates[:max_deep_dive]

    # 5. 并发 enrich
    enriched, enrich_errors = await enrich_repos(
        candidates,
        token_env=token_env,
        readme_max_chars=readme_max_chars,
        timeout=timeout,
    )
    for e in enrich_errors:
        print(f"⚠️ GH enrich: {e}")
    if not enriched:
        return "", None

    # 6. LLM 总结
    md, err = await summarize_github_trending(enriched, config["llm"])
    if err:
        return "", f"summarize_github_trending: {err}"
    return md or "", None
