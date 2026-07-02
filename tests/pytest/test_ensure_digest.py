"""ensure-digest 与补发状态机测试。"""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.run_state import (
    EXIT_ENSURE_DISPATCH_DAILY,
    EXIT_ENSURE_DISPATCH_WECOM,
    EXIT_ENSURE_OK,
    evaluate_ensure_digest,
    has_recent_digest_dispatch,
    is_past_digest_window,
    load_run_state,
    record_digest_dispatch,
    record_digest_success,
    record_wecom_sent,
    save_run_state,
)

TZ = timezone(timedelta(hours=8))
CONFIG = {"schedule": {"timezone_hours": 8, "push_cron": ["0 8 * * *"]}}


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    """隔离 run-state 与 news-data。"""
    data = tmp_path / "news-data"
    data.mkdir()
    state_path = data / "run-state.json"
    monkeypatch.setattr("src.run_state.RUN_STATE_FILE", str(state_path))
    monkeypatch.setattr("src.run_state.PUSH_RESULT_FILE", str(data / ".last-push-result.json"))
    return data


def _freeze_at(monkeypatch, dt: datetime):
    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz:
                return dt.astimezone(tz)
            return dt

    monkeypatch.setattr("src.run_state.datetime", FakeDatetime)


def test_is_past_digest_window_before_and_after(monkeypatch):
    _freeze_at(monkeypatch, datetime(2026, 7, 3, 7, 30, tzinfo=TZ))
    assert is_past_digest_window(CONFIG) is False
    _freeze_at(monkeypatch, datetime(2026, 7, 3, 8, 0, tzinfo=TZ))
    assert is_past_digest_window(CONFIG) is True


def test_ensure_digest_before_window(state_dir, monkeypatch):
    _freeze_at(monkeypatch, datetime(2026, 7, 3, 7, 0, tzinfo=TZ))
    code, msg = evaluate_ensure_digest(CONFIG)
    assert code == EXIT_ENSURE_OK
    assert "未到早报窗口" in msg


def test_ensure_digest_dispatch_daily_when_missing(state_dir, monkeypatch):
    _freeze_at(monkeypatch, datetime(2026, 7, 3, 9, 0, tzinfo=TZ))
    monkeypatch.setattr("src.run_state.load_run_state", lambda path=None: {})
    monkeypatch.setattr(
        "src.run_state.has_digest_skip_for_date", lambda d, data_dir="news-data": False
    )
    monkeypatch.setattr(
        "src.storage.find_push_for_local_date", lambda d, data_dir="news-data": None
    )
    code, msg = evaluate_ensure_digest(CONFIG)
    assert code == EXIT_ENSURE_DISPATCH_DAILY
    assert "补触发 daily" in msg
    state = load_run_state()
    assert state["digest_dispatch"]["action"] == "daily"


def test_ensure_digest_ok_when_digest_exists_and_wecom_sent(state_dir, monkeypatch):
    _freeze_at(monkeypatch, datetime(2026, 7, 3, 9, 0, tzinfo=TZ))
    push = state_dir / "push-2026-07-03-08-00-00.md"
    push.write_text("# test", encoding="utf-8")
    record_digest_success(str(push), CONFIG)
    record_wecom_sent(str(push), CONFIG)
    code, msg = evaluate_ensure_digest(CONFIG)
    assert code == EXIT_ENSURE_OK


def test_ensure_digest_dispatch_wecom_when_push_without_wecom(state_dir, monkeypatch):
    _freeze_at(monkeypatch, datetime(2026, 7, 3, 9, 0, tzinfo=TZ))
    save_run_state({})
    push = state_dir / "push-2026-07-03-08-00-00.md"
    push.write_text("# test", encoding="utf-8")
    record_digest_success(str(push), CONFIG)
    code, msg = evaluate_ensure_digest(CONFIG)
    assert code == EXIT_ENSURE_DISPATCH_WECOM
    assert "wecom_only" in msg


def test_has_recent_digest_dispatch_cooldown(state_dir, monkeypatch):
    fixed = datetime(2026, 7, 3, 9, 0, tzinfo=TZ)
    _freeze_at(monkeypatch, fixed)
    record_digest_dispatch("daily", CONFIG)
    assert has_recent_digest_dispatch("daily", CONFIG) is True
    _freeze_at(monkeypatch, fixed + timedelta(minutes=51))
    assert has_recent_digest_dispatch("daily", CONFIG) is False


def test_ensure_digest_no_double_dispatch_in_cooldown(state_dir, monkeypatch):
    _freeze_at(monkeypatch, datetime(2026, 7, 3, 9, 0, tzinfo=TZ))
    save_run_state(
        {
            "digest_dispatch": {
                "date": "2026-07-03",
                "action": "daily",
                "at": datetime(2026, 7, 3, 9, 0, tzinfo=TZ).isoformat(),
                "count": 1,
            }
        }
    )
    monkeypatch.setattr(
        "src.run_state.evaluate_daily_health",
        lambda config=None: (False, "missing digest"),
    )
    code, msg = evaluate_ensure_digest(CONFIG)
    assert code == EXIT_ENSURE_OK
    assert "已触发早报补发" in msg
