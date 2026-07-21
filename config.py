"""从环境变量加载 DolphinDB、Tushare 和数据更新配置。"""

import os
from dotenv import load_dotenv

# 兼容从项目目录或其父目录启动。
load_dotenv(".env")
load_dotenv("../.env")

# 判断当前是否为生产环境
PROD = os.getenv("PROD") == "true"


class DOLPHIN:
    """DolphinDB 连接及统一因子长表配置。"""

    HOST = os.getenv("DOLPHIN_HOST", "127.0.0.1")
    PORT = int(os.getenv("DOLPHIN_PORT", "8848"))
    USERNAME = os.getenv("DOLPHIN_USERNAME", "admin")
    PASSWORD = os.getenv("DOLPHIN_PASSWORD", "123456")

    DATABASE = os.getenv("DOLPHIN_CORE_DATABASE", "dfs://CoreData")
    TABLE = os.getenv("DOLPHIN_CORE_TABLE", "coreData")
    CALENDAR_FACTOR = os.getenv("DOLPHIN_CORE_CALENDAR_FACTOR", "close")


# 需要持久化并对外提供查询的指数代码。
INDEX_CODES = tuple(filter(None, map(
    str.strip,
    os.getenv(
        "INDEX_CODES",
        "000016.SH,000300.SH,000905.SH,000852.SH"
    ).split(",")
)))

# 数据回溯起点和 Tushare 数据接口访问令牌。
DATA_START_DATE = os.getenv("DATA_START_DATE", "2010-01-01")
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN")
