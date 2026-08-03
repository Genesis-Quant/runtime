"""配置项目统一使用的 Loguru 日志实例。"""

import sys

from loguru import logger

from runtime.config import PROD

logger.remove()
log_format = (
    "<g>{time:YYYY-MM-DD HH:mm:ss}</g> "
    "[<lvl>{level:^7}</lvl>] "
    "<blue>{file}</blue> | <r><u>{function}</u></r>: <c>{line}</c>行| "
    "{message}"
)
logger.add(
    sys.stdout,
    format=log_format,
    level="DEBUG",
    colorize=not PROD,
)
