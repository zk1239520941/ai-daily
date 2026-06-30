#!/usr/bin/env python3
"""生成 GitHub Pages 站点：index.html + news-data/push-*.html。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.console import configure_stdio_utf8
from src.pages.builder import build_all_pages, cleanup_orphan_html

configure_stdio_utf8()


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    data_dir = root / "news-data"
    output = root / "index.html"
    if len(sys.argv) > 1:
        data_dir = Path(sys.argv[1])
    if len(sys.argv) > 2:
        output = Path(sys.argv[2])
    if not data_dir.is_dir():
        print(f"[WARN] 目录不存在: {data_dir}")
        data_dir.mkdir(parents=True, exist_ok=True)
    cleanup_orphan_html(data_dir)
    build_all_pages(data_dir=data_dir, index_output=output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
