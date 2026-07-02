"""运行状态 manifest：记录 fetch/digest 执行情况，供健康检查与幂等控制。"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from src.config import get_timezone

RUN_STATE_FILE = "news-data/run-state.json"
PUSH_RESULT_FILE = "news-data/.last-push-result.json"

# ensure-digest 退出码（供 GHA fetch 读取）
EXIT_ENSURE_OK = 0
EXIT_ENSURE_DISPATCH_DAILY = 2
EXIT_ENSURE_DISPATCH_WECOM = 3

# 补触发 daily 后，在此时间内不重复 dispatch（应大于 daily job timeout）
DISPATCH_COOLDOWN_MINUTES = 50


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
    dispatch = state.get("digest_dispatch") or {}
    if dispatch.get("date") == today and dispatch.get("action") == "daily":
        state.pop("digest_dispatch", None)
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
    dispatch = state.get("digest_dispatch") or {}
    if dispatch.get("date") == today.isoformat():
        state.pop("digest_dispatch", None)
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


def _parse_first_push_cron(config: Optional[Dict]) -> Tuple[int, int]:
    """从 schedule.push_cron 解析首个 cron 的 (minute, hour)。"""
    crons = (config or {}).get("schedule", {}).get("push_cron", ["0 8 * * *"])
    for cron in crons:
        parts = str(cron).split()
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            return int(parts[0]), int(parts[1])
    return 0, 8


def is_past_digest_window(config: Optional[Dict] = None) -> bool:
    """当前本地时间是否已过首个 push_cron 时刻（早报窗口起点）。"""
    minute, hour = _parse_first_push_cron(config)
    now = datetime.now(get_timezone(config))
    window_start = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return now >= window_start


def was_wecom_sent_today(config: Optional[Dict] = None) -> bool:
    """今日 digest 企微是否已成功发送。"""
    today_str = _today(config).isoformat()
    last_wecom = load_run_state().get("last_wecom") or {}
    return last_wecom.get("date") == today_str


def record_wecom_sent(push_file: str, config: Optional[Dict] = None) -> None:
    """记录 digest 企微已成功推送。"""
    state = load_run_state()
    state["last_wecom"] = {
        "at": _now_iso(config),
        "date": _today(config).isoformat(),
        "push_file": push_file,
    }
    dispatch = state.get("digest_dispatch") or {}
    if dispatch.get("date") == _today(config).isoformat() and dispatch.get(
        "action"
    ) == "wecom":
        state.pop("digest_dispatch", None)
    save_run_state(state)


def _digest_dispatch_for_today(
    config: Optional[Dict] = None,
) -> Optional[Dict[str, Any]]:
    """返回今日 digest_dispatch 记录，无则 None。"""
    today_str = _today(config).isoformat()
    dispatch = load_run_state().get("digest_dispatch") or {}
    if dispatch.get("date") != today_str:
        return None
    return dispatch


def has_recent_digest_dispatch(
    action: str,
    config: Optional[Dict] = None,
    cooldown_minutes: int = DISPATCH_COOLDOWN_MINUTES,
) -> bool:
    """是否在冷却期内已补触发过指定 action（daily / wecom）。"""
    dispatch = _digest_dispatch_for_today(config)
    if not dispatch or dispatch.get("action") != action:
        return False
    at_raw = dispatch.get("at")
    if not at_raw:
        return True
    try:
        at = datetime.fromisoformat(at_raw)
        if at.tzinfo is None:
            at = at.replace(tzinfo=get_timezone(config))
    except ValueError:
        return True
    now = datetime.now(get_timezone(config))
    return (now - at).total_seconds() < cooldown_minutes * 60


def record_digest_dispatch(action: str, config: Optional[Dict] = None) -> None:
    """记录 fetch 已补触发 daily / wecom，防止并发重复 dispatch。"""
    state = load_run_state()
    today_str = _today(config).isoformat()
    prev = state.get("digest_dispatch") or {}
    count = int(prev.get("count", 0)) + 1 if prev.get("date") == today_str else 1
    state["digest_dispatch"] = {
        "date": today_str,
        "action": action,
        "at": _now_iso(config),
        "count": count,
    }
    save_run_state(state)


def clear_digest_dispatch(config: Optional[Dict] = None) -> None:
    """digest 已成功落盘或 skip 后清除补触发标记。"""
    state = load_run_state()
    dispatch = state.get("digest_dispatch") or {}
    if dispatch.get("date") == _today(config).isoformat():
        state.pop("digest_dispatch", None)
        save_run_state(state)


def evaluate_ensure_digest(config: Optional[Dict] = None) -> Tuple[int, str]:
    """fetch 完成后检查是否需要补触发 daily / 企微。

    Returns:
        (exit_code, message)
    """
    if not is_past_digest_window(config):
        return EXIT_ENSURE_OK, "未到早报窗口，跳过补发检查"

    today_str = _today(config).isoformat()
    last_digest = load_run_state().get("last_digest") or {}

    if (
        last_digest.get("date") == today_str
        and last_digest.get("status") == "generated"
        and not was_wecom_sent_today(config)
    ):
        push_file = last_digest.get("push_file", "")
        if has_recent_digest_dispatch("wecom", config):
            return EXIT_ENSURE_OK, "已触发企微补发，等待 daily workflow 完成"
        record_digest_dispatch("wecom", config)
        return (
            EXIT_ENSURE_DISPATCH_WECOM,
            f"今日 digest 已生成但未推企微，将补触发 wecom_only: {push_file}",
        )

    ok, health_msg = evaluate_daily_health(config)
    if ok:
        return EXIT_ENSURE_OK, health_msg

    if has_recent_digest_dispatch("daily", config):
        return EXIT_ENSURE_OK, "已触发早报补发，等待 daily workflow 完成"

    record_digest_dispatch("daily", config)
    return EXIT_ENSURE_DISPATCH_DAILY, f"{health_msg} → 将补触发 daily workflow"


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
