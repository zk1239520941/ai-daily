"""Pages 正文解析测试。"""

from src.pages.parser import (
    build_sections_manifest,
    has_sentinels,
    split_sentinel_sections,
    strip_leading_h2,
)


def test_has_sentinels():
    assert has_sentinels("<!-- SECTION:rss BEGIN -->\n### x\n<!-- SECTION:rss END -->")
    assert not has_sentinels("### flat")


def test_split_sentinel_sections():
    body = """<!-- SECTION:rss BEGIN -->
### RSS条
<!-- SECTION:rss END -->

<!-- SECTION:github BEGIN -->
## ⭐ GitHub 趋势
- item
<!-- SECTION:github END -->"""
    sections = split_sentinel_sections(body)
    assert [key for key, _ in sections] == ["rss", "github"]
    assert "### RSS条" in sections[0][1]


def test_strip_leading_h2():
    md = "## ⭐ GitHub 趋势\n\n- **foo/bar**"
    assert strip_leading_h2(md).startswith("- **foo/bar**")


def test_build_sections_manifest():
    manifest = build_sections_manifest(
        {
            "rss": "### a\n### b",
            "github": "",
            "hackernews": "### hn",
            "insights": "plain",
        }
    )
    assert [item["id"] for item in manifest] == ["rss", "hackernews", "insights"]
    assert manifest[0]["entry_count"] == 2
