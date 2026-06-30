"""Pages 静态站点生成测试。"""

from pathlib import Path

from src.pages.builder import (
    build_all_pages,
    build_article_html,
    parse_push_filename,
    push_file_to_html_url,
    push_md_to_html_path,
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
    assert "article-toc" in html_out
    assert "story-block" in html_out
    assert "reading-progress" in html_out
    assert "https://example.com" in html_out
    assert "早报" in html_out


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
---

### 章节

* 内容
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
