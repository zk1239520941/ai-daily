"""src.main.collect_entries_for_push patched at source (lazy import in section)"""

import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.sections.rss.section import run_rss_section


@pytest.mark.asyncio
async def test_returns_markdown_when_entries_present(sample_config, tmp_path):
    with patch(
        "src.main.collect_entries_for_push",
        return_value=([{"link": "x", "title": "t", "score": 80}], []),
    ), patch(
        "src.sections.rss.section.compose_digest",
        new=AsyncMock(return_value="# digest body"),
    ), patch(
        "src.sections.rss.section.load_recent_push_titles", return_value=""
    ), patch(
        "src.sections.rss.section.get_last_push_file", return_value=None
    ):
        md, err = await run_rss_section(sample_config, now=None)

    assert md == "# digest body"
    assert err is None


@pytest.mark.asyncio
async def test_returns_empty_when_no_entries(sample_config):
    with patch(
        "src.main.collect_entries_for_push", return_value=([], [])
    ), patch(
        "src.sections.rss.section.get_last_push_file", return_value=None
    ):
        md, err = await run_rss_section(sample_config, now=None)

    assert md == ""
    assert err is None


@pytest.mark.asyncio
async def test_returns_error_on_compose_failure(sample_config):
    with patch(
        "src.main.collect_entries_for_push",
        return_value=([{"link": "x"}], []),
    ), patch(
        "src.sections.rss.section.compose_digest",
        new=AsyncMock(side_effect=RuntimeError("LLM down")),
    ), patch(
        "src.sections.rss.section.load_recent_push_titles", return_value=""
    ), patch(
        "src.sections.rss.section.get_last_push_file", return_value=None
    ):
        md, err = await run_rss_section(sample_config, now=None)

    assert md == ""
    assert "LLM down" in err
