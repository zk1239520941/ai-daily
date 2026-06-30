"""GitHub Pages 静态站点生成。"""

from src.pages.builder import (
    build_all_pages,
    push_file_to_html_url,
    push_md_to_html_path,
)

__all__ = [
    "build_all_pages",
    "push_file_to_html_url",
    "push_md_to_html_path",
]
