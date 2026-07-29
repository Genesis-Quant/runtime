"""创建 DolphinDB 会话。"""

import re
from typing import Any

import dolphindb

from core.config import DOLPHIN
from core.utils import logger


class LoguruSink(dolphindb.logger.Sink):
    """把 DolphinDB session 消息转发到 Loguru。"""

    def __init__(self) -> None:
        super().__init__("loguru")

    def handle(self, msg: Any) -> None:
        logger.log(msg.level.name, msg.log.rstrip("\r\n"))

    def flush(self) -> None:
        return None


def redirect_session_output(session: Any) -> None:
    """关闭 DolphinDB stdout sink，并注册一次 Loguru sink。"""
    message_logger = session.msg_logger
    message_logger.disable_stdout_sink()
    if not any(sink.name == "loguru" for sink in message_logger.list_sinks()):
        message_logger.add_sink(LoguruSink())


def has_session_variable(session: Any, name: str) -> bool:
    """返回当前 DolphinDB session 中是否存在指定变量。"""
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name) is None:
        raise ValueError(f"不是合法的 DolphinDB 变量名：{name!r}")
    logger.info(f"session.run: 检查变量 {name} 是否存在")
    return bool(session.run(f"`{name} in objs(true).name"))


def create_session() -> Any:
    """连接 DolphinDB，不检查或初始化业务库表。"""
    logger.info(f"DolphinDB: {DOLPHIN.HOST}:{DOLPHIN.PORT}")
    session = dolphindb.session(show_output=True)
    redirect_session_output(session)
    if session.connect(DOLPHIN.HOST, DOLPHIN.PORT, DOLPHIN.USERNAME, DOLPHIN.PASSWORD):
        return session
    session.close()
    raise ConnectionError(f"无法连接 DolphinDB：{DOLPHIN.HOST}:{DOLPHIN.PORT}")
