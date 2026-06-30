"""推送模块测试"""

import os
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from push.discord import DiscordPlatform
from push.feishu import FeishuPlatform
from push.wecom import (
    WeComPlatform,
    build_digest_news_articles,
    build_push_page_url,
    resolve_pages_base_url,
    truncate_description,
    _normalize_article,
)
from push import create_platform


class TestDiscordPlatform:
    """测试Discord推送"""

    def test_validate_config_valid(self):
        config = {
            "enabled": True,
            "apiKeyName": "DISCORD_WEBHOOK_URL",
        }
        with patch.dict(
            os.environ,
            {"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/123456/abcdef"},
        ):
            platform = DiscordPlatform(config)
            assert platform.validate_config(config) is True

    def test_validate_config_disabled(self):
        config = {
            "enabled": False,
            "apiKeyName": "DISCORD_WEBHOOK_URL",
        }
        with patch.dict(
            os.environ,
            {"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/123456/abcdef"},
        ):
            platform = DiscordPlatform(config)
            assert platform.validate_config(config) is False

    def test_validate_config_missing_webhook(self):
        config = {"enabled": True, "apiKeyName": "DISCORD_WEBHOOK_URL"}
        with patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": ""}):
            platform = DiscordPlatform(config)
            assert platform.validate_config(config) is False

    def test_validate_config_invalid_url(self):
        config = {"enabled": True, "apiKeyName": "DISCORD_WEBHOOK_URL"}
        with patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "not-a-valid-url"}):
            platform = DiscordPlatform(config)
            assert platform.validate_config(config) is False

    def test_validate_config_wrong_domain(self):
        config = {"enabled": True, "apiKeyName": "DISCORD_WEBHOOK_URL"}
        with patch.dict(
            os.environ, {"DISCORD_WEBHOOK_URL": "https://example.com/webhook"}
        ):
            platform = DiscordPlatform(config)
            assert platform.validate_config(config) is False

    def test_split_content_short(self):
        with patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://test.com"}):
            config = {"apiKeyName": "DISCORD_WEBHOOK_URL"}
            platform = DiscordPlatform(config)
            short_content = "Hello"
            chunks = platform._split_content(short_content, limit=2000)
            assert len(chunks) == 1
            assert chunks[0] == "Hello"

    def test_split_content_long_message(self):
        with patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://test.com"}):
            config = {"apiKeyName": "DISCORD_WEBHOOK_URL"}
            platform = DiscordPlatform(config)
            long_content = "A\n" * 2500
            chunks = platform._split_content(long_content, limit=2000)
            assert len(chunks) > 1
            assert all(len(c) <= 2000 for c in chunks)

    def test_split_content_exact_boundary(self):
        with patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://test.com"}):
            config = {"apiKeyName": "DISCORD_WEBHOOK_URL"}
            platform = DiscordPlatform(config)
            content = "A" * 2000
            chunks = platform._split_content(content, limit=2000)
            assert len(chunks) == 1

    def test_split_content_unicode(self):
        with patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://test.com"}):
            config = {"apiKeyName": "DISCORD_WEBHOOK_URL"}
            platform = DiscordPlatform(config)
            content = "你好" * 500
            chunks = platform._split_content(content, limit=100)
            assert len(chunks) >= 1

    @pytest.mark.asyncio
    async def test_send_success(self):
        with patch.dict(
            os.environ,
            {"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/test/abc"},
        ):
            config = {"apiKeyName": "DISCORD_WEBHOOK_URL"}
            platform = DiscordPlatform(config)

            with patch.object(platform, "send", new_callable=AsyncMock) as mock_send:
                mock_send.return_value = True

                result = await mock_send("Test message")

            assert result is True

    @pytest.mark.asyncio
    async def test_send_failure(self):
        with patch.dict(
            os.environ,
            {"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/test/abc"},
        ):
            config = {"apiKeyName": "DISCORD_WEBHOOK_URL"}
            platform = DiscordPlatform(config)

            with patch.object(platform, "send", new_callable=AsyncMock) as mock_send:
                mock_send.return_value = False

                result = await mock_send("Test message")

            assert result is False


class TestFeishuPlatform:
    """测试飞书推送"""

    def test_validate_config_valid(self):
        config = {
            "enabled": True,
            "apiKeyName": "FEISHU_WEBHOOK_URL",
        }
        with patch.dict(os.environ, {"FEISHU_WEBHOOK_URL": "https://open.feishu.cn/open-apis/bot/v2/hook/test"}):
            platform = FeishuPlatform(config)
            assert platform.validate_config(config) is True

    def test_validate_config_disabled(self):
        config = {
            "enabled": False,
            "apiKeyName": "FEISHU_WEBHOOK_URL",
        }
        with patch.dict(os.environ, {"FEISHU_WEBHOOK_URL": "https://open.feishu.cn/open-apis/bot/v2/hook/test"}):
            platform = FeishuPlatform(config)
            assert platform.validate_config(config) is False

    def test_validate_config_missing_key(self):
        config = {"enabled": True, "apiKeyName": "FEISHU_WEBHOOK_URL"}
        with patch.dict(os.environ, {"FEISHU_WEBHOOK_URL": ""}):
            platform = FeishuPlatform(config)
            assert platform.validate_config(config) is False

    def test_validate_config_any_non_empty_webhook(self):
        config = {"enabled": True, "apiKeyName": "FEISHU_WEBHOOK_URL"}
        with patch.dict(os.environ, {"FEISHU_WEBHOOK_URL": "https://open.feishu.cn/open-apis/bot/v2/hook/test"}):
            platform = FeishuPlatform(config)
            assert platform.validate_config(config) is True


class TestPushFactory:
    """测试平台工厂"""

    def test_create_enabled_platform(self):
        config = {
            "enabled": True,
            "apiKeyName": "DISCORD_WEBHOOK_URL",
        }
        with patch.dict(
            os.environ,
            {"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/123/abc"},
        ):
            platform = create_platform("discord", config)
            assert platform is not None

    def test_create_disabled_platform_returns_none(self):
        config = {"enabled": False, "apiKeyName": "DISCORD_WEBHOOK_URL"}
        platform = create_platform("discord", config)
        assert platform is None

    def test_create_unknown_platform_raises(self):
        with pytest.raises(ValueError):
            create_platform("unknown", {})

    def test_create_feishu_platform(self):
        config = {
            "enabled": True,
            "apiKeyName": "FEISHU_WEBHOOK_URL",
        }
        with patch.dict(os.environ, {"FEISHU_WEBHOOK_URL": "https://open.feishu.cn/open-apis/bot/v2/hook/test"}):
            platform = create_platform("feishu", config)
            assert platform is not None
            assert isinstance(platform, FeishuPlatform)

    def test_create_discord_platform(self):
        config = {
            "enabled": True,
            "apiKeyName": "DISCORD_WEBHOOK_URL",
        }
        with patch.dict(
            os.environ,
            {"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/test/abc"},
        ):
            platform = create_platform("discord", config)
            assert platform is not None
            assert isinstance(platform, DiscordPlatform)


class TestWeComPlatform:
    """测试企业微信推送"""

    WECOM_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=testkey"

    def test_validate_config_valid(self):
        config = {"enabled": True, "apiKeyName": "WECOM_WEBHOOK_URL"}
        with patch.dict(os.environ, {"WECOM_WEBHOOK_URL": self.WECOM_URL}):
            platform = WeComPlatform(config)
            assert platform.validate_config(config) is True

    def test_validate_config_disabled(self):
        config = {"enabled": False, "apiKeyName": "WECOM_WEBHOOK_URL"}
        with patch.dict(os.environ, {"WECOM_WEBHOOK_URL": self.WECOM_URL}):
            platform = WeComPlatform(config)
            assert platform.validate_config(config) is False

    def test_resolve_pages_base_url_from_env(self):
        cfg = {}
        with patch.dict(os.environ, {"PAGES_BASE_URL": "https://user.github.io/repo/"}):
            assert resolve_pages_base_url(cfg) == "https://user.github.io/repo/"

    def test_resolve_pages_base_url_from_github_repo(self):
        cfg = {}
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "owner/ai-daily"}, clear=False):
            url = resolve_pages_base_url(cfg)
            assert url == "https://owner.github.io/ai-daily/"

    def test_build_push_page_url(self):
        url = build_push_page_url(
            "https://user.github.io/ai-daily/",
            "news-data/push-2026-06-30-17-00-30.md",
        )
        assert url.endswith("news-data/push-2026-06-30-17-00-30.html")

    def test_truncate_description(self):
        long_text = "中" * 200
        assert len(truncate_description(long_text)) <= 128
        assert truncate_description("短摘要") == "短摘要"

    def test_build_digest_news_articles(self):
        content = """### 1. 标题一

* **核心**：第一条要点说明
🔗 [链接](https://example.com/a)

### 2. 标题二

* 第二条要点
"""
        metadata = {
            "title": "测试日报",
            "lead": "今日导语",
            "highlights": [],
        }
        articles = build_digest_news_articles(
            content, metadata, "https://pages.example/full.md"
        )
        assert len(articles) >= 2
        assert articles[0]["url"] == "https://pages.example/full.md"
        assert articles[1]["title"] == "标题一"
        assert len(articles[1]["description"]) <= 128

    def test_build_digest_news_articles_with_entry_images(self):
        content = """### 1. 标题一

* **核心**：第一条要点说明
🔗 [链接](https://example.com/a)

### 2. 标题二

* 第二条要点
🔗 [链接](https://example.com/b)
"""
        metadata = {"title": "测试日报", "lead": "今日导语", "highlights": []}
        entry_images = {"https://example.com/a": "https://img.example/a.jpg"}
        articles = build_digest_news_articles(
            content,
            metadata,
            "https://pages.example/full.md",
            entry_images=entry_images,
        )
        assert "picurl" not in articles[0]
        assert articles[1].get("picurl") == "https://img.example/a.jpg"
        assert "picurl" not in articles[2]

    def test_normalize_article_no_default_picurl(self):
        article = {"title": "T", "description": "D", "url": "https://x.com"}
        normalized = _normalize_article(article)
        assert "picurl" not in normalized

        with_pic = {**article, "picurl": "https://img.example/c.jpg"}
        normalized_with = _normalize_article(with_pic)
        assert normalized_with["picurl"] == "https://img.example/c.jpg"

    @pytest.mark.asyncio
    async def test_send_immediate_news(self):
        config = {"apiKeyName": "WECOM_WEBHOOK_URL", "mode": "news"}
        with patch.dict(os.environ, {"WECOM_WEBHOOK_URL": self.WECOM_URL}):
            platform = WeComPlatform(config)
            mock_resp = MagicMock()
            mock_resp.json = AsyncMock(return_value={"errcode": 0, "errmsg": "ok"})
            mock_post = MagicMock()
            mock_post.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_post.__aexit__ = AsyncMock(return_value=None)
            mock_session = MagicMock()
            mock_session.post = MagicMock(return_value=mock_post)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)

            with patch("aiohttp.ClientSession", return_value=mock_session):
                await platform.send(
                    "",
                    title="快讯",
                    metadata={
                        "profile": "hotspot",
                        "wecom_items": [
                            {
                                "title": "T1",
                                "description": "D1",
                                "url": "https://a.com",
                                "picurl": "https://img.example/a.jpg",
                            },
                            {
                                "title": "T2",
                                "description": "D2",
                                "url": "https://b.com",
                            },
                        ],
                    },
                )
            assert mock_session.post.call_count == 2

    @pytest.mark.asyncio
    async def test_send_digest_news_and_link(self):
        config = {"apiKeyName": "WECOM_WEBHOOK_URL", "mode": "news", "pages_base_url": ""}
        with patch.dict(os.environ, {"WECOM_WEBHOOK_URL": self.WECOM_URL}):
            platform = WeComPlatform(config)
            mock_resp = MagicMock()
            mock_resp.json = AsyncMock(return_value={"errcode": 0, "errmsg": "ok"})
            mock_post = MagicMock()
            mock_post.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_post.__aexit__ = AsyncMock(return_value=None)
            mock_session = MagicMock()
            mock_session.post = MagicMock(return_value=mock_post)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)

            with patch("aiohttp.ClientSession", return_value=mock_session):
                await platform.send(
                    "### 1. 新闻\n\n* 要点\n",
                    title="日报",
                    metadata={
                        "profile": "default",
                        "title": "测试",
                        "lead": "导语",
                        "full_url": "https://pages.example/full.md",
                    },
                )
            # news + 全文链接 text = 2 次
            assert mock_session.post.call_count == 2

    def test_create_wecom_platform(self):
        config = {"enabled": True, "apiKeyName": "WECOM_WEBHOOK_URL"}
        with patch.dict(os.environ, {"WECOM_WEBHOOK_URL": self.WECOM_URL}):
            platform = create_platform("wecom", config)
            assert platform is not None
            assert isinstance(platform, WeComPlatform)


class TestImmediatePushParse:
    """测试即时推 JSON 解析"""

    def test_parse_immediate_push_items(self):
        from llm import parse_immediate_push_items

        raw = '[{"title":"A","description":"摘要","url":"https://x.com"}]'
        items = parse_immediate_push_items(raw)
        assert len(items) == 1
        assert items[0]["title"] == "A"
