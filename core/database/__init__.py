"""统一导出 DolphinDB 长表连接、初始化与写入能力。"""

from .session import (
    CORE_TABLE,
    CoreTableWriter,
    create_session
)

__all__ = [
    "CORE_TABLE",
    "CoreTableWriter",
    "create_session"
]
