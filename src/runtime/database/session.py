"""创建 DolphinDB 会话。"""

from typing import Any

import dolphindb

from runtime.config import DolphinSettings
from runtime.utils import logger, validate_dolphindb_identifier


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
    validate_dolphindb_identifier(name)
    logger.info(f"session.run: 检查变量 {name} 是否存在")
    return bool(session.run(f"`{name} in objs(true).name"))


def create_session() -> Any:
    """连接 DolphinDB，不检查或初始化业务库表。"""
    logger.info(
        f"DolphinDB: {DolphinSettings.HOST}:{DolphinSettings.PORT}"
    )
    session = dolphindb.session(show_output=True)
    redirect_session_output(session)
    if session.connect(
        DolphinSettings.HOST,
        DolphinSettings.PORT,
        DolphinSettings.USERNAME,
        DolphinSettings.PASSWORD,
    ):
        return session
    session.close()
    raise ConnectionError(
        f"无法连接 DolphinDB："
        f"{DolphinSettings.HOST}:{DolphinSettings.PORT}"
    )
