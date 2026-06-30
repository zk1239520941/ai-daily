"""markdown_utils 单元测试。"""

from src.markdown_utils import (
    extract_first_url,
    lookup_entry_image,
    normalize_url,
)


def test_extract_first_url_markdown():
    text = "🔗 [来源](https://example.com/a?q=1#frag)"
    assert extract_first_url(text) == "https://example.com/a?q=1#frag"


def test_normalize_url_strips_fragment_and_trailing_slash():
    assert normalize_url("https://example.com/a/") == "https://example.com/a"
    assert normalize_url("https://example.com/a#x") == "https://example.com/a"


def test_lookup_entry_image_normalized_match():
    images = {"https://example.com/a": "https://img.example/a.jpg"}
    assert lookup_entry_image(images, "https://example.com/a/") == "https://img.example/a.jpg"
