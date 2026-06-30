"""企微 news 封面策略测试"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from main import _enrich_wecom_items_with_entry_images


class TestEnrichWecomItemsWithEntryImages:
    """测试即时热点封面补充"""

    def test_adds_picurl_when_url_matches(self):
        items = [{"title": "A", "description": "D", "url": "https://example.com/a"}]
        entries = [
            {
                "link": "https://example.com/a",
                "image_url": "https://cdn.example.com/a.jpg",
            }
        ]
        _enrich_wecom_items_with_entry_images(items, entries)
        assert items[0]["picurl"] == "https://cdn.example.com/a.jpg"

    def test_skips_when_no_image_url(self):
        items = [{"title": "A", "description": "D", "url": "https://example.com/a"}]
        entries = [{"link": "https://example.com/a"}]
        _enrich_wecom_items_with_entry_images(items, entries)
        assert "picurl" not in items[0]

    def test_skips_when_url_not_match(self):
        items = [{"title": "A", "description": "D", "url": "https://example.com/b"}]
        entries = [
            {
                "link": "https://example.com/a",
                "image_url": "https://cdn.example.com/a.jpg",
            }
        ]
        _enrich_wecom_items_with_entry_images(items, entries)
        assert "picurl" not in items[0]
