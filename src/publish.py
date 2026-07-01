"""GitHub Pages 发布：清理旧日报、生成索引、git push、等待 URL 可访问。"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

import aiohttp

from src.config import get_timezone
from src.storage import get_last_push_file


def _ensure_git_identity() -> None:
    """CI 或未配置 git 用户时设置提交身份。"""
    if os.environ.get("GITHUB_ACTIONS"):
        subprocess.run(
            ["git", "config", "user.name", "github-actions[bot]"],
            check=False,
        )
        subprocess.run(
            [
                "git",
                "config",
                "user.email",
                "41898282+github-actions[bot]@users.noreply.github.com",
            ],
            check=False,
        )


def _git_pull_rebase(root: Path) -> bool:
    """push 前拉取远端，降低并发 commit 冲突概率。"""
    result = subprocess.run(
        ["git", "pull", "--rebase", "--autostash"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[warn] git pull --rebase 失败: {result.stderr.strip()}")
        return False
    return True


def cleanup_old_push_files(days: int = 30, data_dir: str = "news-data") -> int:
    """删除超过 days 天的 push-*.md，返回删除数量。"""
    data_path = Path(data_dir)
    if not data_path.exists():
        return 0

    cutoff = datetime.now(get_timezone()).date() - timedelta(days=days)
    deleted = 0

    for file in data_path.glob("push-*.md"):
        file_date = _parse_push_file_date(file.name)
        if file_date is None:
            continue
        if file_date < cutoff:
            try:
                file.unlink()
                html_file = file.with_suffix(".html")
                if html_file.exists():
                    html_file.unlink()
                deleted += 1
                print(f"   [del] 删除过期日报: {file.name}")
            except OSError as exc:
                print(f"   [warn] 无法删除 {file.name}: {exc}")

    if deleted:
        print(f"   [ok] 已清理 {deleted} 篇超过 {days} 天的 push 日报")
    return deleted


def _parse_push_file_date(filename: str) -> date | None:
    """从 push-2026-06-30-17-51-09.md 解析日期。"""
    stem = filename.replace("push-", "").replace(".md", "")
    parts = stem.split("-")
    if len(parts) < 3:
        return None
    try:
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None


def resolve_push_full_url(
    push_file: str,
    wecom_config: Optional[dict] = None,
) -> str:
    """根据 push 文件路径生成 GitHub Pages 完整版 URL。"""
    if not push_file:
        return ""
    from src.push.wecom import build_push_page_url, resolve_pages_base_url

    pages_base = resolve_pages_base_url(wecom_config or {})
    return build_push_page_url(pages_base, push_file)


async def wait_for_url(
    url: str,
    timeout: int = 300,
    interval: int = 10,
) -> bool:
    """轮询 URL 直到 HTTP 200 或超时。

    Args:
        url: 待检测的完整版日报 URL
        timeout: 最长等待秒数，默认 5 分钟
        interval: 轮询间隔秒数，默认 10 秒

    Returns:
        URL 可访问时返回 True，超时或 URL 为空时返回 False
    """
    if not url:
        print("[warn] wait_for_url: URL 为空，跳过等待")
        return False

    deadline = time.monotonic() + timeout
    attempt = 0

    print(f"[wait] 等待完整版 URL 可访问: {url}")
    print(f"[wait] 超时 {timeout}s，间隔 {interval}s")

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=30)
    ) as session:
        while time.monotonic() < deadline:
            attempt += 1
            try:
                async with session.head(
                    url, allow_redirects=True
                ) as resp:
                    if resp.status == 200:
                        print(f"[ok] 完整版 URL 已可访问 (HTTP 200, 第 {attempt} 次)")
                        return True
                    print(
                        f"[wait] 第 {attempt} 次: HTTP {resp.status}，"
                        f"{interval}s 后重试..."
                    )
            except aiohttp.ClientError as exc:
                print(
                    f"[wait] 第 {attempt} 次: 请求失败 ({exc})，"
                    f"{interval}s 后重试..."
                )

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            await asyncio.sleep(min(interval, remaining))

    print(f"[err] 完整版 URL 在 {timeout}s 内不可访问，放弃 digest 企微推送")
    return False


def publish_pages_to_github(
    push_keep_days: int = 30,
    data_dir: str = "news-data",
    commit_message: str = "chore(data): 更新日报 push 文件",
    wecom_config: Optional[dict] = None,
) -> Tuple[int, str, str]:
    """清理旧 push、生成 index.html、提交并 push 到 origin（触发 Pages）。

    Returns:
        (exit_code, push_file, full_url)
    """
    root = Path(__file__).resolve().parent.parent
    _ensure_git_identity()
    _git_pull_rebase(root)
    cleanup_old_push_files(days=push_keep_days, data_dir=data_dir)

    build_script = root / "scripts" / "build_pages_index.py"
    if build_script.exists():
        result = subprocess.run(
            [sys.executable, str(build_script)],
            cwd=str(root),
            check=False,
        )
        if result.returncode != 0:
            print("[err] 生成 Pages 站点失败")
            latest = get_last_push_file(data_dir) or ""
            return result.returncode, latest, resolve_push_full_url(latest, wecom_config)

    push_files = list(Path(data_dir).glob("push-*.md"))
    push_html_files = list(Path(data_dir).glob("push-*.html"))
    latest_push_file = get_last_push_file(data_dir) or ""
    full_url = resolve_push_full_url(latest_push_file, wecom_config)

    if not push_files:
        print("[info] 无 push-*.md，跳过 git 提交")
        return 0, latest_push_file, full_url

    index_path = root / "index.html"
    if index_path.exists():
        subprocess.run(["git", "add", "-f", "index.html"], cwd=str(root), check=False)
    static_dir = root / "static"
    if static_dir.exists():
        subprocess.run(["git", "add", "-f", "static"], cwd=str(root), check=False)
    for f in push_files:
        subprocess.run(["git", "add", "-f", str(f)], cwd=str(root), check=False)
    for f in push_html_files:
        subprocess.run(["git", "add", "-f", str(f)], cwd=str(root), check=False)
    for pattern in ("run-state.json", "push-skip-*.json"):
        for f in Path(data_dir).glob(pattern):
            subprocess.run(["git", "add", "-f", str(f)], cwd=str(root), check=False)
    subprocess.run(["git", "add", "-u", data_dir], cwd=str(root), check=False)

    staged = subprocess.run(
        ["git", "diff", "--staged", "--quiet"],
        cwd=str(root),
    )
    if staged.returncode == 0:
        print("[info] 无 git 变更，跳过 commit")
        return 0, latest_push_file, full_url

    subprocess.run(
        ["git", "commit", "-m", commit_message],
        cwd=str(root),
        check=True,
    )
    push_result = subprocess.run(["git", "push"], cwd=str(root), check=False)
    if push_result.returncode != 0:
        print("[err] git push 失败，请检查 remote 与认证")
        return push_result.returncode, latest_push_file, full_url

    print("[ok] 已 push 到 GitHub，Pages 部署中...")
    if full_url:
        print(f"[info] 完整版 URL: {full_url}")
    return 0, latest_push_file, full_url


def commit_fetch_to_github(
    data_dir: str = "news-data",
    commit_message: str = "chore(data): 更新 fetch 数据",
) -> int:
    """提交 fetch/notify/trending 数据到 git（GHA hourly fetch 真源）。"""
    root = Path(__file__).resolve().parent.parent
    _ensure_git_identity()
    _git_pull_rebase(root)
    data_path = Path(data_dir)

    for pattern in (
        "fetch-*.json",
        "trending-history.json",
        "notify-*.md",
        "run-state.json",
        "push-skip-*.json",
    ):
        for f in data_path.glob(pattern):
            subprocess.run(["git", "add", "-f", str(f)], cwd=str(root), check=False)

    staged = subprocess.run(
        ["git", "diff", "--staged", "--quiet"],
        cwd=str(root),
    )
    if staged.returncode == 0:
        print("[info] fetch 数据无变更，跳过 commit")
        return 0

    subprocess.run(
        ["git", "commit", "-m", commit_message],
        cwd=str(root),
        check=True,
    )
    push_result = subprocess.run(["git", "push"], cwd=str(root), check=False)
    if push_result.returncode != 0:
        print("[err] fetch 数据 git push 失败")
        return push_result.returncode
    print("[ok] fetch 数据已 push 到 GitHub")
    return 0
