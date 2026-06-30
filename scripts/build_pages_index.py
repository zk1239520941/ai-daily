#!/usr/bin/env python3
"""生成 GitHub Pages 索引页，列出 news-data/push-*.md 全文链接。"""

from __future__ import annotations

import html
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.console import configure_stdio_utf8

configure_stdio_utf8()


def build_index(data_dir: Path, output: Path, title: str = "AI Daily 日报归档") -> int:
    """扫描 push-*.md 并写入 index.html。"""
    files = sorted(data_dir.glob("push-*.md"), reverse=True)
    rows = []
    for f in files:
        name = f.name
        # push-2026-06-30-17-00-30.md → 2026-06-30 17:00
        stem = name.replace("push-", "").replace(".md", "")
        parts = stem.split("-")
        if len(parts) >= 6:
            display = f"{parts[0]}-{parts[1]}-{parts[2]} {parts[3]}:{parts[4]}"
        else:
            display = stem
        rel = f"news-data/{name}"
        rows.append(
            f'    <li><a href="{html.escape(rel)}">{html.escape(display)}</a></li>'
        )

    body = "\n".join(rows) if rows else "    <li>暂无日报</li>"
    content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; }}
    h1 {{ font-size: 1.5rem; }}
    ul {{ line-height: 1.8; }}
    a {{ color: #0969da; }}
    footer {{ margin-top: 2rem; color: #666; font-size: 0.875rem; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <p>点击下方链接阅读 Markdown 全文（浏览器可直接打开 .md 或配合渲染扩展）。</p>
  <ul>
{body}
  </ul>
  <footer>生成于 {html.escape(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))}</footer>
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    print(f"[OK] 已生成 {output}（{len(files)} 篇日报）")
    return len(files)


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
    build_index(data_dir, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
