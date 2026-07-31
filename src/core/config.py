"""从环境变量加载 DolphinDB、Tushare 和数据更新配置。"""

import os
import warnings

from dotenv import load_dotenv

# 兼容从项目目录或其父目录启动。
load_dotenv(".env")
load_dotenv("../.env")

# 判断当前是否为生产环境
PROD = os.getenv("PROD") == "true"

if PROD:
    warnings.filterwarnings("ignore")


class DolphinSettings:
    """DolphinDB 连接及统一因子长表配置。"""

    HOST = os.getenv("DOLPHIN_HOST", "127.0.0.1")
    PORT = int(os.getenv("DOLPHIN_PORT", "8848"))
    USERNAME = os.getenv("DOLPHIN_USERNAME", "admin")
    PASSWORD = os.getenv("DOLPHIN_PASSWORD", "123456")

    DATABASE = os.getenv("DOLPHIN_CORE_DATABASE", "dfs://CoreData")
    TABLE = os.getenv("DOLPHIN_CORE_TABLE", "coreData")
    DIVIDEND_TABLE = os.getenv("DOLPHIN_DIVIDEND_TABLE", "stockDividend")


class ObjectStorageSettings:
    """S3 兼容对象存储连接配置。"""

    ENDPOINT_URL = os.getenv("OBJECT_STORAGE_ENDPOINT_URL")
    ACCESS_KEY_ID = os.getenv("OBJECT_STORAGE_ACCESS_KEY_ID")
    SECRET_ACCESS_KEY = os.getenv("OBJECT_STORAGE_SECRET_ACCESS_KEY")
    BUCKET = os.getenv("OBJECT_STORAGE_BUCKET")
    REGION = os.getenv("OBJECT_STORAGE_REGION", "us-east-1")
    ADDRESSING_STYLE = os.getenv("OBJECT_STORAGE_ADDRESSING_STYLE", "auto")
    ROOT_FOLDER = os.getenv(
        "OBJECT_STORAGE_ROOT_FOLDER",
        "arena-runtime",
    )


# 需要持久化并对外提供查询的指数代码。
INDEX_CODES = tuple(
    filter(
        None,
        map(
            str.strip,
            os.getenv(
                "INDEX_CODES",
                "000016.SH,000300.SH,000905.SH,000852.SH",
            ).split(","),
        ),
    )
)

# 数据回溯起点和 Tushare 数据接口访问令牌。
DATA_START_DATE = os.getenv("DATA_START_DATE", "2010-01-01")
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN")
