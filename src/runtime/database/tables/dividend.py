"""管理 Backtest 使用的股票分红宽表。"""

import json
from typing import Any

import numpy as np
import pandas as pd

from runtime.config import DolphinSettings
from runtime.utils import logger

from ..session import create_session

STOCK_DIVIDEND_COLUMNS = (
    "symbol",
    "endDate",
    "annDate",
    "recordDate",
    "exDate",
    "payDate",
    "divListDate",
    "bonusRatio",
    "capitalConversion",
    "afterTaxCashDiv",
    "allotPrice",
    "allotRatio",
    "impAnnDate",
)
STOCK_DIVIDEND_DATE_COLUMNS = (
    "endDate",
    "annDate",
    "recordDate",
    "exDate",
    "payDate",
    "divListDate",
    "impAnnDate",
)
STOCK_DIVIDEND_REQUIRED_DATE_COLUMNS = (
    "endDate",
    "recordDate",
    "exDate",
)
STOCK_DIVIDEND_VALUE_COLUMNS = (
    "bonusRatio",
    "capitalConversion",
    "afterTaxCashDiv",
    "allotPrice",
    "allotRatio",
)
STOCK_DIVIDEND_EMPTY = pd.DataFrame(
    {
        "symbol": pd.Series(dtype="object"),
        **{
            column: pd.Series(dtype="datetime64[ns]")
            for column in STOCK_DIVIDEND_DATE_COLUMNS
        },
        **{
            column: pd.Series(dtype="float64")
            for column in STOCK_DIVIDEND_VALUE_COLUMNS
        },
    }
).loc[:, list(STOCK_DIVIDEND_COLUMNS)]
STOCK_DIVIDEND_TABLE = (
    f"loadTable({json.dumps(DolphinSettings.DATABASE)}, "
    f"{json.dumps(DolphinSettings.DIVIDEND_TABLE)})"
)


def ensure_stock_dividend_table(session: Any) -> None:
    """在 CoreData 中创建股票分红维度表，已存在时不做处理。"""
    session.upload(
        {
            "coreDividendDatabaseName": DolphinSettings.DATABASE,
            "coreDividendTableName": DolphinSettings.DIVIDEND_TABLE,
        }
    )
    session.run(
        """
        if (!existsTable(coreDividendDatabaseName, coreDividendTableName)) {
            coreDividendSchema = table(
                1:0,
                [
                    "symbol",
                    "endDate",
                    "annDate",
                    "recordDate",
                    "exDate",
                    "payDate",
                    "divListDate",
                    "bonusRatio",
                    "capitalConversion",
                    "afterTaxCashDiv",
                    "allotPrice",
                    "allotRatio",
                    "impAnnDate"
                ],
                [
                    SYMBOL,
                    DATE,
                    DATE,
                    DATE,
                    DATE,
                    DATE,
                    DATE,
                    DOUBLE,
                    DOUBLE,
                    DOUBLE,
                    DOUBLE,
                    DOUBLE,
                    DATE
                ]
            )
            database(coreDividendDatabaseName).createDimensionTable(
                table=coreDividendSchema,
                tableName=coreDividendTableName,
                sortColumns=`symbol`recordDate`exDate,
                keepDuplicates=LAST
            )
        }
        """
    )


def normalize_stock_dividends(data: pd.DataFrame) -> pd.DataFrame:
    """校验并规范可直接写入股票分红维度表的数据。"""
    if not isinstance(data, pd.DataFrame):
        raise TypeError("股票分红数据必须是 pandas.DataFrame")
    if missing := set(STOCK_DIVIDEND_COLUMNS) - set(data.columns):
        raise ValueError(f"股票分红数据缺少列：{sorted(missing)}")
    if data.empty:
        return STOCK_DIVIDEND_EMPTY.copy()

    result = data.loc[:, list(STOCK_DIVIDEND_COLUMNS)].copy()
    symbols = result["symbol"].astype("string").str.strip().str.upper()
    valid_symbols = symbols.str.endswith((".SH", ".SZ", ".BJ"), na=False)
    if not valid_symbols.all():
        invalid = symbols.loc[~valid_symbols].drop_duplicates().tolist()
        raise ValueError(f"股票分红数据包含无效 symbol：{invalid[:10]}")
    result["symbol"] = symbols.astype(object)

    for column in STOCK_DIVIDEND_DATE_COLUMNS:
        source = result[column]
        blank = (
            source.astype("string")
            .str.strip()
            .eq("")
            .fillna(False)
        )
        provided = source.notna() & ~blank
        values = pd.to_datetime(source.mask(blank), errors="coerce")
        invalid = provided & values.isna()
        if invalid.any():
            raise ValueError(
                f"股票分红数据的 {column} 包含 "
                f"{int(invalid.sum())} 个无效日期"
            )
        if (
                column in STOCK_DIVIDEND_REQUIRED_DATE_COLUMNS
                and values.isna().any()
        ):
            raise ValueError(
                f"股票分红数据的 {column} 包含 "
                f"{int(values.isna().sum())} 个空日期"
            )
        result[column] = values

    for column in STOCK_DIVIDEND_VALUE_COLUMNS:
        values = pd.to_numeric(result[column], errors="coerce")
        invalid = values.isna() | ~np.isfinite(values)
        if invalid.any():
            raise ValueError(
                f"股票分红数据的 {column} 包含 "
                f"{int(invalid.sum())} 个无效数值"
            )
        result[column] = values.astype(float)

    return (
        result.sort_values(
            ["symbol", "recordDate", "exDate", "impAnnDate", "annDate"]
        )
        .drop_duplicates(
            ["symbol", "recordDate", "exDate"],
            keep="last",
        )
        .reset_index(drop=True)
    )


def append_stock_dividends(
    data: pd.DataFrame,
    *,
    session: Any | None = None,
) -> int:
    """向股票分红维度表追加规范数据并返回提交行数。"""
    result = normalize_stock_dividends(data)
    if result.empty:
        return 0

    owns_session = session is None
    current_session = create_session() if owns_session else session
    try:
        ensure_stock_dividend_table(current_session)
        current_session.upload({"coreDividendRows": result})
        inserted = current_session.run(
            f"""
            coreNormalizedDividendRows = select
                symbol(symbol) as symbol,
                date(endDate) as endDate,
                date(annDate) as annDate,
                date(recordDate) as recordDate,
                date(exDate) as exDate,
                date(payDate) as payDate,
                date(divListDate) as divListDate,
                double(bonusRatio) as bonusRatio,
                double(capitalConversion) as capitalConversion,
                double(afterTaxCashDiv) as afterTaxCashDiv,
                double(allotPrice) as allotPrice,
                double(allotRatio) as allotRatio,
                date(impAnnDate) as impAnnDate
            from coreDividendRows
            tableInsert({STOCK_DIVIDEND_TABLE}, coreNormalizedDividendRows)
            """
        )
        rows = int(inserted)
        logger.info(f"股票分红宽表写入 {rows:,} 行")
        return rows
    finally:
        if owns_session:
            current_session.close()
