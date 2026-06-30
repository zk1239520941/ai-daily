"""GitHub Pages 发布：清理旧日报、生成索引、git push。"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from src.config import get_timezone


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


def publish_pages_to_github(
    push_keep_days: int = 30,
    data_dir: str = "news-data",
    commit_message: str = "chore(data): 更新日报 push 文件",
) -> int:
    """清理旧 push、生成 index.html、提交并 push 到 origin（触发 Pages）。"""
    root = Path(__file__).resolve().parent.parent
    _ensure_git_identity()
    cleanup_old_push_files(days=push_keep_days, data_dir=data_dir)

    build_script = root / "scripts" / "build_pages_index.py"
    if build_script.exists():
        result = subprocess.run(
            [sys.executable, str(build_script)],
            cwd=str(root),
            check=False,
        )
        if result.returncode != 0:
            print("[err] 生成 index.html 失败")
            return result.returncode

    push_files = list(Path(data_dir).glob("push-*.md"))
    if not push_files:
        print("[info] 无 push-*.md，跳过 git 提交")
        return 0

    index_path = root / "index.html"
    if index_path.exists():
        subprocess.run(["git", "add", "-f", "index.html"], cwd=str(root), check=False)
    static_dir = root / "static"
    if static_dir.exists():
        subprocess.run(["git", "add", "-f", "static"], cwd=str(root), check=False)
    for f in push_files:
        subprocess.run(["git", "add", "-f", str(f)], cwd=str(root), check=False)
    subprocess.run(["git", "add", "-u", data_dir], cwd=str(root), check=False)

    staged = subprocess.run(
        ["git", "diff", "--staged", "--quiet"],
        cwd=str(root),
    )
    if staged.returncode == 0:
        print("[info] 无 git 变更，跳过 commit")
        return 0

    subprocess.run(
        ["git", "commit", "-m", commit_message],
        cwd=str(root),
        check=True,
    )
    push_result = subprocess.run(["git", "push"], cwd=str(root), check=False)
    if push_result.returncode != 0:
        print("[err] git push 失败，请检查 remote 与认证")
        return push_result.returncode

    print("[ok] 已 push 到 GitHub，Pages 约 1-3 分钟后更新")
    return 0
