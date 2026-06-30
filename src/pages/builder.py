"""将 push-*.md 渲染为 GitHub Pages 静态 HTML 站点。"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import markdown

from src.markdown_utils import normalize_str_list, parse_frontmatter

SITE_TITLE = "AI Daily"
SITE_TAGLINE = "精选 AI 资讯 · 技术委员会内部分享"
FONT_LINK = (
    "https://fonts.googleapis.com/css2?"
    "family=IBM+Plex+Mono:wght@400;500&"
    "family=Noto+Serif+SC:wght@500;600;700&"
    "family=Playfair+Display:ital,wght@0,500;0,600;0,700;1,500&"
    "family=Sora:wght@400;500;600&display=swap"
)
_H3_SPLIT_RE = re.compile(r"(?=<h3>)")


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


def _markdown_to_html(body: str) -> str:
    """Markdown 正文转 HTML。"""
    return markdown.markdown(
        body,
        extensions=["extra", "nl2br", "sane_lists"],
        output_format="html5",
    )


def _extract_section_titles(body: str) -> List[str]:
    """从 markdown 正文提取 ### 章节标题。"""
    titles: List[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("### "):
            titles.append(stripped[4:].strip())
    return titles


def _build_toc_html(titles: List[str]) -> str:
    """生成文章目录 HTML。"""
    if not titles:
        return ""
    items = []
    for index, title in enumerate(titles, 1):
        safe = html.escape(title)
        items.append(
            f'<li><a href="#story-{index}"><span>{index:02d}</span>{safe}</a></li>'
        )
    return f"""<aside class="article-toc reveal" aria-label="本日目录">
      <p class="toc-label">本日目录</p>
      <ol>{"".join(items)}</ol>
    </aside>"""


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


def _html_head(title: str, css_href: str) -> str:
    """生成页面 head 片段。"""
    safe_title = html.escape(title)
    return f"""<meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <meta name="color-scheme" content="light"/>
  <meta name="theme-color" content="#f6f2ea"/>
  <title>{safe_title}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
  <link href="{html.escape(FONT_LINK)}" rel="stylesheet"/>
  <link rel="stylesheet" href="{html.escape(css_href)}"/>"""


def build_article_html(md_path: Path, css_href: str = "../static/pages.css") -> str:
    """从 push md 生成单篇 HTML 页面。"""
    raw = md_path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(raw)
    title = str(meta.get("title") or SITE_TITLE)
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
    stats_parts.append(profile)
    stats_html = ""
    if stats_parts:
        pills = "".join(f"<span>{html.escape(p)}</span>" for p in stats_parts)
        stats_html = f'<div class="article-stats">{pills}</div>'

    highlight_html = ""
    if highlights:
        tags = "".join(
            f"<span><i>{i + 1}</i>{html.escape(h)}</span>"
            for i, h in enumerate(highlights[:4])
        )
        highlight_html = f'<div class="highlight-tags">{tags}</div>'

    lead_html = f'<p class="article-lead">{html.escape(lead)}</p>' if lead else ""
    toc_html = _build_toc_html(_extract_section_titles(body))
    body_html = _enhance_article_body(_markdown_to_html(body))

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  {_html_head(f"{title} · {SITE_TITLE}", css_href)}
</head>
<body class="article-page">
  <div id="reading-progress" class="reading-progress" aria-hidden="true"></div>
  <div class="site-shell">
    <nav class="site-nav">
      <div class="site-brand">
        <a href="../index.html">{html.escape(SITE_TITLE)}</a>
        <span>{html.escape(SITE_TAGLINE)}</span>
      </div>
      <a class="back-link" href="../index.html">← 返回归档</a>
    </nav>

    <header class="article-hero reveal">
      <div class="article-hero__top">
        <time datetime="{html.escape(article_time)}">{html.escape(article_time)}</time>
        <span class="article-edition">{html.escape(profile)}</span>
      </div>
      <h1>{html.escape(title)}</h1>
      {lead_html}
      {highlight_html}
      {stats_html}
    </header>

    <div class="article-layout">
      {toc_html}
      <div class="article-body">
        {body_html}
      </div>
    </div>

    <footer class="site-footer">
      {html.escape(SITE_TITLE)} · 由 AI Daily 自动生成
    </footer>
  </div>
  <script src="../static/pages.js" defer></script>
</body>
</html>
"""


def _load_issue_card(md_path: Path) -> Dict[str, str]:
    """读取 md frontmatter 构建索引卡片数据。"""
    raw = md_path.read_text(encoding="utf-8")
    meta, _ = parse_frontmatter(raw)
    parsed = parse_push_filename(md_path.name)
    html_name = md_path.with_suffix(".html").name
    return {
        "title": str(meta.get("title") or parsed["display"]),
        "lead": str(meta.get("lead") or "").strip(),
        "profile": _profile_label(str(meta.get("profile") or ""), md_path.name),
        "display": parsed["display"],
        "href": f"news-data/{html_name}",
        "entries": str(meta.get("totalEntries") or ""),
    }


def _render_issue_card(
    issue: Dict[str, str], index: int, featured: bool = False, issue_no: int = 0
) -> str:
    """渲染单张索引卡片。"""
    excerpt = issue["lead"][:180] + ("…" if len(issue["lead"]) > 180 else "")
    if not excerpt:
        excerpt = "点击进入阅读完整日报"
    card_class = "issue-card issue-card--featured reveal" if featured else "issue-card reveal"
    entries = issue.get("entries", "")
    meta_extra = f"{html.escape(entries)} 条精选" if entries else ""
    footer = f"{meta_extra}{' · ' if meta_extra else ''}阅读全文 →"

    if featured:
        return f"""    <article class="{card_class}">
      <div class="issue-card__inner">
        <div class="issue-card__main">
          <div class="issue-meta">
            <span class="issue-no">Latest · No.{issue_no:03d}</span>
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
      <div class="issue-meta">
        <span class="issue-no">No.{issue_no:03d}</span>
        <span class="issue-date">{html.escape(issue["display"])}</span>
        <span class="issue-badge">{html.escape(issue["profile"])}</span>
      </div>
      <h2><a href="{html.escape(issue["href"])}">{html.escape(issue["title"])}</a></h2>
      <p class="issue-excerpt">{html.escape(excerpt)}</p>
      <div class="issue-footer">{html.escape(footer)}</div>
    </article>"""


def build_index_html(
    data_dir: Path,
    output: Path,
    title: str = f"{SITE_TITLE} 日报归档",
) -> int:
    """扫描 push-*.md 生成 index.html 与对应文章 HTML。"""
    md_files = sorted(data_dir.glob("push-*.md"), reverse=True)
    cards: List[str] = []

    for index, md_path in enumerate(md_files):
        issue = _load_issue_card(md_path)
        html_path = md_path.with_suffix(".html")
        html_path.write_text(build_article_html(md_path), encoding="utf-8")
        cards.append(
            _render_issue_card(
                issue,
                index,
                featured=(index == 0),
                issue_no=len(md_files) - index,
            )
        )

    grid_body = (
        "\n".join(cards)
        if cards
        else '    <div class="empty-state">暂无日报，等待 AI Daily 定时任务生成</div>'
    )
    built_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    latest_label = _load_issue_card(md_files[0])["display"] if md_files else "—"

    content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  {_html_head(title, "static/pages.css")}
</head>
<body>
  <div class="site-shell">
    <nav class="site-nav">
      <div class="site-brand">
        <a href="index.html">{html.escape(SITE_TITLE)}</a>
        <span>{html.escape(SITE_TAGLINE)}</span>
      </div>
    </nav>

    <header class="hero reveal">
      <div class="hero-copy">
        <span class="hero-kicker">Daily Briefing</span>
        <h1>{html.escape(title)}</h1>
        <p class="hero-lead">每日 AI 精选摘要，面向技术分享与内部分发。最新一期置顶展示，往期归档于下方。</p>
      </div>
      <aside class="hero-panel reveal" aria-label="归档概览">
        <dl>
          <dt>已归档</dt>
          <dd>{len(md_files)} 期</dd>
          <dt>最新更新</dt>
          <dd>{html.escape(latest_label)}</dd>
        </dl>
      </aside>
    </header>

    <section class="issue-grid">
{grid_body}
    </section>

    <footer class="site-footer">
      共 {len(md_files)} 篇日报 · 更新于 {html.escape(built_at)}
    </footer>
  </div>
  <script src="static/pages.js" defer></script>
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    return len(md_files)


def build_all_pages(
    data_dir: Path | str = "news-data",
    index_output: Path | str = "index.html",
    title: str = f"{SITE_TITLE} 日报归档",
) -> int:
    """生成 index.html 与全部 push-*.html。"""
    data_path = Path(data_dir)
    output_path = Path(index_output)
    count = build_index_html(data_path, output_path, title=title)
    print(f"[OK] 已生成 {output_path} 与 {count} 篇 HTML 日报")
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
