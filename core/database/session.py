"""管理统一因子长表的连接、初始化、分区和批量写入。"""

from collections.abc import Iterable
import json
import re
from typing import Any

import dolphindb
import numpy as np
import pandas as pd

from config import DOLPHIN, INDEX_CODES
from core.utils.logging import logger


TIME_COLUMN = "time"
CODE_COLUMN = "code"
FACTOR_COLUMN = "factor"
VALUE_COLUMN = "value"
CORE_COLUMNS = (
    TIME_COLUMN,
    CODE_COLUMN,
    FACTOR_COLUMN,
    VALUE_COLUMN,
)
IS_ST_FACTOR = "is_st"
WEIGHT_PREFIX = "weight_"

logger.info(f"DolphinDB: {DOLPHIN.HOST}:{DOLPHIN.PORT}")


def index_weight_factor(index_code: str) -> str:
    """把指数代码转换为统一长表中的权重因子名。"""
    normalized = str(index_code).strip().upper()
    if re.fullmatch(r"[A-Z0-9]+\.[A-Z0-9]+", normalized) is None:
        raise ValueError(f"无效指数代码：{index_code!r}")
    return WEIGHT_PREFIX + normalized.replace(".", "")


DEFAULT_FACTORS = (
    "open",
    "high",
    "low",
    "close",
    IS_ST_FACTOR,
    *(index_weight_factor(code) for code in INDEX_CODES),
)


def _ddb_string(value: str) -> str:
    """生成安全的 DolphinDB 字符串字面量。"""
    return json.dumps(value, ensure_ascii=False)


CORE_TABLE = (
    f"loadTable({_ddb_string(DOLPHIN.DATABASE)}, "
    f"{_ddb_string(DOLPHIN.TABLE)})"
)


def _connect_session():
    """创建原始 DolphinDB 连接，不检查业务库表。"""
    session = dolphindb.session()
    connected = session.connect(
        DOLPHIN.HOST,
        DOLPHIN.PORT,
        DOLPHIN.USERNAME,
        DOLPHIN.PASSWORD,
    )
    if connected is False:
        session.close()
        raise ConnectionError(
            f"无法连接 DolphinDB：{DOLPHIN.HOST}:{DOLPHIN.PORT}"
        )
    return session


def _core_table_exists(session: Any) -> bool:
    """返回统一因子数据库和数据表是否都已存在。"""
    database_exists = bool(
        session.run(f"existsDatabase({_ddb_string(DOLPHIN.DATABASE)})")
    )
    if not database_exists:
        return False
    return bool(
        session.run(
            f"existsTable({_ddb_string(DOLPHIN.DATABASE)}, "
            f"{_ddb_string(DOLPHIN.TABLE)})"
        )
    )


def create_session():
    """连接 DolphinDB，并在统一因子库表缺失时自动初始化。"""
    session = _connect_session()
    try:
        if not _core_table_exists(session):
            logger.warning("DolphinDB 统一因子库表不存在，开始自动初始化")
            _initialize_with_session(session, list(DEFAULT_FACTORS))
    except Exception:
        session.close()
        raise
    return session


def _normalize_factors(values: Iterable[str]) -> list[str]:
    """清理、去重并校验 factor 分区值。"""
    factors: list[str] = []
    for value in values:
        if value is None:
            continue
        factor = str(value).strip()
        if not factor:
            continue
        if factor not in factors:
            factors.append(factor)
    if not factors:
        raise ValueError("factor 至少包含一个非空值")
    return factors


def _initialize_with_session(session: Any, factors: list[str]) -> str:
    """使用已有会话幂等创建组合分区数据库和 TSDB 表。"""
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
        """
def initializeCoreDatabase(dbName, tableName, initialFactors) {
    // 创建按月和 factor 组合分区的统一 TSDB 长表。
    if (size(initialFactors) == 0) throw "initialFactors 不能为空"
    if (!existsDatabase(dbName)) {
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
    }

    db = database(dbName)
    if (!existsTable(dbName, tableName)) {
        db.createPartitionedTable(
            table=table(
                1:0,
                ["time", "code", "factor", "value"],
                [TIMESTAMP, SYMBOL, SYMBOL, DOUBLE]
            ),
            tableName=tableName,
            partitionColumns=["time", "factor"],
            sortColumns=[`code, `time],
            keepDuplicates=LAST,
            sortKeyMappingFunction=[hashBucket{, 500}]
        )
    }
    return "CoreData initialized"
}

initializeCoreDatabase(coreDatabaseName, coreTableName, coreInitialFactors)
"""
    )
    logger.success(str(result))
    return result


def initialize_database(
    initial_factors: Iterable[str] = DEFAULT_FACTORS,
    *,
    session: Any | None = None,
) -> str:
    """幂等创建数据库和统一长表，不在模块导入时产生连接副作用。"""
    factors = _normalize_factors(initial_factors)
    owns_session = session is None
    current = _connect_session() if owns_session else session
    try:
        return _initialize_with_session(current, factors)
    finally:
        if owns_session:
            current.close()


def ensure_factor_partitions(
    values: Iterable[str],
    *,
    session: Any | None = None,
) -> list[str]:
    """补建缺失的 factor VALUE 分区并返回新增分区。"""
    factors = _normalize_factors(values)
    owns_session = session is None
    current = create_session() if owns_session else session
    try:
        exists = current.run(
            f"existsDatabase({_ddb_string(DOLPHIN.DATABASE)})"
        )
        if not exists:
            _initialize_with_session(current, [*DEFAULT_FACTORS, *factors])

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


def normalize_core_frame(data: pd.DataFrame) -> pd.DataFrame:
    """校验并规范为 time/code/factor/value 四列长表。"""
    if not isinstance(data, pd.DataFrame):
        raise TypeError("待写入数据必须是 pandas.DataFrame")
    missing = set(CORE_COLUMNS) - set(data.columns)
    if missing:
        raise ValueError(f"待写入数据缺少列：{sorted(missing)}")
    if data.empty:
        return pd.DataFrame(columns=CORE_COLUMNS)

    result = data.loc[:, list(CORE_COLUMNS)].copy()
    result["time"] = pd.to_datetime(result["time"], errors="coerce")
    result["code"] = result["code"].astype("string").str.strip()
    result["factor"] = result["factor"].astype("string").str.strip()
    result["value"] = pd.to_numeric(result["value"], errors="coerce")

    invalid = result[list(CORE_COLUMNS)].isna().any(axis=1)
    invalid |= result["code"].eq("") | result["factor"].eq("")
    invalid |= ~np.isfinite(result["value"].to_numpy(dtype=float))
    if invalid.any():
        raise ValueError(
            f"待写入数据包含 {int(invalid.sum())} 行无效 time/code/factor/value"
        )

    return (
        result.drop_duplicates(["time", "code", "factor"], keep="last")
        .sort_values(["factor", "code", "time"])
        .reset_index(drop=True)
    )


class CoreTableWriter:
    """复用一个多线程写入器，持续追加已规范的统一长表数据。

    ``append`` 是低层写入边界，只接受已完成清洗的四列数据。Worker 数据
    由 ``BaseWorker.normalize_result`` 负责规范；其他调用者应使用
    :func:`write_core_table`，由其执行一次 ``normalize_core_frame``。
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

        self.factors = tuple(_normalize_factors(factors))
        self.factor_set = set(self.factors)
        self.thread_count = min(thread_count, len(self.factors))
        self.pool: Any | None = None
        self.appender: Any | None = None
        self.closed = False

    def open(self) -> None:
        """补建一次 factor 分区并创建整个更新过程复用的写入器。"""
        if self.closed:
            raise RuntimeError("CoreTableWriter 已关闭")
        if self.appender is not None:
            return

        session = create_session()
        try:
            ensure_factor_partitions(self.factors, session=session)
        finally:
            session.close()

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
                partition_col="factor",
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
        unknown = set(data["factor"].unique()) - self.factor_set
        if unknown:
            raise ValueError(f"待写入数据包含未声明 factor：{sorted(unknown)}")

        self.open()
        appender = self.appender
        if appender is None:
            raise RuntimeError("DolphinDB Writer 创建失败")
        rows = int(appender.append(data))
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
        if pool is None:
            return
        if not pool.is_shutdown():
            pool.shutDown()

    def __enter__(self) -> "CoreTableWriter":
        """返回惰性创建的写入器上下文。"""
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        """退出上下文时完成所有已提交写入。"""
        self.close()


def write_core_table(data: pd.DataFrame) -> int:
    """为非 Worker 调用规范一次长表，并返回实际写入行数。"""
    # Worker 直接复用 CoreTableWriter；这里只为独立调用者承担规范化。
    result = normalize_core_frame(data)
    if result.empty:
        return 0

    logger.debug(
        f"DolphinDB 开始写入 {len(result):,} 行、"
        f"{result['factor'].nunique():,} 个 factor"
    )
    with CoreTableWriter(result["factor"].unique()) as writer:
        rows = writer.append(result)
    logger.debug(f"DolphinDB 写入完成，共 {rows:,} 行")
    return rows


__all__ = [
    "CODE_COLUMN",
    "CORE_COLUMNS",
    "CORE_TABLE",
    "CoreTableWriter",
    "DEFAULT_FACTORS",
    "FACTOR_COLUMN",
    "IS_ST_FACTOR",
    "TIME_COLUMN",
    "VALUE_COLUMN",
    "WEIGHT_PREFIX",
    "create_session",
    "ensure_factor_partitions",
    "index_weight_factor",
    "initialize_database",
    "normalize_core_frame",
    "write_core_table",
]
