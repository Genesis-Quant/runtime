"""管理统一因子长表的连接、初始化、分区和批量写入。"""

from collections.abc import Iterable
import json
from typing import Any

import dolphindb
import numpy as np
import pandas as pd

from config import DOLPHIN
from core.utils.schema import (
    CODE_COLUMN,
    CORE_COLUMNS,
    FACTOR_COLUMN,
    TIME_COLUMN,
    VALUE_COLUMN,
    normalize_factors,
)
from core.utils.logging import logger

logger.info(f"DolphinDB: {DOLPHIN.HOST}:{DOLPHIN.PORT}")


def _ddb_string(value: str) -> str:
    """生成安全的 DolphinDB 字符串字面量。"""
    return json.dumps(value, ensure_ascii=False)


CORE_TABLE = (
    f"loadTable({_ddb_string(DOLPHIN.DATABASE)}, "
    f"{_ddb_string(DOLPHIN.TABLE)})"
)


def create_session():
    """连接 DolphinDB，不检查或初始化业务库表。"""
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


def ensure_core_table(session: Any, factors: list[str]) -> None:
    """统一因子库表缺失时，使用已有会话完成初始化。"""
    if session.run(
            f"existsDatabase({_ddb_string(DOLPHIN.DATABASE)})"
    ) and session.run(
        f"existsTable({_ddb_string(DOLPHIN.DATABASE)}, {_ddb_string(DOLPHIN.TABLE)})"
    ):
        return

    logger.info(
        f"初始化 DolphinDB 统一因子表：{DOLPHIN.DATABASE}/"
        f"{DOLPHIN.TABLE}，初始 factor={len(factors):,} 个"
    )
    session.upload(
        {
            "coreDatabaseName": DOLPHIN.DATABASE,
            "coreTableName": DOLPHIN.TABLE,
            "coreInitialFactors": np.asarray(factors, dtype=str),
        }
    )
    result = session.run(
        f"""
        def initializeCoreDatabase(dbName, tableName, initialFactors) {{
            // 创建按月和 factor 组合分区的统一 TSDB 长表。
            if (size(initialFactors) == 0) throw "initialFactors 不能为空"
            if (!existsDatabase(dbName)) {{
                database(
                    directory=dbName,
                    partitionType=COMPO,
                    partitionScheme=[
                        database(
                            ,
                            partitionType=RANGE,
                            partitionScheme=date(datetimeAdd(1990.01M, 0..61*12, "M"))
                        ),
                        database(
                            ,
                            partitionType=VALUE,
                            partitionScheme=symbol(initialFactors)
                        )
                    ],
                    engine="TSDB"
                )
            }}

            db = database(dbName)
            if (!existsTable(dbName, tableName)) {{
                db.createPartitionedTable(
                    table=table(
                        1:0,
                        ["{TIME_COLUMN}", "{CODE_COLUMN}", "{FACTOR_COLUMN}", "{VALUE_COLUMN}"],
                        [TIMESTAMP, SYMBOL, SYMBOL, DOUBLE]
                    ),
                    tableName=tableName,
                    partitionColumns=["{TIME_COLUMN}", "{FACTOR_COLUMN}"],
                    sortColumns=[`{CODE_COLUMN}, `{TIME_COLUMN}],
                    keepDuplicates=LAST,
                    sortKeyMappingFunction=[hashBucket{{, 500}}]
                )
            }}
            return "CoreData initialized"
        }}

        initializeCoreDatabase(coreDatabaseName, coreTableName, coreInitialFactors)
        """
    )
    logger.success(str(result))


def ensure_factor_partitions(
        values: Iterable[str],
        *,
        session: Any | None = None,
) -> list[str]:
    """补建缺失的 factor VALUE 分区并返回新增分区。"""
    factors = normalize_factors(values)
    owns_session = session is None
    current = create_session() if owns_session else session
    try:
        ensure_core_table(current, factors)

        schema = current.run(
            f"schema(database({_ddb_string(DOLPHIN.DATABASE)}))"
        )
        existing = {str(value) for value in schema["partitionSchema"][1]}
        missing = [factor for factor in factors if factor not in existing]
        if missing:
            preview = missing[:10]
            remainder = len(missing) - len(preview)
            suffix = f"，其余 {remainder:,} 个" if remainder else ""
            logger.info(
                f"DolphinDB 新增 {len(missing):,} 个 factor 分区："
                f"{preview}{suffix}"
            )
            current.upload(
                {"coreNewFactorPartitions": np.asarray(missing, dtype=str)}
            )
            current.run(
                f"addValuePartitions(database({_ddb_string(DOLPHIN.DATABASE)}), "
                "symbol(coreNewFactorPartitions), 1)"
            )
        return missing
    finally:
        if owns_session:
            current.close()


class CoreTableWriter:
    """复用一个多线程写入器，持续追加已规范的统一长表数据。

    ``append`` 是低层写入边界，只接受由 ``BaseWorker.normalize_result``
    完成清洗的四列 Worker 数据。
    """

    def __init__(
            self,
            factors: Iterable[str],
            *,
            thread_count: int = 3,
    ) -> None:
        """保存固定 factor 和写入配置，首次追加数据时再建立连接。"""
        if thread_count <= 0:
            raise ValueError("thread_count 必须大于 0")

        self.factors = tuple(normalize_factors(factors))
        self.factor_set = set(self.factors)
        self.thread_count = min(thread_count, len(self.factors))
        self.pool: Any | None = None
        self.appender: Any | None = None
        self.prepared = False
        self.closed = False

    def prepare(self) -> None:
        """确保数据库、表和 factor 分区存在，但不创建写入连接池。"""
        if self.closed:
            raise RuntimeError("CoreTableWriter 已关闭")
        if self.prepared:
            return
        ensure_factor_partitions(self.factors)
        self.prepared = True

    def open(self) -> Any:
        """补建 factor 分区，返回整个更新过程复用的写入器。"""
        if self.closed:
            raise RuntimeError("CoreTableWriter 已关闭")
        if self.appender is not None:
            return self.appender

        self.prepare()

        pool = dolphindb.DBConnectionPool(
            DOLPHIN.HOST,
            DOLPHIN.PORT,
            threadNum=self.thread_count,
            userid=DOLPHIN.USERNAME,
            password=DOLPHIN.PASSWORD,
            reConnect=True,
            show_output=False,
        )
        try:
            appender = dolphindb.PartitionedTableAppender(
                db_path=DOLPHIN.DATABASE,
                table_name=DOLPHIN.TABLE,
                partition_col=FACTOR_COLUMN,
                pool=pool,
            )
        except Exception:
            pool.shutDown()
            raise
        self.pool = pool
        self.appender = appender
        logger.debug(
            f"DolphinDB Writer 已创建：threads={self.thread_count}，"
            f"factor={len(self.factors):,} 个"
        )
        return appender

    def append(self, data: pd.DataFrame) -> int:
        """原样批量追加四列成品数据，并返回实际写入行数。"""
        if self.closed:
            raise RuntimeError("CoreTableWriter 已关闭")
        if not isinstance(data, pd.DataFrame):
            raise TypeError("待写入数据必须是 pandas.DataFrame")
        if data.empty:
            return 0
        if tuple(data.columns) != CORE_COLUMNS:
            raise ValueError(
                "待写入数据列必须严格为 "
                f"{list(CORE_COLUMNS)}，实际为 {list(data.columns)}"
            )

        # 这里只做分区安全检查；任何数据转换都属于上游规范化职责。
        unknown = set(data[FACTOR_COLUMN].unique()) - self.factor_set
        if unknown:
            raise ValueError(f"待写入数据包含未声明 factor：{sorted(unknown)}")

        rows = int(self.open().append(data))
        if rows != len(data):
            raise RuntimeError(
                f"DolphinDB 写入行数不一致：预期 {len(data):,}，实际 {rows:,}"
            )
        return rows

    def close(self) -> None:
        """关闭连接池；未打开或已关闭时不执行额外操作。"""
        if self.closed:
            return
        self.closed = True
        pool = self.pool
        self.appender = None
        self.pool = None
        if pool is not None and not pool.is_shutdown():
            pool.shutDown()

    def __enter__(self) -> "CoreTableWriter":
        """先准备库表和分区，再返回惰性创建连接的写入器上下文。"""
        self.prepare()
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        """退出上下文时完成所有已提交写入。"""
        self.close()


__all__ = [
    "CORE_TABLE",
    "CoreTableWriter",
    "create_session",
]
