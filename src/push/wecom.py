"""企业微信（WeCom）群机器人推送平台。"""

import asyncio
import os
import re
from typing import Any, Dict, List, Optional

import aiohttp

from src.markdown_utils import extract_first_url, lookup_entry_image
from src.storage import extract_section

from .base import PushPlatform

# 企微 news 单条 description 建议上限（字符）
MAX_NEWS_DESC_CHARS = 128
MAX_NEWS_ARTICLES = 8
# text 消息 UTF-8 字节上限
MAX_TEXT_BYTES = 2048
# webhook POST 超时与重试（应对 GHA 到企微的偶发连接超时）
POST_TIMEOUT_SECONDS = 30
POST_MAX_RETRIES = 3


class WeComPlatform(PushPlatform):
    """企业微信群机器人 Webhook 推送（text / news，markdown 仅 fallback）。"""

    def __init__(self, config: Dict):
        super().__init__(config)
        self.api_key_name = config.get("apiKeyName", "WECOM_WEBHOOK_URL")
        self.webhook_url = os.environ.get(self.api_key_name, "")
        self.mode = config.get("mode", "news")  # news | text
        self.pages_base_url = resolve_pages_base_url(config)

    def validate_config(self, config: Dict) -> bool:
        """检查企业微信配置是否有效。"""
        if not config.get("enabled", False):
            return False
        api_key_name = config.get("apiKeyName", "WECOM_WEBHOOK_URL")
        webhook = os.environ.get(api_key_name, "")
        return bool(webhook and "qyapi.weixin.qq.com" in webhook)

    async def send(self, content: str, title: str = None, metadata: Dict = None):
        """根据 profile 选择 text / news / markdown fallback。"""
        metadata = metadata or {}
        profile = metadata.get("profile", "")

        if profile == "hotspot":
            await self._send_immediate(content, title, metadata)
            return

        if profile in ("default", "morning"):
            await self._send_digest(content, title, metadata)
            return

        # 未知 profile（如 LLM 异常通知）走 markdown fallback
        await self._send_markdown_fallback(content, title)

    async def send_text(self, text: str):
        """发送 text 类型消息。"""
        payload = {"msgtype": "text", "text": {"content": text}}
        await self._post_payload(payload)

    async def send_news(self, articles: List[Dict[str, str]]):
        """发送 news 类型消息，articles 最多 8 条。"""
        if not articles:
            return
        trimmed = [_normalize_article(a) for a in articles[:MAX_NEWS_ARTICLES]]
        payload = {"msgtype": "news", "news": {"articles": trimmed}}
        await self._post_payload(payload)

    async def _send_immediate(self, content: str, title: str, metadata: Dict):
        """即时热点：每条单独推一条短消息。"""
        items = metadata.get("wecom_items") or []
        if not items:
            items = _fallback_immediate_items(content, title)

        for item in items:
            if self.mode == "text":
                text = _format_immediate_text(item)
                await self.send_text(text)
            else:
                await self.send_news([item])

    async def _send_digest(self, content: str, title: str, metadata: Dict):
        """早晚报：1 条 news（最多 8 条目录）+ 可选全文链接 text。"""
        if "full_url" in metadata:
            full_url = metadata.get("full_url") or ""
        else:
            full_url = build_push_page_url(
                self.pages_base_url, metadata.get("push_file", "")
            )
        articles = build_digest_news_articles(
            content,
            metadata,
            full_url,
            entry_images=metadata.get("entry_images"),
        )

        if self.mode == "text":
            lines = [title or metadata.get("title", "AI Daily")]
            for i, art in enumerate(articles[:MAX_NEWS_ARTICLES], 1):
                lines.append(f"{i}. {art.get('title', '')}")
                if art.get("description"):
                    lines.append(f"   {art['description']}")
            if full_url:
                lines.append(f"\n📖 阅读全文：{full_url}")
            await self.send_text("\n".join(lines))
            return

        await self.send_news(articles)

        if full_url:
            digest_title = metadata.get("title") or (title or "AI Daily")
            link_text = f"📖 {digest_title}\n阅读全文：{full_url}"
            await self.send_text(link_text)

    async def _send_markdown_fallback(self, content: str, title: str = None):
        """markdown 仅作 fallback，尽量单条发送。"""
        full_content = f"# {title}\n\n{content}" if title else content
        if len(full_content.encode("utf-8")) <= 3500:
            payload = {"msgtype": "markdown", "markdown": {"content": full_content}}
            await self._post_payload(payload)
            return

        chunks = _split_by_bytes(full_content, 3500)
        for chunk in chunks:
            payload = {"msgtype": "markdown", "markdown": {"content": chunk}}
            await self._post_payload(payload)

    async def _post_payload(self, payload: Dict):
        """POST 到 webhook，不打印 URL / key；网络错误自动重试。"""
        timeout = aiohttp.ClientTimeout(total=POST_TIMEOUT_SECONDS)
        last_error: Optional[Exception] = None

        for attempt in range(1, POST_MAX_RETRIES + 1):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(self.webhook_url, json=payload) as resp:
                        data = await resp.json()
                        if data.get("errcode") != 0:
                            raise RuntimeError(
                                f"企业微信推送失败: errcode={data.get('errcode')} "
                                f"errmsg={data.get('errmsg')}"
                            )
                return
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
                last_error = exc
                if attempt >= POST_MAX_RETRIES:
                    break
                wait_seconds = 2**attempt
                print(
                    f"⚠️ 企微 webhook 请求失败（第 {attempt}/{POST_MAX_RETRIES} 次）: "
                    f"{exc}，{wait_seconds}s 后重试"
                )
                await asyncio.sleep(wait_seconds)

        raise RuntimeError(f"企业微信推送失败: {last_error}")


def resolve_pages_base_url(wecom_config: Dict) -> str:
    """解析 GitHub Pages 根 URL，优先 env，其次 config，再推断 GITHUB_REPOSITORY。"""
    url = os.environ.get("PAGES_BASE_URL") or wecom_config.get("pages_base_url", "")
    if url:
        return url.rstrip("/") + "/"

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if repo and "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner}.github.io/{name}/"

    return ""


def build_push_page_url(pages_base: str, push_file: str) -> str:
    """根据 Pages 根 URL 与 push 文件相对路径生成 HTML 全文链接。"""
    from src.pages.builder import push_file_to_html_url

    return push_file_to_html_url(pages_base, push_file)


def truncate_description(text: str, max_chars: int = MAX_NEWS_DESC_CHARS) -> str:
    """截断 news description，避免超出企微展示限制。"""
    text = (text or "").strip().replace("\n", " ")
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def _content_for_news_sections(content: str) -> str:
    """早报 sentinel 正文：抽取 RSS/GH/HN 段供 news 目录解析（跳过 insights）。"""
    if "<!-- SECTION:" not in (content or ""):
        return content or ""
    parts: List[str] = []
    for key in ("rss", "github", "hackernews"):
        section_md = extract_section(content, key).strip()
        if section_md:
            parts.append(section_md)
    return "\n\n".join(parts)


def build_digest_news_articles(
    content: str,
    metadata: Dict,
    full_url: str,
    entry_images: Optional[Dict[str, str]] = None,
) -> List[Dict[str, str]]:
    """从 digest 正文与 metadata 构建 news articles（最多 8 条）。"""
    articles: List[Dict[str, str]] = []
    digest_title = metadata.get("title") or "AI Daily 每日精选"
    lead = metadata.get("lead") or ""
    url_images = entry_images or {}

    if full_url:
        # 完整版 lead 卡片不配封面
        articles.append(
            {
                "title": digest_title,
                "description": truncate_description(lead or "点击阅读全文"),
                "url": full_url,
            }
        )

    sections = _parse_digest_sections(_content_for_news_sections(content))
    for sec in sections:
        if len(articles) >= MAX_NEWS_ARTICLES:
            break
        sec_url = sec.get("url") or full_url or "https://github.com"
        article: Dict[str, str] = {
            "title": sec["title"],
            "description": truncate_description(sec.get("description", "")),
            "url": sec_url,
        }
        picurl = lookup_entry_image(url_images, sec_url)
        if picurl:
            article["picurl"] = picurl
        articles.append(article)

    if not articles:
        highlights = metadata.get("highlights") or []
        for hl in highlights[:MAX_NEWS_ARTICLES]:
            articles.append(
                {
                    "title": hl,
                    "description": truncate_description(lead),
                    "url": full_url or "https://github.com",
                }
            )

    return articles[:MAX_NEWS_ARTICLES]


def _parse_digest_sections(content: str) -> List[Dict[str, str]]:
    """从 digest markdown 解析 ### 标题、首条要点与首个链接。"""
    sections: List[Dict[str, str]] = []
    if not content:
        return sections

    pattern = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(content))
    for i, match in enumerate(matches):
        title = re.sub(r"^\d+\.\s*", "", match.group(1).strip())
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[start:end].strip()

        desc = ""
        for line in body.splitlines():
            line = line.strip()
            if line.startswith("*") or line.startswith("-"):
                desc = re.sub(r"^[\*\-]\s*", "", line)
                desc = re.sub(r"\*\*([^*]+)\*\*", r"\1", desc)
                break

        url = extract_first_url(body)
        sections.append({"title": title, "description": desc, "url": url})

    return sections


def _extract_first_url(text: str) -> str:
    """兼容旧调用，委托 markdown_utils。"""
    return extract_first_url(text)


def _normalize_article(article: Dict[str, Any]) -> Dict[str, str]:
    """规范化 news article 字段；picurl 为可选，仅在有有效封面 URL 时写入。"""
    picurl = (article.get("picurl") or "").strip()
    normalized: Dict[str, str] = {
        "title": (article.get("title") or "AI Daily")[:128],
        "description": truncate_description(article.get("description", "")),
        "url": article.get("url") or "https://github.com",
    }
    if picurl:
        normalized["picurl"] = picurl
    return normalized


def _fallback_immediate_items(content: str, title: str) -> List[Dict[str, str]]:
    """从旧式 markdown 即时推正文降级提取单条。"""
    first_line = ""
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            first_line = re.sub(r"^[\*\-]\s*", "", line)
            first_line = re.sub(r"\*\*([^*]+)\*\*", r"\1", first_line)
            break
    url = _extract_first_url(content)
    return [
        {
            "title": title or "AI Daily 快讯",
            "description": truncate_description(first_line or content[:128]),
            "url": url or "https://github.com",
        }
    ]


def _format_immediate_text(item: Dict[str, str]) -> str:
    """格式化即时推 text 消息。"""
    parts = [item.get("title", "AI Daily 快讯")]
    if item.get("description"):
        parts.append(item["description"])
    if item.get("url"):
        parts.append(item["url"])
    text = "\n".join(parts)
    if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
        text = text.encode("utf-8")[: MAX_TEXT_BYTES - 3].decode("utf-8", errors="ignore") + "..."
    return text


def _split_by_bytes(text: str, max_bytes: int) -> List[str]:
    """按 UTF-8 字节长度切分。"""
    if len(text.encode("utf-8")) <= max_bytes:
        return [text]

    parts: List[str] = []
    current: List[str] = []
    size = 0

    for line in text.split("\n"):
        line_bytes = len(line.encode("utf-8")) + 1
        if size + line_bytes > max_bytes and current:
            parts.append("\n".join(current))
            current = [line]
            size = line_bytes
        else:
            current.append(line)
            size += line_bytes

    if current:
        parts.append("\n".join(current))

    return parts
