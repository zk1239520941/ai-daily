"""Pages 静态站点生成测试。"""

import json
import re
from pathlib import Path

from src.pages.builder import (
    HOME_SSR_LIMIT,
    build_all_pages,
    build_article_html,
    collect_all_issues,
    get_on_this_day_items,
    parse_push_filename,
    push_file_to_html_url,
    push_md_to_html_path,
    write_issues_json,
    write_on_this_day_json,
)
from src.push.wecom import build_push_page_url


def test_push_md_to_html_path():
    assert push_md_to_html_path("news-data/push-2026-06-30-17-00-30.md") == (
        "news-data/push-2026-06-30-17-00-30.html"
    )


def test_push_file_to_html_url():
    url = push_file_to_html_url(
        "https://example.github.io/ai-daily/",
        "news-data/push-2026-06-30-17-00-30.md",
    )
    assert url.endswith("news-data/push-2026-06-30-17-00-30.html")


def test_build_push_page_url_uses_html():
    url = build_push_page_url(
        "https://pages.example/",
        "news-data/push-2026-06-30-17-00-30.md",
    )
    assert url.endswith(".html")
    assert ".md" not in url


def test_parse_push_filename():
    parsed = parse_push_filename("push-2026-06-30-17-00-30.md")
    assert parsed["date"] == "2026-06-30"
    assert parsed["time"] == "17:00"
    assert "17:00" in parsed["display"]


def test_clean_section_title():
    from src.pages.builder import _clean_section_title

    assert _clean_section_title("1️⃣ Anthropic 洽谈") == "Anthropic 洽谈"
    assert _clean_section_title("1. AWS 发布") == "AWS 发布"


def test_build_article_html(tmp_path):
    md = tmp_path / "push-2026-06-30-18-00-00.md"
    md.write_text(
        """---
title: "测试标题"
lead: "测试导语"
highlights: ["要点一", "要点二"]
profile: "morning"
date: "2026-06-30"
sourceCount: 3
totalEntries: 5
---

### 第一条

* **亮点**：内容
* 🔗 [链接](https://example.com)
""",
        encoding="utf-8",
    )
    html_out = build_article_html(md, css_href="../static/pages.css")
    assert "测试标题" in html_out
    assert "测试导语" in html_out
    assert "要点一" in html_out
    assert "story-block" in html_out
    assert "article-toc" not in html_out
    assert "reading-progress" in html_out
    assert "https://example.com" in html_out
    assert "早报" in html_out


def test_build_article_html_with_images_and_sentinel(tmp_path):
    md = tmp_path / "push-morning.md"
    md.write_text(
        """---
title: "早报测试"
lead: "导语"
profile: "morning"
entry_images:
  "https://example.com/rss": "https://img.example/rss.jpg"
cover_image: "https://img.example/rss.jpg"
---

<!-- SECTION:rss BEGIN -->
### RSS条
* 🔗 [链](https://example.com/rss)
<!-- SECTION:rss END -->

<!-- SECTION:github BEGIN -->
## ⭐ GitHub 趋势
- **foo/bar** — desc
<!-- SECTION:github END -->
""",
        encoding="utf-8",
    )
    html_out = build_article_html(md, css_href="../static/pages.css")
    assert "board-section" in html_out
    assert "RSS 精选" in html_out
    assert "GitHub 趋势" in html_out
    assert "article-toc" in html_out
    assert 'id="board-rss"' in html_out
    assert "entry-figure" in html_out
    assert "article-cover" in html_out
    assert "<!-- SECTION:" not in html_out


def test_build_article_html_seotitle_and_sections(tmp_path):
    md = tmp_path / "push-seo.md"
    md.write_text(
        """---
title: "很长很长很长的新闻标题用于页面展示"
seotitle: "短标题"
sections:
  - id: rss
    label: RSS 精选
    entry_count: 4
  - id: github
    label: GitHub 趋势
    entry_count: 3
---

<!-- SECTION:rss BEGIN -->
### 一条
* 内容
<!-- SECTION:rss END -->

<!-- SECTION:github BEGIN -->
## GH
### 项目
* 描述
<!-- SECTION:github END -->
""",
        encoding="utf-8",
    )
    html_out = build_article_html(md, css_href="../static/pages.css")
    assert "<title>短标题 · AI Daily</title>" in html_out
    assert "很长很长很长的新闻标题" in html_out
    assert "RSS 精选 4" in html_out


def test_collapse_hn_discussions():
    from src.pages.builder import _collapse_hn_discussions

    raw = (
        '<section class="story-block" id="story-1">'
        "<h3>标题</h3><ul><li>摘要</li></ul>"
        "<p><strong>💬 讨论总结</strong></p>"
        "<ul><li>观点一</li></ul>"
        "</section>"
    )
    folded = _collapse_hn_discussions(raw)
    assert "discussion-fold" in folded
    assert "观点一" in folded
    assert "<p><strong>💬 讨论总结</strong></p>" not in folded


def test_latest_update_label_uses_beijing_time(tmp_path):
    from src.pages.builder import _latest_update_label

    md = tmp_path / "push-2026-06-30-18-18-19.md"
    md.write_text(
        """---
pushDate: "2026-06-30T18:18:19.579841+08:00"
---
body
""",
        encoding="utf-8",
    )
    label = _latest_update_label([md])
    assert "北京时间" in label
    assert "18:18" in label
    assert "UTC" not in label

    from src.pages.builder import _profile_label

    assert _profile_label("default", "push-2026-06-30-08-00-00.md") == "早报"
    assert _profile_label("default", "push-2026-06-30-18-00-00.md") == "晚报"


def test_build_all_pages(tmp_path):
    data_dir = tmp_path / "news-data"
    data_dir.mkdir()
    (data_dir / "push-2026-06-30-17-00-00.md").write_text(
        """---
title: "归档测试"
lead: "导语"
profile: "default"
date: "2026-06-30"
cover_image: "https://img.example/cover.jpg"
entry_images:
  "https://example.com/x": "https://img.example/x.jpg"
---

### 章节

* 🔗 [链](https://example.com/x)
""",
        encoding="utf-8",
    )
    index = tmp_path / "index.html"
    count = build_all_pages(data_dir=data_dir, index_output=index)
    assert count == 1
    assert index.exists()
    assert (data_dir / "push-2026-06-30-17-00-00.html").exists()
    index_text = index.read_text(encoding="utf-8")
    assert "归档测试" in index_text
    assert "issue-card--featured" in index_text
    assert "news-data/push-2026-06-30-17-00-00.html" in index_text
    assert "issue-card__cover" in index_text
    assert "archive/index.html" in index_text
    assert "search.html" in index_text
    assert (tmp_path / "search.html").exists()
    assert (tmp_path / "archive" / "index.html").exists()
    assert (data_dir / "issues-index.json").exists()
    assert (data_dir / "issues-2026.json").exists()
    assert (data_dir / "on-this-day.json").exists()


def test_home_ssr_limit(tmp_path):
    """首页只 SSR 最近 N 期，其余通过 JSON 按需加载。"""
    data_dir = tmp_path / "news-data"
    data_dir.mkdir()
    for day in range(1, HOME_SSR_LIMIT + 5):
        (data_dir / f"push-2026-07-{day:02d}-10-00-00.md").write_text(
            f"""---
title: "第 {day} 期"
lead: "导语 {day}"
profile: morning
date: "2026-07-{day:02d}"
---

### 内容
""",
            encoding="utf-8",
        )
    index = tmp_path / "index.html"
    build_all_pages(data_dir=data_dir, index_output=index)
    index_text = index.read_text(encoding="utf-8")
    assert len(re.findall(r'<article class="issue-card', index_text)) == HOME_SSR_LIMIT
    assert "load-more-btn" in index_text
    assert f'data-total="{HOME_SSR_LIMIT + 4}"' in index_text
    index_data = json.loads(
        index_text.split('id="issues-index-data">')[1].split("</script>")[0]
    )
    assert index_data["total"] == HOME_SSR_LIMIT + 4
    assert index_data["home_ssr_limit"] == HOME_SSR_LIMIT


def test_issues_json_and_on_this_day(tmp_path):
    data_dir = tmp_path / "news-data"
    data_dir.mkdir()
    fixtures = [
        ("push-2025-07-02-09-00-00.md", "2025", "2025 年同日"),
        ("push-2026-07-02-10-00-00.md", "2026", "2026 年同日"),
        ("push-2026-07-01-10-00-00.md", "2026", "七月一日"),
    ]
    for filename, _year, title in fixtures:
        date = filename.split("-")[1] + "-" + filename.split("-")[2] + "-" + filename.split("-")[3]
        (data_dir / filename).write_text(
            f"""---
title: "{title}"
lead: "导语"
profile: morning
date: "{date}"
---

### 内容
""",
            encoding="utf-8",
        )
    issues = collect_all_issues(data_dir)
    write_issues_json(data_dir, issues)
    write_on_this_day_json(data_dir, issues)

    index_json = json.loads((data_dir / "issues-index.json").read_text(encoding="utf-8"))
    assert index_json["total"] == 3
    assert "2026" in index_json["years"]
    assert "2025" in index_json["years"]

    year_2026 = json.loads((data_dir / "issues-2026.json").read_text(encoding="utf-8"))
    assert len(year_2026) == 2
    assert year_2026[0]["date"] >= year_2026[1]["date"]

    otd = json.loads((data_dir / "on-this-day.json").read_text(encoding="utf-8"))
    assert "07-02" in otd
    assert len(otd["07-02"]) == 2
    assert otd["07-02"][0]["year"] == 2026


def test_on_this_day_in_article(tmp_path):
    data_dir = tmp_path / "news-data"
    data_dir.mkdir()
    (data_dir / "push-2025-07-02-09-00-00.md").write_text(
        """---
title: "去年今日"
lead: "导语"
profile: morning
date: "2025-07-02"
---
### 内容
""",
        encoding="utf-8",
    )
    (data_dir / "push-2026-07-02-10-00-00.md").write_text(
        """---
title: "今年今日"
lead: "导语"
profile: morning
date: "2026-07-02"
---
### 内容
""",
        encoding="utf-8",
    )
    build_all_pages(data_dir=data_dir, index_output=tmp_path / "index.html")
    html_out = (data_dir / "push-2026-07-02-10-00-00.html").read_text(encoding="utf-8")
    assert "往年今日" in html_out
    assert "去年今日" in html_out
    assert "2025" in html_out

    html_no_otd = (data_dir / "push-2025-07-02-09-00-00.html").read_text(encoding="utf-8")
    assert "往年今日" not in html_no_otd


def test_get_on_this_day_excludes_current_and_future_years():
    issues = [
        {"month_day": "07-02", "date": "2024-07-02", "title": "A", "url": "a.html"},
        {"month_day": "07-02", "date": "2025-07-02", "title": "B", "url": "b.html"},
        {"month_day": "07-02", "date": "2026-07-02", "title": "C", "url": "c.html"},
    ]
    items = get_on_this_day_items(issues, "07-02", "2026")
    assert len(items) == 2
    assert items[0]["year"] == 2025
    assert items[1]["year"] == 2024

    assert get_on_this_day_items(issues, "07-02", "2025") == [
        {"year": 2024, "date": "2024-07-02", "title": "A", "url": "a.html"}
    ]


def test_archive_pages_generated(tmp_path):
    data_dir = tmp_path / "news-data"
    data_dir.mkdir()
    (data_dir / "push-2026-06-15-10-00-00.md").write_text(
        """---
title: "六月刊"
lead: "导语"
profile: morning
date: "2026-06-15"
---
### 内容
""",
        encoding="utf-8",
    )
    (data_dir / "push-2026-07-02-10-00-00.md").write_text(
        """---
title: "七月刊"
lead: "导语"
profile: morning
date: "2026-07-02"
---
### 内容
""",
        encoding="utf-8",
    )
    build_all_pages(data_dir=data_dir, index_output=tmp_path / "index.html")
    year_page = (tmp_path / "archive" / "2026" / "index.html").read_text(encoding="utf-8")
    assert "archive-tabs" in year_page
    assert "列表" in year_page
    assert "日历" in year_page
    assert (tmp_path / "archive" / "2026" / "07.html").exists()
    assert (tmp_path / "archive" / "2026" / "06.html").exists()
    month_page = (tmp_path / "archive" / "2026" / "07.html").read_text(encoding="utf-8")
    assert "七月刊" in month_page
