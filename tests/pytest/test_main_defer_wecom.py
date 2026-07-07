"""测试 defer-wecom 与 digest 企微延迟推送流程"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.main import cmd_daily, cmd_wecom, run_push_job, send_digest_wecom


@pytest.mark.asyncio
async def test_run_push_job_generate_only_skips_send(sample_config):
    with patch(
        "src.main._run_daily_push", new=AsyncMock(return_value="news-data/push-test.md")
    ) as daily_push, patch("src.main.send_to_platforms", new=AsyncMock()) as send_mock:
        result = await run_push_job(sample_config, generate_only=True)

    assert result == "news-data/push-test.md"
    daily_push.assert_awaited_once_with(
        sample_config, generate_only=True, force=False
    )
    send_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_digest_wecom_loads_push_file(tmp_path, sample_config):
    push_file = tmp_path / "push-test.md"
    push_file.write_text(
        "---\ntitle: 测试日报\nprofile: default\n---\n\n### 1. 新闻\n\n* 要点\n",
        encoding="utf-8",
    )

    with patch(
        "src.main.send_to_platforms", new=AsyncMock(return_value=True)
    ) as send_mock:
        ok = await send_digest_wecom(
            sample_config,
            str(push_file),
            "https://pages.example/full.md",
        )

    assert ok is True
    send_mock.assert_awaited_once()
    _, kwargs = send_mock.call_args
    assert kwargs["metadata"]["full_url"] == "https://pages.example/full.md"


@pytest.mark.asyncio
async def test_send_digest_wecom_returns_false_when_send_fails(tmp_path, sample_config):
    push_file = tmp_path / "push-test.md"
    push_file.write_text(
        "---\ntitle: 测试日报\nprofile: default\n---\n\n### 1. 新闻\n\n* 要点\n",
        encoding="utf-8",
    )

    with patch("src.main.send_to_platforms", new=AsyncMock(return_value=False)):
        ok = await send_digest_wecom(
            sample_config,
            str(push_file),
            "https://pages.example/full.md",
        )

    assert ok is False


@pytest.mark.asyncio
async def test_cmd_wecom_fails_when_send_digest_returns_false(sample_config):
    with patch("src.main.get_last_push_file", return_value="news-data/push-x.md"), patch(
        "src.publish.resolve_push_full_url",
        return_value="https://pages.example/full.html",
    ), patch(
        "src.main.send_digest_wecom", new=AsyncMock(return_value=False)
    ), patch("src.main.record_wecom_sent") as record_mock:
        code = await cmd_wecom(sample_config, skip_wait=True)

    assert code == 1
    record_mock.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_wecom_aborts_when_url_not_ready(sample_config):
    """URL 未就绪时不推送 digest，仅告警。"""
    with patch("src.main.get_last_push_file", return_value="news-data/push-x.md"), patch(
        "src.publish.resolve_push_full_url",
        return_value="https://pages.example/full.html",
    ), patch("src.publish.wait_for_pages_workflow", return_value=True), patch(
        "src.publish.wait_for_url", new=AsyncMock(return_value=False)
    ), patch("src.main.send_digest_wecom", new=AsyncMock(return_value=True)) as send_mock, patch(
        "src.main.notify_digest_url_unavailable", new=AsyncMock()
    ) as alert_mock:
        code = await cmd_wecom(sample_config)

    assert code == 1
    send_mock.assert_not_awaited()
    alert_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_cmd_daily_pipeline_order(sample_config):
    with patch("src.main.cmd_fetch", new=AsyncMock(return_value=0)), patch(
        "src.main.run_push_job", new=AsyncMock(return_value="news-data/push-y.md")
    ) as push_job, patch(
        "src.main.cmd_publish", new=AsyncMock(return_value=(0, "news-data/push-y.md", "https://u.md"))
    ) as publish, patch(
        "src.publish.wait_for_pages_workflow", return_value=True
    ), patch(
        "src.publish.wait_for_url", new=AsyncMock(return_value=True)
    ), patch("src.main.cmd_wecom", new=AsyncMock(return_value=0)) as wecom_cmd:
        code = await cmd_daily(sample_config)

    assert code == 0
    push_job.assert_awaited_once_with(sample_config, generate_only=True)
    publish.assert_awaited_once()
    wecom_cmd.assert_awaited_once()
