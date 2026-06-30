"""封面图选取测试。"""

from src.pages.cover import enrich_image_metadata, select_cover_image


def test_select_cover_image_from_first_story():
    body = """### 1️⃣ A
* 🔗 [链](https://example.com/a)

### 2️⃣ B
* 🔗 [链](https://example.com/b)
"""
    images = {
        "https://example.com/a": "https://img.example/a.jpg",
        "https://example.com/b": "https://img.example/b.jpg",
    }
    assert select_cover_image(images, body) == "https://img.example/a.jpg"


def test_enrich_image_metadata_sets_cover():
    metadata = {
        "entry_images": {"https://example.com/a": "https://img.example/a.jpg"}
    }
    body = "### x\n* 🔗 [链](https://example.com/a)"
    enrich_image_metadata(metadata, body)
    assert metadata["cover_image"] == "https://img.example/a.jpg"
