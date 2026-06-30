"""测试 digest 空内容静默跳过"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.main import _should_skip_digest


def _cfg(**overrides):
    base = {
        "filter": {
            "skip_empty_digest": True,
            "digest_min_items": 0,
        }
    }
    base["filter"].update(overrides)
    return base


def test_skip_when_all_sections_empty():
    assert _should_skip_digest(_cfg(), "", "", "", "", "") is True


def test_skip_when_only_empty_whitespace():
    assert _should_skip_digest(_cfg(), "  \n  ", "", "", "", "") is True


def test_no_skip_when_rss_has_items():
    rss = "### 1. 标题\n\n* 要点\n"
    assert _should_skip_digest(_cfg(), rss, "", "", "", "lead") is False


def test_no_skip_when_github_has_content():
    assert _should_skip_digest(_cfg(), "x", "", "## GH", "", "") is False


def test_respects_skip_empty_digest_false():
    cfg = _cfg(skip_empty_digest=False)
    assert _should_skip_digest(cfg, "", "", "", "", "") is False


def test_digest_min_items_with_no_other_sections():
    cfg = _cfg(digest_min_items=2)
    rss = "### 1. only one\n"
    assert _should_skip_digest(cfg, rss, rss, "", "", "") is True

    rss2 = "### 1. a\n\n### 2. b\n"
    assert _should_skip_digest(cfg, rss2, rss2, "", "", "") is False
