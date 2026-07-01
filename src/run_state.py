"""运行状态 manifest：记录 fetch/digest 执行情况，供健康检查与幂等控制。"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from src.config import get_timezone

RUN_STATE_FILE = "news-data/run-state.json"
PUSH_RESULT_FILE = "news-data/.last-push-result.json"


def _now_iso(config: Optional[Dict] = None) -> str:
    """返回配置时区下的 ISO 时间字符串。"""
    return datetime.now(get_timezone(config)).isoformat()


def _today(config: Optional[Dict] = None) -> date:
    """返回配置时区下的今日日期。"""
    return datetime.now(get_timezone(config)).date()


def load_run_state(path: str = RUN_STATE_FILE) -> Dict[str, Any]:
    """加载 run-state.json。"""
    p = Path(path)
    if not p.exists() or p.stat().st_size == 0:
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_run_state(state: Dict[str, Any], path: str = RUN_STATE_FILE) -> None:
    """持久化 run-state.json。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_push_result(
    status: str,
    push_file: str = "",
    reason: str = "",
    config: Optional[Dict] = None,
    path: Optional[str] = None,
) -> None:
    """写入最近一次 push 结果，供 GHA 读取。"""
    target = path or PUSH_RESULT_FILE
    payload = {
        "status": status,
        "push_file": push_file,
        "reason": reason,
        "at": _now_iso(config),
        "date": _today(config).isoformat(),
    }
    p = Path(target)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_push_result(path: str = PUSH_RESULT_FILE) -> Dict[str, Any]:
    """读取最近一次 push 结果。"""
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def record_fetch_success(config: Optional[Dict] = None) -> None:
    """记录 hourly fetch 成功。"""
    state = load_run_state()
    state["last_fetch"] = {
        "at": _now_iso(config),
        "date": _today(config).isoformat(),
        "status": "ok",
    }
    save_run_state(state)


def record_fetch_error(message: str, config: Optional[Dict] = None) -> None:
    """记录 fetch 失败。"""
    state = load_run_state()
    state["last_fetch"] = {
        "at": _now_iso(config),
        "date": _today(config).isoformat(),
        "status": "error",
        "error": message,
    }
    state["last_error"] = {
        "stage": "fetch",
        "at": _now_iso(config),
        "message": message,
    }
    save_run_state(state)


def record_digest_success(push_file: str, config: Optional[Dict] = None) -> None:
    """记录 digest 生成成功。"""
    state = load_run_state()
    today = _today(config).isoformat()
    state["last_digest"] = {
        "at": _now_iso(config),
        "date": today,
        "status": "generated",
        "push_file": push_file,
    }
    save_run_state(state)


def record_digest_skip(reason: str, config: Optional[Dict] = None) -> str:
    """记录 digest 静默跳过，并写入 push-skip 文件。"""
    state = load_run_state()
    today = _today(config)
    skip_path = Path("news-data") / f"push-skip-{today.isoformat()}.json"
    skip_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "date": today.isoformat(),
        "reason": reason,
        "at": _now_iso(config),
    }
    skip_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    state["last_digest"] = {
        "at": _now_iso(config),
        "date": today.isoformat(),
        "status": "skipped",
        "reason": reason,
        "skip_file": str(skip_path),
    }
    save_run_state(state)
    return str(skip_path)


def record_digest_error(message: str, config: Optional[Dict] = None) -> None:
    """记录 digest 失败。"""
    state = load_run_state()
    state["last_digest"] = {
        "at": _now_iso(config),
        "date": _today(config).isoformat(),
        "status": "error",
        "error": message,
    }
    state["last_error"] = {
        "stage": "digest",
        "at": _now_iso(config),
        "message": message,
    }
    save_run_state(state)


def has_digest_skip_for_date(d: date, data_dir: str = "news-data") -> bool:
    """检查指定日期是否已有 skip 记录。"""
    return (Path(data_dir) / f"push-skip-{d.isoformat()}.json").exists()


def evaluate_daily_health(config: Optional[Dict] = None) -> Tuple[bool, str]:
    """健康检查：今日是否已有 digest 或 skip 记录。

    Returns:
        (ok, message)
    """
    today = _today(config)
    today_str = today.isoformat()
    state = load_run_state()
    last_digest = state.get("last_digest") or {}

    if last_digest.get("date") == today_str and last_digest.get("status") in (
        "generated",
        "skipped",
    ):
        status = last_digest.get("status")
        detail = last_digest.get("push_file") or last_digest.get("reason") or ""
        return True, f"今日 digest 状态={status} {detail}".strip()

    from src.storage import find_push_for_local_date

    existing = find_push_for_local_date(today, "news-data")
    if existing:
        return True, f"今日已有 push 文件: {existing}"

    if has_digest_skip_for_date(today):
        return True, f"今日已有 push-skip 记录"

    last_at = last_digest.get("at", "未知")
    return (
        False,
        f"今日 ({today_str}) 未发现 digest 或 skip 记录，最近 digest 记录时间: {last_at}",
    )
