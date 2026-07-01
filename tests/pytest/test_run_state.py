"""run_state manifest 与健康检查测试。"""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.run_state import (
    evaluate_daily_health,
    load_run_state,
    record_digest_skip,
    record_digest_success,
    save_run_state,
    write_push_result,
)
from src.storage import find_push_for_local_date


TZ = timezone(timedelta(hours=8))


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    """隔离 run-state 与 news-data 目录。"""
    data = tmp_path / "news-data"
    data.mkdir()
    state_path = data / "run-state.json"
    monkeypatch.setattr("src.run_state.RUN_STATE_FILE", str(state_path))
    monkeypatch.setattr("src.run_state.PUSH_RESULT_FILE", str(data / ".last-push-result.json"))
    return data


def test_write_push_result(state_dir):
    write_push_result("generated", "news-data/push-2026-07-01-08-00-00.md", config={"schedule": {"timezone_hours": 8}})
    result_path = state_dir / ".last-push-result.json"
    assert result_path.exists()
    assert '"status": "generated"' in result_path.read_text(encoding="utf-8")


def test_record_digest_skip_creates_skip_file(state_dir):
    skip_path = record_digest_skip("四段全空", config={"schedule": {"timezone_hours": 8}})
    assert Path(skip_path).exists()
    state = load_run_state()
    assert state["last_digest"]["status"] == "skipped"


def test_find_push_for_local_date(state_dir):
    push = state_dir / "push-2026-07-01-08-00-00.md"
    push.write_text("# test", encoding="utf-8")
    found = find_push_for_local_date(date(2026, 7, 1), str(state_dir))
    assert found == str(push)


def test_evaluate_daily_health_ok_with_state(state_dir, monkeypatch):
    fixed = datetime(2026, 7, 1, 9, 0, tzinfo=TZ)

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed if tz else fixed

    monkeypatch.setattr("src.run_state.datetime", FakeDatetime)
    record_digest_success(
        "news-data/push-2026-07-01-08-00-00.md",
        config={"schedule": {"timezone_hours": 8}},
    )
    ok, msg = evaluate_daily_health({"schedule": {"timezone_hours": 8}})
    assert ok is True
    assert "generated" in msg


def test_evaluate_daily_health_fail_when_missing(state_dir, monkeypatch):
    fixed = datetime(2026, 7, 1, 9, 0, tzinfo=TZ)

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed if tz else fixed

    monkeypatch.setattr("src.run_state.datetime", FakeDatetime)
    monkeypatch.setattr("src.run_state.load_run_state", lambda path=None: {})
    monkeypatch.setattr(
        "src.run_state.has_digest_skip_for_date", lambda d, data_dir="news-data": False
    )
    monkeypatch.setattr(
        "src.storage.find_push_for_local_date", lambda d, data_dir="news-data": None
    )
    ok, msg = evaluate_daily_health({"schedule": {"timezone_hours": 8}})
    assert ok is False
    assert "2026-07-01" in msg


def test_record_digest_success_updates_state(state_dir):
    record_digest_success("news-data/push-2026-07-01-08-00-00.md", config={"schedule": {"timezone_hours": 8}})
    state = load_run_state()
    assert state["last_digest"]["status"] == "generated"
    assert "push-2026-07-01" in state["last_digest"]["push_file"]
