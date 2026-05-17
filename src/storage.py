"""数据存储模块 - JSON文件读写"""

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from src.config import get_timezone


def get_fetch_file(d: date = None, data_dir: str = "news-data") -> str:
    """获取fetch文件路径 (使用配置时区)"""
    if d is None:
        d = datetime.now(get_timezone()).date()
    return f"{data_dir}/fetch-{d.isoformat()}.json"


def get_push_file(push_time: datetime = None, data_dir: str = "news-data") -> str:
    """生成push文件路径"""
    if push_time is None:
        push_time = datetime.now()
    time_str = push_time.strftime("%Y-%m-%d-%H-%M-%S")
    return f"{data_dir}/push-{time_str}.md"


def get_notify_file(d: date = None, data_dir: str = "news-data") -> str:
    """获取notify文件路径 (使用配置时区)"""
    if d is None:
        d = datetime.now(get_timezone()).date()
    return f"{data_dir}/notify-{d.isoformat()}.md"


def save_notify_file(filepath: str, content: str):
    """保存即时推送文件（Markdown格式），同一天的内容追加到同一文件"""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    notify_time = datetime.now(get_timezone()).isoformat()

    new_content = f"""---
pushTime: "{notify_time}"
---

{content}

------
"""

    with open(path, "a", encoding="utf-8") as f:
        f.write(new_content)


_LEADING_NOISE_RE = re.compile(r"^[\W\d_]+", flags=re.UNICODE)


def _clean_title(raw: str) -> str:
    """剥离标题前导的 emoji / 数字序号 / 标点，仅保留文字主体"""
    return _LEADING_NOISE_RE.sub("", raw).strip()


def _extract_notify_titles(content: str) -> List[tuple]:
    """从单个 notify 文件内容解析事件清单

    notify 文件结构：多个推送块用 `------` 分隔，每块含
        ---
        pushTime: "..."
        ---
        # 🚨 AI Daily 快讯 | YYYY-MM-DD
        ## 🔥 <标题>
        ## 🌟 <标题>     # 可能有第二条

    返回 [(time_str, title), ...]，time_str 形如 "MM-DD HH:MM"
    """
    results = []
    for block in content.split("------"):
        block = block.strip()
        if not block:
            continue

        time_str = ""
        time_match = re.search(r'pushTime:\s*"([^"]+)"', block)
        if time_match:
            try:
                dt = datetime.fromisoformat(time_match.group(1))
                time_str = dt.strftime("%m-%d %H:%M")
            except (ValueError, TypeError):
                time_str = ""

        for title_match in re.finditer(r"^##\s+(.+)$", block, flags=re.MULTILINE):
            title = _clean_title(title_match.group(1))
            if title:
                results.append((time_str, title))

    return results


def _extract_push_titles(content: str) -> List[tuple]:
    """从单个 push 文件内容解析事件清单

    push 文件结构：
        ---
        pushDate: "..."
        ---
        # 📰 AI Daily 每日精选 | YYYY-MM-DD
        *引言*
        ### 1️⃣ <emoji> <标题>
        ### 2️⃣ <emoji> <标题>

    返回 [(time_str, title), ...]
    """
    results = []
    time_str = ""
    time_match = re.search(r'pushDate:\s*"([^"]+)"', content)
    if time_match:
        try:
            dt = datetime.fromisoformat(time_match.group(1))
            time_str = dt.strftime("%m-%d %H:%M")
        except (ValueError, TypeError):
            time_str = ""

    for title_match in re.finditer(r"^###\s+(.+)$", content, flags=re.MULTILINE):
        title = _clean_title(title_match.group(1))
        if title:
            results.append((time_str, title))

    return results


_SECTION_RE_CACHE: Dict[str, re.Pattern] = {}


def _section_re(section: str) -> re.Pattern:
    """获取/缓存 sentinel 正则。section 名做转义,允许字母数字下划线"""
    if section not in _SECTION_RE_CACHE:
        s = re.escape(section)
        pattern = rf"<!--\s*SECTION:{s}\s*BEGIN\s*-->(.*?)<!--\s*SECTION:{s}\s*END\s*-->"
        _SECTION_RE_CACHE[section] = re.compile(pattern, flags=re.DOTALL)
    return _SECTION_RE_CACHE[section]


def extract_section(push_md: str, section: str) -> str:
    """从 push 文件内容中切出 <!-- SECTION:{section} BEGIN/END --> 之间的 markdown。

    向后兼容:
    - 新文件(带 sentinel): 返回 sentinel 边界内的原文(不去边界空行)
    - 老文件(无 sentinel) 且 section == 'rss': 返回整个 push_md
    - 老文件(无 sentinel) 且 section != 'rss': 返回空字符串
    - sentinel 残缺(只有 BEGIN 没有 END): 返回空字符串
    """
    match = _section_re(section).search(push_md)
    if match:
        return match.group(1)

    # 老文件兜底:rss 段视为整个 body
    has_any_sentinel = "<!-- SECTION:" in push_md
    if section == "rss" and not has_any_sentinel:
        return push_md
    return ""


def load_recent_notify_titles(
    context_days: int = 3, data_dir: str = "news-data"
) -> str:
    """加载最近 context_days 天 notify 文件的事件标题清单（仅供 LLM 查重）

    返回紧凑的纯文本清单，每行一条事件，避免把成品推送当成风格范例传回 LLM。
    """
    data_path = Path(data_dir)
    if not data_path.exists():
        return ""

    tz = get_timezone()
    today = datetime.now(tz).date()

    items = []
    loaded_files = []
    for i in range(context_days):
        d = today - timedelta(days=i)
        notify_file = data_path / f"notify-{d.isoformat()}.md"
        if not notify_file.exists() or notify_file.stat().st_size == 0:
            continue
        try:
            with open(notify_file, "r", encoding="utf-8") as f:
                items.extend(_extract_notify_titles(f.read()))
                loaded_files.append(notify_file.name)
        except Exception:
            continue

    if loaded_files:
        print(
            f"   📂 已加载 {len(loaded_files)} 个 notify 文件 (titles): {', '.join(loaded_files)}"
        )

    return "\n".join(f"- [{t}] {title}" if t else f"- {title}" for t, title in items)


def load_recent_push_titles(
    context_days: int = 3, data_dir: str = "news-data"
) -> str:
    """加载最近 context_days 天 push 文件的事件标题清单（仅供 LLM 查重）"""
    data_path = Path(data_dir)
    if not data_path.exists():
        return ""

    tz = get_timezone()
    today = datetime.now(tz).date()

    items = []
    loaded_files = []
    for i in range(context_days):
        d = today - timedelta(days=i)
        pattern = f"push-{d.isoformat()}-*.md"
        for push_file in sorted(data_path.glob(pattern)):
            if push_file.stat().st_size == 0:
                continue
            try:
                with open(push_file, "r", encoding="utf-8") as f:
                    items.extend(_extract_push_titles(f.read()))
                    loaded_files.append(push_file.name)
            except Exception:
                continue

    if loaded_files:
        print(
            f"   📂 已加载 {len(loaded_files)} 个 push 文件 (titles): {', '.join(loaded_files)}"
        )

    return "\n".join(f"- [{t}] {title}" if t else f"- {title}" for t, title in items)


def get_last_push_file(data_dir: str = "news-data") -> Optional[str]:
    """从news-data目录找到最新的push文件"""
    data_path = Path(data_dir)
    if not data_path.exists():
        return None

    push_files = sorted(data_path.glob("push-*.md"))
    return str(push_files[-1]) if push_files else None


def extract_push_time(filepath: str) -> Optional[datetime]:
    """从push文件名提取时间"""
    try:
        basename = Path(filepath).name
        time_str = basename.replace("push-", "").replace(".md", "")
        dt = datetime.strptime(time_str, "%Y-%m-%d-%H-%M-%S")
        return dt.replace(tzinfo=get_timezone())
    except (ValueError, AttributeError):
        return None


def read_entries(filepath: str) -> List[Dict]:
    """读取fetch文件，返回entries列表"""
    path = Path(filepath)
    if not path.exists():
        return []

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data.get("entries", [])


def read_fetch_data(filepath: str) -> Dict:
    """读取完整的fetch文件数据（包含meta和entries）"""
    path = Path(filepath)
    if not path.exists():
        return {"meta": {}, "entries": []}

    # 检查文件是否为空
    if path.stat().st_size == 0:
        return {"meta": {}, "entries": []}

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_fetch_file(filepath: str, meta: Dict, entries: List[Dict]):
    """保存fetch文件（JSON格式）"""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {"meta": meta, "entries": entries}

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def append_entries(filepath: str, new_entries: List[Dict], meta: Dict = None):
    """追加条目到fetch文件"""
    path = Path(filepath)

    # 读取现有数据
    if path.exists():
        data = read_fetch_data(filepath)
    else:
        data = {"meta": meta or {}, "entries": []}

    # 更新meta（如果提供了）
    if meta:
        data["meta"].update(meta)

    # 去重：基于link字段
    existing_links = {e.get("link") for e in data["entries"]}
    for entry in new_entries:
        if entry.get("link") not in existing_links:
            data["entries"].append(entry)
            existing_links.add(entry.get("link"))

    # 保存
    save_fetch_file(filepath, data["meta"], data["entries"])
    return len(new_entries)


def format_entry(entry: Dict) -> str:
    """格式化单条条目为Markdown字符串"""
    tags = entry.get("tags", [])
    tags_str = json.dumps(tags, ensure_ascii=False) if tags else "[]"
    score = entry.get("score", "")
    summary = entry.get("summary", "")

    return f"""## {entry["title"]}

---
source: {entry["source"]}
link: {entry["link"]}
published: {entry["published"]}
fetched_at: {entry["fetched_at"]}
tags: {tags_str}
score: {score}
summary: {summary}
---

{entry["content"]}

------
"""


def json_to_md(data: Dict) -> str:
    """
    将JSON格式的fetch数据转换为Markdown格式，便于阅读

    Args:
        data: {"meta": {...}, "entries": [...]}

    Returns:
        Markdown格式的字符串
    """
    meta = data.get("meta", {})
    entries = data.get("entries", [])

    lines = []

    # 文件头部YAML frontmatter
    if meta.get("date"):
        lines.append("---")
        lines.append(f'date: "{meta["date"]}"')
        lines.append("---")
        lines.append("")

    # 条目
    for entry in entries:
        lines.append(format_entry(entry))

    return "\n".join(lines)


def convert_fetch_json_to_md(json_filepath: str, md_filepath: str = None) -> str:
    """
    将fetch JSON文件转换为Markdown文件

    Args:
        json_filepath: JSON文件路径
        md_filepath: 输出MD文件路径，默认为同名.md

    Returns:
        生成的Markdown内容
    """
    data = read_fetch_data(json_filepath)
    md_content = json_to_md(data)

    if md_filepath:
        path = Path(md_filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(md_content)

    return md_content


def save_push_file(
    filepath: str,
    content: str,
    source_count: int,
    total_entries: int,
    profile: str = "default",
):
    """保存推送文件（Markdown格式）

    Args:
        profile: "morning" | "default"  ← 早报或常规;写入 frontmatter,便于按 profile 分析
    """
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    push_time = datetime.now(get_timezone())
    frontmatter = (
        "---\n"
        f'pushDate: "{push_time.isoformat()}"\n'
        f'profile: "{profile}"\n'
        f"sourceCount: {source_count}\n"
        f"totalEntries: {total_entries}\n"
        "---\n\n"
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(frontmatter + content)


def load_existing_links(filepath: str, threshold: int = 150) -> set:
    """加载文件中已有的链接（用于去重）

    如果当天时间已超过 threshold 分钟，则只需加载当天文件；
    否则需要同时加载当天和昨天的文件（用于处理跨天边界情况）。

    Args:
        filepath: 当天的 fetch 文件路径
        threshold: 阈值（分钟），超过此时间只加载当天文件
    """
    tz = get_timezone()
    now = datetime.now(tz)
    current_minutes = now.hour * 60 + now.minute

    need_yesterday = current_minutes < threshold

    if not need_yesterday:
        if not filepath or not Path(filepath).exists():
            return set()
        entries = read_entries(filepath)
        return {e.get("link") for e in entries if e.get("link")}

    all_links = set()
    if filepath and Path(filepath).exists():
        all_links.update(
            {e.get("link") for e in read_entries(filepath) if e.get("link")}
        )

    yesterday = (now - timedelta(days=1)).date()
    yesterday_file = get_fetch_file(yesterday)
    if Path(yesterday_file).exists():
        all_links.update(
            {e.get("link") for e in read_entries(yesterday_file) if e.get("link")}
        )

    return all_links


def cleanup_old_files(days: int = 7, data_dir: str = "news-data"):
    """清理超过days天的旧文件"""
    data_path = Path(data_dir)
    if not data_path.exists():
        return

    cutoff = datetime.now() - timedelta(days=days)
    deleted_count = 0

    for pattern in ["fetch-*.json", "fetch-*.md", "push-*.md", "notify-*.md"]:
        for file in data_path.glob(pattern):
            try:
                date_str = (
                    file.name.replace("fetch-", "")
                    .replace("push-", "")
                    .replace("notify-", "")
                    .replace(".json", "")
                    .replace(".md", "")
                )
                date_parts = date_str.split("-")
                if len(date_parts) >= 3:
                    file_date = date(
                        int(date_parts[0]), int(date_parts[1]), int(date_parts[2])
                    )
                    if file_date < cutoff.date():
                        file.unlink()
                        deleted_count += 1
                        print(f"   🗑️ 删除旧文件: {file.name}")
            except (ValueError, OSError):
                continue

    # trending-history.json: 剪枝过期条目,保留文件本身
    trending_path = data_path / "trending-history.json"
    if trending_path.exists() and trending_path.stat().st_size > 0:
        try:
            history = load_trending_history(str(trending_path))
            before = len(history.repos)
            history.cleanup(today=datetime.now().date(), keep_days=days)
            after = len(history.repos)
            if after < before:
                history.save()
                print(f"   ✂️ trending-history 剪枝: {before} → {after} 条")
        except Exception as e:
            print(f"   ⚠️ trending-history 剪枝失败: {e}")

    if deleted_count > 0:
        print(f"   ✅ 清理完成: 删除了 {deleted_count} 个旧文件")


def load_recent_section_titles(
    section: str, days: int, data_dir: str = "news-data"
) -> str:
    """加载最近 days 天 push 文件中 section 段的标题清单(供 LLM 查重防风格趋同)。

    返回紧凑纯文本,每行一条事件;遇到老文件(无 sentinel)按 extract_section 的兜底语义处理。
    """
    data_path = Path(data_dir)
    if not data_path.exists():
        return ""

    tz = get_timezone()
    today = datetime.now(tz).date()

    items: List[tuple] = []
    loaded_files: List[str] = []
    for i in range(days):
        d = today - timedelta(days=i)
        pattern = f"push-{d.isoformat()}-*.md"
        for push_file in sorted(data_path.glob(pattern)):
            if push_file.stat().st_size == 0:
                continue
            try:
                with open(push_file, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                continue
            section_md = extract_section(content, section)
            if not section_md:
                continue
            items.extend(_extract_push_titles(section_md))
            loaded_files.append(push_file.name)

    if loaded_files:
        print(
            f"   📂 已加载 {len(loaded_files)} 个 push 文件 (section={section}): "
            f"{', '.join(loaded_files)}"
        )

    return "\n".join(f"- [{t}] {title}" if t else f"- {title}" for t, title in items)


class TrendingHistory:
    """GitHub trending 已查阅 repo 索引。

    repos 字段:url → last_seen_date (ISO YYYY-MM-DD)。
    每次早报 cleanup 一次,touch 完所有今日 URL 后 save。
    """

    def __init__(self, path: str, repos: Dict[str, str]):
        self._path = path
        self.repos: Dict[str, str] = dict(repos)

    def __contains__(self, url: str) -> bool:
        return url in self.repos

    def touch(self, url: str, today: date) -> None:
        self.repos[url] = today.isoformat()

    def cleanup(self, today: date, keep_days: int) -> None:
        cutoff = today - timedelta(days=keep_days)
        self.repos = {
            url: d
            for url, d in self.repos.items()
            if _parse_iso_date_safe(d) is not None
            and _parse_iso_date_safe(d) >= cutoff
        }

    def save(self) -> None:
        path = Path(self._path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "repos": self.repos,
            "updated_at": datetime.now(get_timezone()).isoformat(),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)


def _parse_iso_date_safe(s: str) -> Optional[date]:
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def load_trending_history(path: str) -> TrendingHistory:
    """读取 trending-history.json;不存在返回空实例。"""
    p = Path(path)
    if not p.exists() or p.stat().st_size == 0:
        return TrendingHistory(path, {})
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return TrendingHistory(path, data.get("repos", {}))
    except (json.JSONDecodeError, OSError):
        print(f"⚠️ trending-history 读取失败,使用空索引: {path}")
        return TrendingHistory(path, {})


_SECTION_ORDER = ("rss", "github", "hackernews", "insights")


def assemble_with_sentinels(sections: Dict[str, str]) -> str:
    """按固定顺序拼装四段 markdown,每段包 sentinel;空段整段省略。"""
    parts: List[str] = []
    for key in _SECTION_ORDER:
        body = (sections.get(key) or "").strip()
        if not body:
            continue
        parts.append(f"<!-- SECTION:{key} BEGIN -->\n{body}\n<!-- SECTION:{key} END -->")
    return "\n\n".join(parts)
