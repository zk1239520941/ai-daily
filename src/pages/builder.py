"""将 push-*.md 渲染为 GitHub Pages 静态 HTML 站点。"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import markdown

from src.markdown_utils import normalize_str_list, parse_frontmatter

SITE_TITLE = "AI Daily"
SITE_TAGLINE = "精选 AI 资讯 · 技术委员会内部分享"
FONT_LINK = (
    "https://fonts.googleapis.com/css2?"
    "family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;1,9..40,400&"
    "family=Instrument+Serif:ital@0;1&"
    "family=Noto+Serif+SC:wght@400;600&display=swap"
)


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
        }
    return {"date": stem, "time": "", "display": stem}


def _profile_label(profile: str) -> str:
    """将 profile 字段转为中文标签。"""
    mapping = {
        "morning": "早报",
        "default": "晚报",
        "evening": "晚报",
    }
    return mapping.get((profile or "").strip(), "精选")


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


def _html_head(title: str, css_href: str) -> str:
    """生成页面 head 片段。"""
    safe_title = html.escape(title)
    return f"""<meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <meta name="color-scheme" content="dark"/>
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
    profile = _profile_label(str(meta.get("profile") or ""))
    article_time = _format_article_time(meta, md_path.name)
    source_count = meta.get("sourceCount")
    total_entries = meta.get("totalEntries")

    stats_parts: List[str] = []
    if source_count:
        stats_parts.append(f"{source_count} 个来源")
    if total_entries:
        stats_parts.append(f"{total_entries} 条精选")
    stats_parts.append(profile)
    stats_html = " · ".join(html.escape(p) for p in stats_parts)

    highlight_html = ""
    if highlights:
        tags = "".join(f"<span>{html.escape(h)}</span>" for h in highlights[:4])
        highlight_html = f'<div class="highlight-tags">{tags}</div>'

    lead_html = (
        f'<p class="article-lead">{html.escape(lead)}</p>' if lead else ""
    )
    body_html = _markdown_to_html(body)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  {_html_head(f"{title} · {SITE_TITLE}", css_href)}
</head>
<body class="article-page">
  <div class="site-shell">
    <nav class="site-nav">
      <div class="site-brand">
        <a href="../index.html">{html.escape(SITE_TITLE)}</a>
        <span>{html.escape(SITE_TAGLINE)}</span>
      </div>
      <a class="back-link" href="../index.html">← 返回归档</a>
    </nav>

    <header class="article-hero">
      <time datetime="{html.escape(article_time)}">{html.escape(article_time)}</time>
      <h1>{html.escape(title)}</h1>
      {lead_html}
      {highlight_html}
      <div class="article-stats">{stats_html}</div>
    </header>

    <div class="article-body">
      {body_html}
    </div>

    <footer class="site-footer">
      {html.escape(SITE_TITLE)} · 由 AI Daily 自动生成
    </footer>
  </div>
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
        "profile": _profile_label(str(meta.get("profile") or "")),
        "display": parsed["display"],
        "href": f"news-data/{html_name}",
    }


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
        html_path.write_text(
            build_article_html(md_path),
            encoding="utf-8",
        )

        excerpt = html.escape(issue["lead"][:180] + ("…" if len(issue["lead"]) > 180 else ""))
        if not issue["lead"]:
            excerpt = "点击进入阅读完整日报"

        cards.append(
            f"""    <article class="issue-card" style="animation-delay:{0.05 + index * 0.05:.2f}s">
      <div class="issue-meta">
        <span class="issue-date">{html.escape(issue["display"])}</span>
        <span class="issue-badge">{html.escape(issue["profile"])}</span>
      </div>
      <h2><a href="{html.escape(issue["href"])}">{html.escape(issue["title"])}</a></h2>
      <p class="issue-excerpt">{excerpt}</p>
      <div class="issue-footer">阅读全文 →</div>
    </article>"""
        )

    grid_body = "\n".join(cards) if cards else '    <div class="empty-state">暂无日报，等待 AI Daily 定时任务生成</div>'
    built_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

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

    <header class="hero">
      <span class="hero-kicker">Daily Briefing</span>
      <h1>{html.escape(title)}</h1>
      <p class="hero-lead">每日 AI 精选摘要，面向技术分享与内部分发。点击卡片阅读排版后的完整日报。</p>
    </header>

    <section class="issue-grid">
{grid_body}
    </section>

    <footer class="site-footer">
      共 {len(md_files)} 篇日报 · 更新于 {html.escape(built_at)}
    </footer>
  </div>
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
