"""测试 run_push_job 每日 digest 路径"""

import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.main import run_push_job


@pytest.mark.asyncio
async def test_run_push_job_delegates_to_daily_push(sample_config):
    with patch(
        "src.main._run_daily_push", new=AsyncMock(return_value="news-data/push-x.md")
    ) as daily_path:
        result = await run_push_job(sample_config)

    daily_path.assert_awaited_once_with(sample_config, generate_only=False)
    assert result == "news-data/push-x.md"


@pytest.mark.asyncio
async def test_run_push_job_generate_only(sample_config):
    with patch(
        "src.main._run_daily_push", new=AsyncMock(return_value="news-data/push-y.md")
    ) as daily_path:
        result = await run_push_job(sample_config, generate_only=True)

    daily_path.assert_awaited_once_with(sample_config, generate_only=True)
    assert result == "news-data/push-y.md"
