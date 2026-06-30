"""Markdown / YAML frontmatter 公共辅助。

供 storage、llm 等模块复用,避免重复实现。本模块零业务依赖,仅依赖 yaml/json/re。
"""

import json
import re
from typing import Any, Dict, List, Tuple

import yaml

__all__ = [
    "yaml_value",
    "dump_frontmatter",
    "parse_frontmatter",
    "normalize_str_list",
    "extract_first_url",
    "normalize_url",
    "lookup_entry_image",
]

_MD_LINK_RE = re.compile(r"\]\((https?://[^)]+)\)")
_HREF_RE = re.compile(r'href="(https?://[^"]+)"')
_BARE_URL_RE = re.compile(r"(https?://[^\s\])>]+)")


def yaml_value(v: Any) -> str:
    """把单个值序列化为 YAML 合法的 token,借道 JSON 语法。

    依据:JSON 是 YAML 1.2 的真子集,任何 json.dumps 的输出都是合法 YAML 标量/序列/映射。
    始终带引号的字符串可以避免 PyYAML 的若干怪癖(折行、未引号字符串歧义、unicode 转义)。
    """
    if isinstance(v, (dict, list, str)):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return ""
    return str(v)


def dump_frontmatter(meta: Dict) -> str:
    """把扁平 metadata dict 序列化为 frontmatter 文本(不含包围的 `---`)。

    保留插入顺序(title 在前,bookkeeping 字段在后)。仅支持扁平结构 —— 当前所有
    metadata 都是扁平的,无需处理嵌套。
    """
    return "".join(f"{k}: {yaml_value(v)}\n" for k, v in meta.items())


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def parse_frontmatter(text: str) -> Tuple[Dict, str]:
    """从 markdown 文本中分离 YAML frontmatter 与正文。

    返回 (metadata_dict, body)。无 frontmatter / YAML 解析失败 / 非 dict 时返回
    ({}, 原文) —— 保证降级路径不丢内容,调用方可凭 metadata_dict 是否为空判定。
    """
    match = _FRONTMATTER_RE.match(text.strip())
    if not match:
        return {}, text

    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        print("frontmatter 数据段解析失败")
        return {}, text

    if not isinstance(meta, dict):
        return {}, text

    return meta, match.group(2).strip()


def normalize_str_list(value: Any) -> List[str]:
    """将 str/list/None 规整为非空字符串列表。

    用于兜底 LLM 输出的列表型字段(如 frontmatter 中的 highlights):单字符串包裹为单元素列表,
    null/非列表/非字符串返回空列表,列表中夹杂的空白项过滤掉。不做数量截断。
    """
    if not value:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        return []
    return [str(x).strip() for x in items if str(x).strip()]


def extract_first_url(text: str) -> str:
    """提取 markdown 链接、HTML href 或裸 URL。"""
    md_match = _MD_LINK_RE.search(text or "")
    if md_match:
        return md_match.group(1)
    href_match = _HREF_RE.search(text or "")
    if href_match:
        return href_match.group(1)
    bare_match = _BARE_URL_RE.search(text or "")
    return bare_match.group(1) if bare_match else ""


def normalize_url(url: str) -> str:
    """规范化 URL 以便 entry_images 匹配。"""
    normalized = (url or "").strip()
    if not normalized:
        return ""
    if "#" in normalized:
        normalized = normalized.split("#", 1)[0]
    if normalized.endswith("/") and len(normalized) > len("https://a/"):
        normalized = normalized.rstrip("/")
    return normalized


def lookup_entry_image(entry_images: Dict[str, str], url: str) -> str:
    """按规范化 URL 查找配图。"""
    if not entry_images or not url:
        return ""
    target = normalize_url(url)
    for key, image in entry_images.items():
        if normalize_url(key) == target:
            return image or ""
    return entry_images.get(url, "") or ""
