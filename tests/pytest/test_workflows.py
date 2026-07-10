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


def test_daily_wecom_only_on_generated():
    """幂等 rerun 不得重复推企微。"""
    daily = (WORKFLOW_DIR / "daily.yml").read_text(encoding="utf-8")
    assert "if: steps.push.outputs.status == 'generated'" in daily
    assert (
        "steps.push.outputs.status == 'generated' || steps.push.outputs.status == 'idempotent'"
        not in daily
    )


def test_fetch_and_daily_separate_concurrency():
    fetch = (WORKFLOW_DIR / "fetch.yml").read_text(encoding="utf-8")
    daily = (WORKFLOW_DIR / "daily.yml").read_text(encoding="utf-8")
    assert "ai-daily-fetch" in fetch
    assert "ai-daily-daily" in daily
    assert "ai-daily-fetch" not in daily or "ai-daily-daily" in daily


def test_fetch_ensure_digest_can_dispatch_daily():
    """hourly fetch 在 digest 缺失时应能补触发 daily / wecom。"""
    fetch = (WORKFLOW_DIR / "fetch.yml").read_text(encoding="utf-8")
    assert "actions: write" in fetch
    assert "ensure-digest" in fetch
    assert "createWorkflowDispatch" in fetch
    assert "daily.yml" in fetch
    assert "wecom_only" in fetch


def test_fetch_does_not_cache_overwrite_news_data():
    """news-data 以 git 为真源，不得用 actions/cache 覆盖 checkout 结果。"""
    fetch = (WORKFLOW_DIR / "fetch.yml").read_text(encoding="utf-8")
    assert "path: news-data" not in fetch
    assert "ai-daily-news-data" not in fetch


def test_health_check_alert_only():
    """health-check 仅告警，不再负责补触发。"""
    health = (WORKFLOW_DIR / "health-check.yml").read_text(encoding="utf-8")
    assert "health-check" in health
    assert "createWorkflowDispatch" not in health
    assert "actions: write" not in health
