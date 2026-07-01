"""测试 publish 模块 URL 等待与完整版链接生成"""

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.publish import resolve_push_full_url, wait_for_url


class TestResolvePushFullUrl:
    """测试完整版 URL 生成"""

    def test_builds_md_url(self):
        with patch.dict(os.environ, {"PAGES_BASE_URL": ""}, clear=False):
            url = resolve_push_full_url(
                "news-data/push-2026-06-30-18-00-00.md",
                {"pages_base_url": "https://example.github.io/ai-daily/"},
            )
        assert url == "https://example.github.io/ai-daily/news-data/push-2026-06-30-18-00-00.html"

    def test_empty_push_file(self):
        assert resolve_push_full_url("", {"pages_base_url": "https://x/"}) == ""


@pytest.mark.asyncio
async def test_wait_for_url_success_on_second_attempt():
    """第二次 GET 返回 200 时应成功"""
    resp_fail = MagicMock()
    resp_fail.status = 404
    resp_fail.__aenter__ = AsyncMock(return_value=resp_fail)
    resp_fail.__aexit__ = AsyncMock(return_value=None)

    resp_ok = MagicMock()
    resp_ok.status = 200
    resp_ok.__aenter__ = AsyncMock(return_value=resp_ok)
    resp_ok.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.get = MagicMock(side_effect=[resp_fail, resp_ok])
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session), patch(
        "src.publish.asyncio.sleep", new=AsyncMock()
    ):
        ok = await wait_for_url("https://example.com/page.html", timeout=60, interval=1)

    assert ok is True
    assert mock_session.get.call_count == 2


@pytest.mark.asyncio
async def test_wait_for_url_timeout():
    """超时后应返回 False"""
    resp = MagicMock()
    resp.status = 503
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session), patch(
        "src.publish.asyncio.sleep", new=AsyncMock()
    ), patch("src.publish.time.monotonic", side_effect=[0, 0, 400]):
        ok = await wait_for_url("https://example.com/page.md", timeout=300, interval=10)

    assert ok is False


@pytest.mark.asyncio
async def test_wait_for_url_empty():
    assert await wait_for_url("") is False
