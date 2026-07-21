"""管理统一因子长表的连接、初始化、分区和批量写入。"""

from collections.abc import Iterable
import json
import re
from typing import Any

import dolphindb
import numpy as np
import pandas as pd

from config import DOLPHIN, INDEX_CODES


CORE_COLUMNS = ("time", "code", "factor", "value")
IS_ST_FACTOR = "is_st"
WEIGHT_PREFIX = "weight_"


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
    session.upload(
        {
            "coreDatabaseName": DOLPHIN.DATABASE,
            "coreTableName": DOLPHIN.TABLE,
            "coreInitialFactors": np.asarray(factors, dtype=str),
        }
    )
    return session.run(
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


def write_core_table(data: pd.DataFrame) -> int:
    """动态补分区后，通过多线程写入器追加统一因子数据。"""
    result = normalize_core_frame(data)
    if result.empty:
        return 0

    session = create_session()
    try:
        factors = result["factor"].unique()
        ensure_factor_partitions(factors, session=session)
    finally:
        session.close()
    writer = dolphindb.MultithreadedTableWriter(
        host=DOLPHIN.HOST,
        port=DOLPHIN.PORT,
        userId=DOLPHIN.USERNAME,
        password=DOLPHIN.PASSWORD,
        dbPath=DOLPHIN.DATABASE,
        tableName=DOLPHIN.TABLE,
        batchSize=10_000,
        throttle=1.0,
    )
    insertion_error: RuntimeError | None = None
    try:
        for row in result.itertuples(index=False, name=None):
            error = writer.insert(*row)
            if error.hasError():
                insertion_error = RuntimeError(
                    f"DolphinDB 插入失败：{error.errorCode} {error.errorInfo}"
                )
                break
    finally:
        writer.waitForThreadCompletion()

    if insertion_error is not None:
        raise insertion_error
    status = writer.getStatus()
    if status.hasError() or status.unsentRows or status.sendFailedRows:
        raise RuntimeError(
            "DolphinDB 批量写入失败："
            f"{status.errorCode} {status.errorInfo}; "
            f"unsentRows={status.unsentRows}, "
            f"sendFailedRows={status.sendFailedRows}"
        )
    return len(result)


__all__ = [
    "CORE_COLUMNS",
    "CORE_TABLE",
    "DEFAULT_FACTORS",
    "IS_ST_FACTOR",
    "WEIGHT_PREFIX",
    "create_session",
    "ensure_factor_partitions",
    "index_weight_factor",
    "initialize_database",
    "normalize_core_frame",
    "write_core_table",
]
