"""
配置文件模块

从 .env 文件中加载环境变量，集中管理项目所需的各项配置，
包括 DolphinDB 数据库连接信息和 Tushare 数据接口的 Token。
"""

import os
from dotenv import load_dotenv

# 加载当前目录和上级目录的 .env 文件，确保不同运行路径下都能读取到配置
load_dotenv(".env")
load_dotenv("../.env")

# 判断当前是否为生产环境
PROD = os.getenv("PROD") == "true"


class DOLPHIN:
    """DolphinDB 数据库连接配置"""

    HOST = os.getenv("DOLPHIN_HOST")          # 数据库主机地址
    PORT = int(os.getenv("DOLPHIN_PORT"))     # 数据库端口号
    USERNAME = os.getenv("DOLPHIN_USERNAME")  # 数据库用户名
    PASSWORD = os.getenv("DOLPHIN_PASSWORD")  # 数据库密码

    class DAILY:
        """日频数据相关的库表配置"""

        DB = os.getenv("DOLPHIN_DAILY_DB")        # 日频数据所在的数据库名
        STOCK = os.getenv("DOLPHIN_DAILY_STOCK_TB")  # 日频股票行情数据表名
        INDEX_WEIGHT = os.getenv("DOLPHIN_DAILY_INDEX_WEIGHT_TB", "indexWeight")  # 指数成分股权重表名


# 需要持久化并对外提供查询的指数代码。
INDEX_CODES = tuple(filter(None, map(
    str.strip,
    os.getenv(
        "INDEX_CODES",
        "000016.SH,000300.SH,000905.SH,000852.SH"
    ).split(",")
)))


# Tushare 数据接口的访问令牌
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN")
