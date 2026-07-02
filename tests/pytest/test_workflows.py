"""GitHub Actions workflow 契约测试：禁止脆弱的 detect 时间检测。"""

from pathlib import Path

import pytest

WORKFLOW_DIR = Path(__file__).resolve().parents[2] / ".github" / "workflows"


@pytest.mark.parametrize(
    "filename",
    ["fetch.yml", "daily.yml", "health-check.yml", "check.yml", "pages.yml"],
)
def test_workflow_file_exists(filename):
    assert (WORKFLOW_DIR / filename).exists()


def test_no_detect_job_with_date_minute_check():
    """daily/fetch 不得再用 date -u 分钟数判断任务类型。"""
    for name in ("fetch.yml", "daily.yml", "health-check.yml", "check.yml"):
        text = (WORKFLOW_DIR / name).read_text(encoding="utf-8")
        assert "date -u +%M" not in text, f"{name} 仍含脆弱的分钟检测"
        assert "detect:" not in text, f"{name} 仍含 detect job"


def test_daily_workflow_uses_push_result_status():
    daily = (WORKFLOW_DIR / "daily.yml").read_text(encoding="utf-8")
    assert "steps.push.outputs.status" in daily
    assert ".last-push-result.json" in daily
    assert "config.user.json" in daily
    assert "deploy-pages@v4" in daily
    assert "wecom_only" in daily


def test_fetch_and_daily_separate_concurrency():
    fetch = (WORKFLOW_DIR / "fetch.yml").read_text(encoding="utf-8")
    daily = (WORKFLOW_DIR / "daily.yml").read_text(encoding="utf-8")
    assert "ai-daily-fetch" in fetch
    assert "ai-daily-daily" in daily
    assert "ai-daily-fetch" not in daily or "ai-daily-daily" in daily


def test_health_check_can_dispatch_daily():
    """健康检查失败时应能补触发 daily workflow。"""
    health = (WORKFLOW_DIR / "health-check.yml").read_text(encoding="utf-8")
    assert "actions: write" in health
    assert "createWorkflowDispatch" in health
    assert "daily.yml" in health
