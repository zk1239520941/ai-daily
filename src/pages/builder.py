"""将 push-*.md 渲染为 GitHub Pages 静态 HTML 站点。"""

from __future__ import annotations

import html
import json
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import markdown

from src.markdown_utils import (
    extract_first_url,
    lookup_entry_image,
    normalize_str_list,
    parse_frontmatter,
)
from src.pages.parser import (
    SECTION_LABELS,
    has_sentinels,
    split_sentinel_sections,
    strip_leading_h2,
)

SITE_TITLE = "AI Daily"
SITE_INDEX_TITLE = "AI Daily · 每日精选"
SITE_HERO_HEADING = "AI 每日精选"
SITE_HERO_KICKER = "每日精选"
SITE_HERO_LEAD = "精选 AI 领域要闻。最新一期置顶，更多内容见下方。"
SITE_BACK_LINK = "← 返回首页"
SITE_EMPTY_STATE = "暂无内容，敬请期待。"
SITE_FOOTER = "AI Daily"
HOME_SSR_LIMIT = 30
ON_THIS_DAY_MAX = 5
FONT_LINK = (
    "https://fonts.googleapis.com/css2?"
    "family=IBM+Plex+Mono:wght@400;500&"
    "family=Inter:wght@400;500;600;700&"
    "family=Noto+Serif+SC:wght@500;600;700&display=swap"
)
_H3_SPLIT_RE = re.compile(r"(?=<h3>)")
_EMOJI_NUM_RE = re.compile(r"^[1-9]️⃣\s*")
_LEADING_NUM_RE = re.compile(r"^\d+[\.、]\s*")


def push_md_to_html_path(push_file: str) -> str:
    """将 push md 相对路径映射为 html 路径。"""
    normalized = push_file.replace("\\", "/").lstrip("./")
    if normalized.endswith(".md"):
        return normalized[:-3] + ".html"
    return normalized


def push_file_to_html_url(pages_base: str, push_file: str) -> str:
    """根据 Pages 根 URL 生成 HTML 全文链接。"""
    from urllib.parse import quote

    if not pages_base or not push_file:
        return ""
    rel = push_md_to_html_path(push_file)
    base = pages_base if pages_base.endswith("/") else pages_base + "/"
    return base + quote(rel, safe="/")


def parse_push_filename(filename: str) -> Dict[str, str]:
    """从 push-2026-06-30-17-00-30.md 解析展示用日期时间。"""
    stem = filename.replace("push-", "").replace(".md", "").replace(".html", "")
    parts = stem.split("-")
    if len(parts) >= 6:
        return {
            "date": f"{parts[0]}-{parts[1]}-{parts[2]}",
            "time": f"{parts[3]}:{parts[4]}",
            "display": f"{parts[0]}-{parts[1]}-{parts[2]} · {parts[3]}:{parts[4]}",
            "hour": parts[3],
        }
    return {"date": stem, "time": "", "display": stem, "hour": ""}


def _profile_label(profile: str, filename: str = "") -> str:
    """将 profile 字段转为中文标签，必要时按推送时间推断早晚报。"""
    key = (profile or "").strip().lower()
    if key == "morning":
        return "早报"
    if key in ("evening", "晚报"):
        return "晚报"

    parsed = parse_push_filename(filename) if filename else {}
    hour_raw = parsed.get("hour", "")
    if hour_raw.isdigit():
        return "早报" if int(hour_raw) < 12 else "晚报"
    if key == "default":
        return "晚报"
    return "精选"


def _format_article_time(meta: Dict[str, Any], filename: str) -> str:
    """优先 frontmatter 时间，否则用文件名。"""
    for key in ("pushDate", "pushTime", "date"):
        raw = meta.get(key)
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            return dt.strftime("%Y年%m月%d日 · %H:%M")
        except ValueError:
            if key == "date":
                return str(raw)
    parsed = parse_push_filename(filename)
    return parsed["display"]


def _beijing_tz() -> timezone:
    """北京时间（与 daily 定时任务一致）。"""
    return timezone(timedelta(hours=8))


def _latest_update_label(md_files: List[Path]) -> str:
    """取最新一期 push 的发布时间（北京时间）。"""
    if not md_files:
        return "—"
    latest = md_files[0]
    meta, _ = parse_frontmatter(latest.read_text(encoding="utf-8"))
    for key in ("pushDate", "pushTime"):
        raw = meta.get(key)
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            return dt.astimezone(_beijing_tz()).strftime("%Y-%m-%d %H:%M 北京时间")
        except ValueError:
            continue
    parsed = parse_push_filename(latest.name)
    if parsed.get("time"):
        return f"{parsed['date']} {parsed['time']} 北京时间"
    return parsed.get("date", "—")


def _clean_section_title(title: str) -> str:
    """去掉标题前的 emoji 序号或数字编号。"""
    text = title.strip()
    text = _EMOJI_NUM_RE.sub("", text)
    text = _LEADING_NUM_RE.sub("", text)
    return text.strip()


def _normalize_h3_titles(body_html: str) -> str:
    """清理 h3 标题中的重复序号。"""

    def _repl(match: re.Match[str]) -> str:
        raw = re.sub(r"<[^>]+>", "", match.group(1))
        return f"<h3>{html.escape(_clean_section_title(raw))}</h3>"

    return re.sub(r"<h3>(.*?)</h3>", _repl, body_html, flags=re.DOTALL)


def _markdown_to_html(body: str) -> str:
    """Markdown 正文转 HTML。"""
    return markdown.markdown(
        body,
        extensions=["extra", "nl2br", "sane_lists"],
        output_format="html5",
    )


def _enhance_article_body(body_html: str) -> str:
    """将每个 h3 章节包裹为带锚点的 story-block 卡片。"""
    text = body_html.strip()
    if not text:
        return text
    parts = _H3_SPLIT_RE.split(text)
    blocks: List[str] = []
    index = 0
    for part in parts:
        chunk = part.strip()
        if not chunk:
            continue
        if chunk.startswith("<h3>"):
            index += 1
            blocks.append(
                f'<section class="story-block reveal" id="story-{index}">{chunk}</section>'
            )
        else:
            blocks.append(chunk)
    return "\n".join(blocks)


def _render_figure(image_url: str) -> str:
    """渲染条目配图 figure（pretext 混排用）。"""
    safe_src = html.escape(image_url)
    return (
        f'<figure class="entry-figure pretext-figure">'
        f'<img src="{safe_src}" alt="" loading="lazy" '
        f'referrerpolicy="no-referrer" decoding="async"/>'
        f"</figure>"
    )


def _inject_entry_figures(body_html: str, entry_images: Dict[str, str]) -> str:
    """在 story-block 内首个链接命中 entry_images 时注入 figure 并 pretext 混排。"""
    if not body_html or not entry_images:
        return body_html

    block_index = 0

    def _inject_block(match: re.Match[str]) -> str:
        nonlocal block_index
        block_index += 1
        opening = match.group(1)
        block_html = match.group(2)
        closing = match.group(3)
        url = extract_first_url(block_html)
        image = lookup_entry_image(entry_images, url)
        if not image:
            return match.group(0)
        side = "right" if block_index % 2 == 1 else "left"
        figure = _render_figure(image)
        if "<h3>" in block_html:
            h3_end = block_html.find("</h3>") + len("</h3>")
            h3_part = block_html[:h3_end]
            body_part = block_html[h3_end:].strip()
            block_html = (
                f"{h3_part}"
                f'<div class="pretext-block pretext-{side}">'
                f"{figure}"
                f'<div class="story-prose">{body_part}</div>'
                f"</div>"
            )
        else:
            block_html = (
                f'<div class="pretext-block pretext-{side}">'
                f"{figure}"
                f'<div class="story-prose">{block_html}</div>'
                f"</div>"
            )
        return f"{opening}{block_html}{closing}"

    return re.sub(
        r'(<section class="story-block[^"]*"[^>]*>)(.*?)(</section>)',
        _inject_block,
        body_html,
        flags=re.DOTALL,
    )


def _section_body_html(section_md: str, entry_images: Dict[str, str]) -> str:
    """将 markdown 段转为 story-block HTML，并注入配图。"""
    rendered = _markdown_to_html(section_md)
    wrapped = _enhance_article_body(_normalize_h3_titles(rendered))
    return _inject_entry_figures(wrapped, entry_images)


def _format_sections_summary(meta: Dict[str, Any], compact: bool = False) -> str:
    """从 frontmatter sections 生成栏目摘要。"""
    sections_raw = meta.get("sections") or []
    if not isinstance(sections_raw, list):
        return ""

    short_labels = {
        "RSS 精选": "RSS",
        "GitHub 趋势": "GH",
        "Hacker News": "HN",
        "今日洞察": "洞察",
    }
    parts: List[str] = []
    for item in sections_raw:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        display = short_labels.get(label, label) if compact else label
        count = item.get("entry_count", 0)
        if isinstance(count, int) and count > 0:
            parts.append(f"{display}·{count}" if compact else f"{display} {count}")
        else:
            parts.append(display)
    return " · ".join(parts)


def _build_section_toc(body: str) -> str:
    """早报四段导航（sticky 锚点）。"""
    if not has_sentinels(body):
        return ""

    sections = split_sentinel_sections(body)
    if len(sections) < 2:
        return ""

    links: List[str] = []
    for key, section_md in sections:
        label = SECTION_LABELS.get(key, key)
        count = section_md.count("###") if key == "rss" or "###" in section_md else 0
        count_html = (
            f'<span class="article-toc__count">{count}</span>' if count else ""
        )
        links.append(
            f'<a class="article-toc__link" href="#board-{html.escape(key)}">'
            f"{html.escape(label)}{count_html}</a>"
        )

    inner = "".join(links)
    return (
        f'<nav class="article-toc reveal" aria-label="栏目导航">{inner}</nav>'
    )


def _collapse_hn_discussions(section_html: str) -> str:
    """HN 段：将「讨论总结」之后的内容折叠为 details。"""
    if not section_html:
        return section_html

    marker_re = re.compile(
        r"<p>\s*<strong>💬\s*讨论总结</strong>\s*</p>",
        re.IGNORECASE,
    )

    def _fold_block(match: re.Match[str]) -> str:
        opening, block_body, closing = match.group(1), match.group(2), match.group(3)
        hit = marker_re.search(block_body)
        if not hit:
            return match.group(0)
        before = block_body[: hit.start()]
        after = marker_re.sub("", block_body[hit.start() :], count=1)
        return (
            f"{opening}{before}"
            f'<details class="discussion-fold">'
            f"<summary>💬 讨论总结</summary>"
            f'<div class="discussion-fold__body">{after}</div>'
            f"</details>{closing}"
        )

    return re.sub(
        r'(<section class="story-block[^"]*"[^>]*>)(.*?)(</section>)',
        _fold_block,
        section_html,
        flags=re.DOTALL,
    )


def _render_article_body(body: str, entry_images: Dict[str, str]) -> str:
    """渲染正文：晚报 flat；早报按 sentinel 分栏。"""
    images = entry_images or {}
    if not has_sentinels(body):
        return _section_body_html(body, images)

    parts: List[str] = []
    for key, section_md in split_sentinel_sections(body):
        label = SECTION_LABELS.get(key, key)
        inner_md = section_md if key == "rss" else strip_leading_h2(section_md)
        if key == "rss" or "###" in inner_md:
            inner_html = _section_body_html(inner_md, images)
        else:
            inner_html = _markdown_to_html(inner_md)
        if key == "hackernews":
            inner_html = _collapse_hn_discussions(inner_html)
        parts.append(
            f'<section class="board-section board-{html.escape(key)} reveal" '
            f'id="board-{html.escape(key)}">'
            f'<header class="board-section__head">'
            f'<h2 class="board-section__title">{html.escape(label)}</h2>'
            f"</header>"
            f'<div class="board-section__body">{inner_html}</div>'
            f"</section>"
        )
    return "\n".join(parts)


def _html_head(title: str, css_href: str, cover_image: str = "") -> str:
    """生成页面 head 片段。"""
    safe_title = html.escape(title)
    og_image = ""
    if cover_image:
        og_image = (
            f'\n  <meta property="og:image" content="{html.escape(cover_image)}"/>'
        )
    return f"""<meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <meta name="color-scheme" content="light"/>
  <meta name="theme-color" content="#F5F5F2"/>
  <title>{safe_title}</title>{og_image}
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
  <link href="{html.escape(FONT_LINK)}" rel="stylesheet"/>
  <link rel="stylesheet" href="{html.escape(css_href)}"/>"""


def _site_nav_html(
    prefix: str = "",
    *,
    compact: bool = False,
    back_href: str = "",
    show_archive_links: bool = True,
) -> str:
    """生成站点导航栏 HTML。"""
    compact_class = " site-nav--compact" if compact else ""
    back = ""
    if compact or back_href:
        href = back_href or f"{prefix}index.html"
        back = f'<a class="back-link" href="{html.escape(href)}">{SITE_BACK_LINK}</a>'
    links = ""
    if show_archive_links and not compact:
        links = (
            f'<div class="site-nav__links">'
            f'<a href="{prefix}archive/index.html">归档浏览</a>'
            f'<a href="{prefix}search.html">搜索</a>'
            f"</div>"
        )
    return f"""    <nav class="site-nav{compact_class}">
      <div class="site-brand">
        <a href="{prefix}index.html">{html.escape(SITE_TITLE)}</a>
      </div>
      {links}
      {back}
    </nav>"""


def _render_on_this_day_html(items: List[Dict[str, Any]]) -> str:
    """渲染「往年今日」模块（无数据时返回空字符串）。"""
    if not items:
        return ""
    rows = []
    for item in items:
        rows.append(
            f'        <li class="on-this-day__item">'
            f'<a href="../{html.escape(item["url"])}">'
            f'<span class="on-this-day__year">{item["year"]}</span>'
            f'<span class="on-this-day__title">{html.escape(item["title"])}</span>'
            f"</a></li>"
        )
    return f"""    <section class="on-this-day reveal" aria-label="往年今日">
      <h2 class="on-this-day__heading">往年今日</h2>
      <ul class="on-this-day__list">
{chr(10).join(rows)}
      </ul>
      <p class="on-this-day__foot"><a href="../archive/index.html">浏览全部归档 →</a></p>
    </section>"""


def build_article_html(
    md_path: Path,
    css_href: str = "../static/pages.css",
    on_this_day: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """从 push md 生成单篇 HTML 页面。"""
    raw = md_path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(raw)
    title = str(meta.get("title") or SITE_TITLE)
    head_title = str(meta.get("seotitle") or title).strip() or title
    lead = str(meta.get("lead") or "").strip()
    highlights = normalize_str_list(meta.get("highlights"))
    profile = _profile_label(str(meta.get("profile") or ""), md_path.name)
    article_time = _format_article_time(meta, md_path.name)
    source_count = meta.get("sourceCount")
    total_entries = meta.get("totalEntries")

    stats_parts: List[str] = []
    if source_count:
        stats_parts.append(f"{source_count} 个来源")
    if total_entries:
        stats_parts.append(f"{total_entries} 条精选")
    stats_html = ""
    if stats_parts:
        pills = "".join(f"<span>{html.escape(p)}</span>" for p in stats_parts)
        stats_html = f'<div class="article-stats">{pills}</div>'

    section_summary = _format_sections_summary(meta)
    if section_summary:
        stats_html += (
            f'<div class="article-sections">{html.escape(section_summary)}</div>'
        )

    highlight_html = ""
    if highlights:
        tags = "".join(
            f"<span><i>{i + 1}</i>{html.escape(h)}</span>"
            for i, h in enumerate(highlights[:4])
        )
        highlight_html = f'<div class="highlight-tags">{tags}</div>'

    lead_html = f'<p class="article-lead">{html.escape(lead)}</p>' if lead else ""
    entry_images_raw = meta.get("entry_images") or {}
    entry_images = entry_images_raw if isinstance(entry_images_raw, dict) else {}
    cover_image = str(meta.get("cover_image") or "").strip()
    cover_html = ""
    if cover_image:
        cover_html = (
            f'<figure class="article-cover">'
            f'<img src="{html.escape(cover_image)}" alt="" loading="eager" '
            f'referrerpolicy="no-referrer" decoding="async"/>'
            f"</figure>"
        )
    body_html = _render_article_body(body, entry_images)
    section_toc = _build_section_toc(body)
    on_this_day_html = _render_on_this_day_html(on_this_day or [])

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  {_html_head(f"{head_title} · {SITE_TITLE}", css_href, cover_image=cover_image)}
</head>
<body class="article-page">
  <div id="reading-progress" class="reading-progress" aria-hidden="true"></div>
  <div class="site-shell">
{_site_nav_html("../", compact=True, back_href="../index.html", show_archive_links=False)}

    <article class="article-main">
      <header class="article-hero reveal">
        <div class="article-hero__top">
          <time datetime="{html.escape(article_time)}">{html.escape(article_time)}</time>
          <span class="article-edition">{html.escape(profile)}</span>
        </div>
        {cover_html}
        <h1>{html.escape(title)}</h1>
        {lead_html}
        {highlight_html}
        {stats_html}
      </header>

      {section_toc}

      <div class="article-body">
        {body_html}
      </div>
    </article>

{on_this_day_html}

    <footer class="site-footer">
      {html.escape(SITE_FOOTER)}
    </footer>
  </div>
  <script src="../static/pages.js" defer></script>
</body>
</html>
"""


def _load_issue_entry(md_path: Path, issue_no: int) -> Dict[str, Any]:
    """读取 md frontmatter 构建完整 issue 条目。"""
    raw = md_path.read_text(encoding="utf-8")
    meta, _ = parse_frontmatter(raw)
    parsed = parse_push_filename(md_path.name)
    html_name = md_path.with_suffix(".html").name
    lead = str(meta.get("lead") or "").strip()
    excerpt = lead[:180] + ("…" if len(lead) > 180 else "")
    if not excerpt:
        excerpt = "点击阅读全文"
    date = parsed["date"]
    month_day = date[5:10] if len(date) >= 10 else ""
    section_summary = _format_sections_summary(meta, compact=True)
    return {
        "id": md_path.stem,
        "date": date,
        "time": parsed.get("time", ""),
        "month_day": month_day,
        "title": str(meta.get("title") or parsed["display"]),
        "excerpt": excerpt,
        "lead": lead,
        "url": f"news-data/{html_name}",
        "cover": str(meta.get("cover_image") or "").strip(),
        "sections": section_summary,
        "issue_no": issue_no,
        "profile": _profile_label(str(meta.get("profile") or ""), md_path.name),
        "display": parsed["display"],
        "entries": str(meta.get("totalEntries") or ""),
        "section_summary": section_summary,
        "cover_image": str(meta.get("cover_image") or "").strip(),
        "href": f"news-data/{html_name}",
    }


def _load_issue_card(md_path: Path, issue_no: int = 0) -> Dict[str, str]:
    """读取 md frontmatter 构建索引卡片数据。"""
    entry = _load_issue_entry(md_path, issue_no)
    return {
        "title": entry["title"],
        "lead": entry["lead"],
        "profile": entry["profile"],
        "display": entry["display"],
        "href": entry["href"],
        "entries": entry["entries"],
        "cover_image": entry["cover_image"],
        "section_summary": entry["section_summary"],
    }


def _issue_json_record(issue: Dict[str, Any]) -> Dict[str, Any]:
    """提取写入 JSON 索引的字段。"""
    return {
        "id": issue["id"],
        "date": issue["date"],
        "time": issue["time"],
        "month_day": issue["month_day"],
        "title": issue["title"],
        "excerpt": issue["excerpt"],
        "url": issue["url"],
        "cover": issue["cover"],
        "sections": issue["sections"],
        "issue_no": issue["issue_no"],
        "profile": issue["profile"],
    }


def collect_all_issues(data_dir: Path) -> List[Dict[str, Any]]:
    """扫描 push-*.md 并返回倒序 issue 列表。"""
    md_files = sorted(data_dir.glob("push-*.md"), reverse=True)
    total = len(md_files)
    return [
        _load_issue_entry(md_path, issue_no=total - index)
        for index, md_path in enumerate(md_files)
    ]


def write_issues_json(data_dir: Path, issues: List[Dict[str, Any]]) -> None:
    """写入 issues-index.json 与按年拆分的 issues-YYYY.json。"""
    by_year: Dict[str, List[Dict[str, Any]]] = {}
    for issue in issues:
        year = issue["date"][:4]
        by_year.setdefault(year, []).append(_issue_json_record(issue))

    year_list = sorted(by_year.keys(), reverse=True)
    for year, year_issues in by_year.items():
        path = data_dir / f"issues-{year}.json"
        path.write_text(
            json.dumps(year_issues, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    index_data = {
        "title": SITE_TITLE,
        "total": len(issues),
        "years": year_list,
        "home_ssr_limit": HOME_SSR_LIMIT,
        "updated_at": issues[0]["display"] if issues else "",
    }
    (data_dir / "issues-index.json").write_text(
        json.dumps(index_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_on_this_day_json(data_dir: Path, issues: List[Dict[str, Any]]) -> None:
    """写入 on-this-day.json（键 MM-DD → 历史条目数组）。"""
    otd: Dict[str, List[Dict[str, Any]]] = {}
    for issue in issues:
        month_day = issue.get("month_day")
        if not month_day:
            continue
        otd.setdefault(month_day, []).append(
            {
                "year": int(issue["date"][:4]),
                "date": issue["date"],
                "title": issue["title"],
                "url": issue["url"],
            }
        )
    for items in otd.values():
        items.sort(key=lambda item: item["year"], reverse=True)
    (data_dir / "on-this-day.json").write_text(
        json.dumps(otd, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_on_this_day_items(
    issues: List[Dict[str, Any]],
    month_day: str,
    current_year: str,
    limit: int = ON_THIS_DAY_MAX,
) -> List[Dict[str, Any]]:
    """获取同月日历史条目（仅更早年份）。"""
    items: List[Dict[str, Any]] = []
    for issue in issues:
        if issue.get("month_day") != month_day:
            continue
        issue_year = issue["date"][:4]
        if issue_year >= current_year:
            continue
        items.append(
            {
                "year": int(issue_year),
                "date": issue["date"],
                "title": issue["title"],
                "url": issue["url"],
            }
        )
    items.sort(key=lambda item: item["year"], reverse=True)
    return items[:limit]


def _render_issue_card(
    issue: Dict[str, str], index: int, featured: bool = False, issue_no: int = 0
) -> str:
    """渲染单张索引卡片。"""
    excerpt = issue["lead"][:180] + ("…" if len(issue["lead"]) > 180 else "")
    if not excerpt:
        excerpt = "点击阅读全文"
    card_class = "issue-card issue-card--featured reveal" if featured else "issue-card reveal"
    entries = issue.get("entries", "")
    section_summary = issue.get("section_summary", "")
    meta_bits: List[str] = []
    if entries:
        meta_bits.append(f"{html.escape(entries)} 条精选")
    if section_summary:
        meta_bits.append(html.escape(section_summary))
    meta_extra = " · ".join(meta_bits)
    footer = f"{meta_extra}{' · ' if meta_extra else ''}阅读全文 →"
    cover = issue.get("cover_image", "")
    cover_block = ""
    if cover:
        cover_block = (
            f'<div class="issue-card__cover">'
            f'<img src="{html.escape(cover)}" alt="" loading="lazy" '
            f'referrerpolicy="no-referrer" decoding="async"/>'
            f"</div>"
        )

    if featured:
        return f"""    <article class="{card_class}">
      {cover_block}
      <div class="issue-card__inner">
        <div class="issue-card__main">
          <div class="issue-meta">
            <span class="issue-no">最新 · 第 {issue_no:03d} 期</span>
            <span class="issue-date">{html.escape(issue["display"])}</span>
            <span class="issue-badge">{html.escape(issue["profile"])}</span>
          </div>
          <h2><a href="{html.escape(issue["href"])}">{html.escape(issue["title"])}</a></h2>
          <p class="issue-excerpt">{html.escape(excerpt)}</p>
        </div>
        <div class="issue-card__cta">
          <a class="issue-read-btn" href="{html.escape(issue["href"])}">开始阅读</a>
          <span class="issue-footer">{html.escape(footer.replace(' · 阅读全文 →', ''))}</span>
        </div>
      </div>
    </article>"""

    return f"""    <article class="{card_class}" style="--i:{index}">
      {cover_block}
      <div class="issue-meta">
        <span class="issue-no">第 {issue_no:03d} 期</span>
        <span class="issue-date">{html.escape(issue["display"])}</span>
        <span class="issue-badge">{html.escape(issue["profile"])}</span>
      </div>
      <h2><a href="{html.escape(issue["href"])}">{html.escape(issue["title"])}</a></h2>
      <p class="issue-excerpt">{html.escape(excerpt)}</p>
      <div class="issue-footer">{html.escape(footer)}</div>
    </article>"""


def _render_compact_issue_card(issue: Dict[str, Any], index: int) -> str:
    """渲染归档月页精简卡片。"""
    meta_bits: List[str] = []
    if issue.get("entries"):
        meta_bits.append(f'{html.escape(str(issue["entries"]))} 条精选')
    if issue.get("sections"):
        meta_bits.append(html.escape(str(issue["sections"])))
    meta_extra = " · ".join(meta_bits)
    return f"""    <article class="archive-issue reveal" style="--i:{index}">
      <div class="archive-issue__meta">
        <span class="archive-issue__no">第 {issue["issue_no"]:03d} 期</span>
        <span class="archive-issue__date">{html.escape(issue["display"])}</span>
        <span class="archive-issue__badge">{html.escape(issue["profile"])}</span>
      </div>
      <h2><a href="../../{html.escape(issue["url"])}">{html.escape(issue["title"])}</a></h2>
      <p class="archive-issue__excerpt">{html.escape(issue["excerpt"])}</p>
      {f'<p class="archive-issue__foot">{meta_extra}</p>' if meta_extra else ""}
    </article>"""


def build_search_html(
    output: Path,
    total: int,
    issues: Optional[List[Dict[str, Any]]] = None,
    title: str = f"{SITE_TITLE} · 搜索",
) -> None:
    """生成 search.html 客户端搜索页。"""
    years = sorted({issue["date"][:4] for issue in (issues or [])}, reverse=True)
    index_data = {"total": total, "years": years}
    index_json = json.dumps(index_data, ensure_ascii=False)
    content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  {_html_head(title, "static/pages.css")}
</head>
<body class="search-page">
  <div class="site-shell">
{_site_nav_html("", compact=True, back_href="index.html")}

    <header class="page-header reveal">
      <h1>搜索日报</h1>
      <p class="page-lead">在 {total} 期精选中搜索标题与摘要。</p>
    </header>

    <div class="search-box reveal">
      <label class="search-box__label" for="search-input">关键词</label>
      <input id="search-input" class="search-box__input" type="search"
             placeholder="输入标题或摘要关键词…" autocomplete="off"/>
      <p class="search-box__hint" id="search-status" aria-live="polite">输入关键词开始搜索</p>
    </div>

    <section class="search-results" id="search-results" aria-live="polite"></section>

    <footer class="site-footer">
      共 {total} 期 · {html.escape(SITE_FOOTER)}
    </footer>
  </div>
  <script type="application/json" id="issues-index-data">{index_json}</script>
  <script src="static/pages.js" defer></script>
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")


def build_archive_pages(archive_root: Path, issues: List[Dict[str, Any]]) -> None:
    """生成 archive/index.html、archive/YYYY/index.html 与 archive/YYYY/MM.html。"""
    if archive_root.exists():
        shutil.rmtree(archive_root)
    archive_root.mkdir(parents=True, exist_ok=True)

    by_year: Dict[str, List[Dict[str, Any]]] = {}
    for issue in issues:
        by_year.setdefault(issue["date"][:4], []).append(issue)

    year_counts = {year: len(items) for year, items in by_year.items()}
    year_links = []
    for year in sorted(year_counts.keys(), reverse=True):
        count = year_counts[year]
        year_links.append(
            f'      <li class="archive-years__item reveal">'
            f'<a href="{html.escape(year)}/index.html">'
            f'<span class="archive-years__label">{html.escape(year)} 年</span>'
            f'<span class="archive-years__count">{count} 期</span>'
            f"</a></li>"
        )
    years_body = (
        "\n".join(year_links)
        if year_links
        else f'      <li class="empty-state">{html.escape(SITE_EMPTY_STATE)}</li>'
    )

    archive_index = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  {_html_head(f"{SITE_TITLE} · 归档", "../static/pages.css")}
</head>
<body class="archive-page">
  <div class="site-shell">
{_site_nav_html("../", compact=True, back_href="../index.html")}

    <header class="page-header reveal">
      <h1>归档浏览</h1>
      <p class="page-lead">按年份浏览全部 {len(issues)} 期 AI Daily 精选。</p>
    </header>

    <ul class="archive-years">
{years_body}
    </ul>

    <footer class="site-footer">
      共 {len(issues)} 期 · {html.escape(SITE_FOOTER)}
    </footer>
  </div>
  <script src="../static/pages.js" defer></script>
</body>
</html>
"""
    (archive_root / "index.html").write_text(archive_index, encoding="utf-8")

    month_names = [
        "一月", "二月", "三月", "四月", "五月", "六月",
        "七月", "八月", "九月", "十月", "十一月", "十二月",
    ]

    for year, year_issues in by_year.items():
        year_dir = archive_root / year
        year_dir.mkdir(parents=True, exist_ok=True)

        month_counts: Dict[str, int] = {}
        month_dates: Dict[str, List[str]] = {}
        for issue in year_issues:
            month = issue["date"][5:7]
            month_counts[month] = month_counts.get(month, 0) + 1
            day = issue["date"][8:10]
            month_dates.setdefault(month, [])
            if day not in month_dates[month]:
                month_dates[month].append(day)

        month_links = []
        for mm in range(1, 13):
            key = f"{mm:02d}"
            count = month_counts.get(key, 0)
            label = month_names[mm - 1]
            if count:
                month_links.append(
                    f'          <li class="archive-months__item">'
                    f'<a href="{key}.html">'
                    f'<span class="archive-months__label">{label}</span>'
                    f'<span class="archive-months__count">{count} 期</span>'
                    f"</a></li>"
                )
            else:
                month_links.append(
                    f'          <li class="archive-months__item archive-months__item--empty">'
                    f'<span class="archive-months__label">{label}</span>'
                    f'<span class="archive-months__count">—</span>'
                    f"</li>"
                )

        calendar_data = {
            "year": year,
            "months": {mm: sorted(days) for mm, days in month_dates.items()},
        }
        calendar_json = json.dumps(calendar_data, ensure_ascii=False)

        year_page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  {_html_head(f"{SITE_TITLE} · {year} 年归档", "../../static/pages.css")}
</head>
<body class="archive-page archive-year-page">
  <div class="site-shell">
{_site_nav_html("../../", compact=True, back_href="../../index.html")}

    <header class="page-header reveal">
      <p class="page-kicker"><a href="../index.html">归档</a> / {html.escape(year)}</p>
      <h1>{html.escape(year)} 年</h1>
      <p class="page-lead">共 {len(year_issues)} 期，可按月份列表或日历浏览。</p>
    </header>

    <div class="archive-tabs" id="archive-tabs" data-year="{html.escape(year)}">
      <div class="archive-tabs__bar" role="tablist" aria-label="归档视图">
        <button type="button" class="archive-tabs__btn is-active" role="tab"
                aria-selected="true" data-tab="list">列表</button>
        <button type="button" class="archive-tabs__btn" role="tab"
                aria-selected="false" data-tab="calendar">日历</button>
      </div>
      <div class="archive-tabs__panel is-active" data-panel="list" role="tabpanel">
        <ul class="archive-months">
{chr(10).join(month_links)}
        </ul>
      </div>
      <div class="archive-tabs__panel" data-panel="calendar" role="tabpanel" hidden>
        <div class="archive-calendar-toolbar">
          <label for="calendar-month-select">月份</label>
          <select id="calendar-month-select" class="archive-calendar-select"></select>
        </div>
        <div id="archive-calendar" class="archive-calendar" aria-label="月历"></div>
      </div>
    </div>

    <footer class="site-footer">
      {html.escape(year)} 年 · {len(year_issues)} 期
    </footer>
  </div>
  <script type="application/json" id="archive-year-data">{calendar_json}</script>
  <script src="../../static/pages.js" defer></script>
</body>
</html>
"""
        (year_dir / "index.html").write_text(year_page, encoding="utf-8")

        for month, count in month_counts.items():
            month_issues = [
                issue for issue in year_issues if issue["date"][5:7] == month
            ]
            cards = [
                _render_compact_issue_card(issue, index)
                for index, issue in enumerate(month_issues)
            ]
            month_label = month_names[int(month) - 1]
            month_page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  {_html_head(f"{SITE_TITLE} · {year} 年{month_label}", "../../static/pages.css")}
</head>
<body class="archive-page archive-month-page">
  <div class="site-shell">
{_site_nav_html("../../", compact=True, back_href="../../index.html")}

    <header class="page-header reveal">
      <p class="page-kicker">
        <a href="../index.html">归档</a> /
        <a href="index.html">{html.escape(year)}</a> /
        {html.escape(month_label)}
      </p>
      <h1>{html.escape(year)} 年 {html.escape(month_label)}</h1>
      <p class="page-lead">本月共 {count} 期。</p>
    </header>

    <section class="archive-issue-list">
{chr(10).join(cards) if cards else f'      <div class="empty-state">{html.escape(SITE_EMPTY_STATE)}</div>'}
    </section>

    <footer class="site-footer">
      <a href="index.html">← 返回 {html.escape(year)} 年归档</a>
    </footer>
  </div>
  <script src="../../static/pages.js" defer></script>
</body>
</html>
"""
            (year_dir / f"{month}.html").write_text(month_page, encoding="utf-8")


def build_index_html(
    data_dir: Path,
    output: Path,
    title: str = SITE_INDEX_TITLE,
    issues: Optional[List[Dict[str, Any]]] = None,
) -> int:
    """扫描 push-*.md 生成 index.html 与对应文章 HTML。"""
    if issues is None:
        issues = collect_all_issues(data_dir)

    ssr_issues = issues[:HOME_SSR_LIMIT]
    cards: List[str] = []
    for index, issue in enumerate(ssr_issues):
        cards.append(
            _render_issue_card(
                issue,
                index,
                featured=(index == 0),
                issue_no=issue["issue_no"],
            )
        )

    grid_body = (
        "\n".join(cards)
        if cards
        else f'    <div class="empty-state">{html.escape(SITE_EMPTY_STATE)}</div>'
    )

    md_files = [data_dir / f"{issue['id']}.md" for issue in issues]
    updated_at = _latest_update_label(md_files)
    latest_label = issues[0]["display"] if issues else "—"
    total = len(issues)
    has_more = total > HOME_SSR_LIMIT

    load_more_html = ""
    if has_more:
        load_more_html = f"""
    <div class="load-more-wrap reveal" id="load-more-wrap"
         data-shown="{HOME_SSR_LIMIT}" data-total="{total}">
      <button type="button" class="load-more-btn" id="load-more-btn">加载更多</button>
    </div>"""

    index_data = {
        "total": total,
        "years": sorted({issue["date"][:4] for issue in issues}, reverse=True),
        "home_ssr_limit": HOME_SSR_LIMIT,
    }
    index_json = json.dumps(index_data, ensure_ascii=False)

    content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  {_html_head(title, "static/pages.css")}
</head>
<body>
  <div class="site-shell">
{_site_nav_html("")}

    <header class="hero reveal">
      <div class="hero-copy">
        <span class="hero-kicker">{SITE_HERO_KICKER}</span>
        <h1>{html.escape(SITE_HERO_HEADING)}</h1>
        <p class="hero-lead">{html.escape(SITE_HERO_LEAD)}</p>
      </div>
      <aside class="hero-panel reveal" aria-label="站点概览">
        <dl>
          <dt>已发布</dt>
          <dd>{total} 期</dd>
          <dt>最近更新</dt>
          <dd>{html.escape(latest_label)}</dd>
        </dl>
      </aside>
    </header>

    <section class="issue-grid" id="issue-grid">
{grid_body}
    </section>
{load_more_html}

    <footer class="site-footer">
      共 {total} 篇精选 · 最近更新 {html.escape(updated_at)}
    </footer>
  </div>
  <script type="application/json" id="issues-index-data">{index_json}</script>
  <script src="static/pages.js" defer></script>
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    return total


def build_all_pages(
    data_dir: Path | str = "news-data",
    index_output: Path | str = "index.html",
    title: str = SITE_INDEX_TITLE,
    archive_root: Path | str | None = None,
    search_output: Path | str | None = None,
) -> int:
    """生成 index.html、JSON 索引、归档、搜索与全部 push-*.html。"""
    data_path = Path(data_dir)
    output_path = Path(index_output)
    site_root = output_path.parent
    archive_path = Path(archive_root) if archive_root else site_root / "archive"
    search_path = Path(search_output) if search_output else site_root / "search.html"

    issues = collect_all_issues(data_path)
    write_issues_json(data_path, issues)
    write_on_this_day_json(data_path, issues)

    for issue in issues:
        md_path = data_path / f"{issue['id']}.md"
        otd = get_on_this_day_items(
            issues,
            issue.get("month_day", ""),
            issue["date"][:4],
        )
        html_path = data_path / f"{issue['id']}.html"
        html_path.write_text(
            build_article_html(md_path, on_this_day=otd),
            encoding="utf-8",
        )

    count = build_index_html(data_path, output_path, title=title, issues=issues)
    build_search_html(search_path, total=count, issues=issues)
    build_archive_pages(archive_path, issues)
    print(
        f"[OK] 已生成 {output_path}、归档、搜索与 {count} 篇 HTML 日报"
    )
    return count


def cleanup_orphan_html(data_dir: Path | str = "news-data") -> int:
    """删除没有对应 md 的 push-*.html。"""
    data_path = Path(data_dir)
    removed = 0
    for html_file in data_path.glob("push-*.html"):
        if not html_file.with_suffix(".md").exists():
            html_file.unlink()
            removed += 1
    return removed
