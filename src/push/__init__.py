"""推送平台模块"""

from typing import Dict, Optional

from .base import PushPlatform
from .discord import DiscordPlatform
from .feishu import FeishuPlatform
from .custom import CustomPlatform
from .wecom import WeComPlatform

# 全局 dry-run 开关，由 main --dry-run 设置
_dry_run: bool = False


def set_dry_run(enabled: bool):
    """设置是否仅打印推送 payload 而不实际发送。"""
    global _dry_run
    _dry_run = enabled


def is_dry_run() -> bool:
    return _dry_run


def create_platform(name: str, config: Dict) -> Optional[PushPlatform]:
    """工厂函数，创建推送平台实例"""
    platforms = {
        "discord": DiscordPlatform,
        "feishu": FeishuPlatform,
        "wecom": WeComPlatform,
        "custom": CustomPlatform,
    }

    if name not in platforms:
        raise ValueError(f"未知推送平台: {name}")

    platform_class = platforms[name]
    platform = platform_class(config)

    if not platform.validate_config(config):
        return None

    return platform


async def send_to_platforms(
    content: str,
    push_config: Dict,
    title: str = None,
    metadata: Optional[Dict] = None,
) -> bool:
    """发送内容到所有已启用且配置有效的平台。

    Returns:
        全部启用平台均推送成功时返回 True，任一失败或未配置有效平台时返回 False。
    """
    all_ok = True
    for platform_name, platform_conf in push_config.items():
        if not platform_conf.get("enabled"):
            continue

        platform = create_platform(platform_name, platform_conf)
        if platform is None:
            print(f"❌ {platform_name} 已启用但配置无效，跳过推送")
            all_ok = False
            continue

        try:
            if _dry_run:
                print(
                    f"🔍 [dry-run] 将推送到 {platform_name} | title={title!r} "
                    f"profile={(metadata or {}).get('profile')}"
                )
                if metadata and metadata.get("wecom_items"):
                    for i, item in enumerate(metadata["wecom_items"], 1):
                        print(f"   条目{i}: {item}")
                continue
            await platform.send(content, title, metadata)
            print(f"✅ 已推送到 {platform_name}")
        except Exception as e:
            print(f"❌ 推送到 {platform_name} 失败: {e}")
            all_ok = False
    return all_ok
