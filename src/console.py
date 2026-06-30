"""控制台输出编码配置，兼容 Windows GBK 终端。"""

from __future__ import annotations

import io
import sys


def configure_stdio_utf8() -> None:
    """将 stdout/stderr 设为 UTF-8（errors=replace），避免 emoji 触发 UnicodeEncodeError。

    在 Windows 默认 GBK 代码页下，Python 3 仍可能按 GBK 编码 stdout；
    本函数在程序最早阶段调用，无需设置 PYTHONIOENCODING 即可安全输出 Unicode。
    """
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
                continue
            encoding = getattr(stream, "encoding", None) or ""
            if encoding.lower() not in ("utf-8", "utf8"):
                buffer = getattr(stream, "buffer", None)
                if buffer is not None:
                    wrapper = io.TextIOWrapper(
                        buffer,
                        encoding="utf-8",
                        errors="replace",
                        line_buffering=getattr(stream, "line_buffering", True),
                    )
                    setattr(sys, name, wrapper)
        except Exception:
            pass
