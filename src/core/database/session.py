"""创建 DolphinDB 会话。"""

from typing import Any

import dolphindb

from core.config import DOLPHIN
from core.utils import logger


def create_session() -> Any:
    """连接 DolphinDB，不检查或初始化业务库表。"""
    logger.info(f"DolphinDB: {DOLPHIN.HOST}:{DOLPHIN.PORT}")
    session = dolphindb.session()
    if session.connect(
        DOLPHIN.HOST,
        DOLPHIN.PORT,
        DOLPHIN.USERNAME,
        DOLPHIN.PASSWORD,
    ):
        return session
    session.close()
    raise ConnectionError(f"无法连接 DolphinDB：{DOLPHIN.HOST}:{DOLPHIN.PORT}")


__all__ = ["create_session"]
