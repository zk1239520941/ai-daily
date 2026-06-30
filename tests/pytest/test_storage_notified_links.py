"""测试 notify 链接加载与 digest 排除"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.storage import load_notified_links


def test_load_notified_links_empty_dir(temp_dir):
    assert load_notified_links(context_days=3, data_dir=str(temp_dir)) == set()


def test_load_notified_links_from_wecom_items(temp_dir):
    today = datetime.now(timezone.utc).date().isoformat()
    content = """---
wecom_items:
  - title: 快讯
    url: https://example.com/a
---
正文
"""
    notify_file = temp_dir / f"notify-{today}.md"
    notify_file.write_text(content, encoding="utf-8")

    urls = load_notified_links(context_days=1, data_dir=str(temp_dir))
    assert "https://example.com/a" in urls


def test_load_notified_links_from_body_url(temp_dir):
    today = datetime.now(timezone.utc).date().isoformat()
    content = """---
title: 快讯
---
## 标题

https://example.com/body-link
"""
    notify_file = temp_dir / f"notify-{today}.md"
    notify_file.write_text(content, encoding="utf-8")

    urls = load_notified_links(context_days=1, data_dir=str(temp_dir))
    assert "https://example.com/body-link" in urls
