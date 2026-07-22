"""在 DolphinDB 内完成统一因子查询、填充和 DSL 计算。"""

import json
import time
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd

from core.database.session import CORE_TABLE, create_session
from core.query.dolphindb.script import build_script
from core.query.schema import FactorQuery
from core.utils import (
    CODE_COLUMN,
    IS_ST_FACTOR,
    TIME_COLUMN,
    WEIGHT_PREFIX,
    get_trading_dates,
    logger,
    normalize_date_range,
)
from core.workers.stock_financial import FINANCIAL_FACTORS


def execute_query(
        request: FactorQuery | dict[str, Any],
        *,
        session: Any | None = None,
) -> pd.DataFrame:
    """在同一 DolphinDB 会话中依次完成查询、填充、DSL 计算和筛选。"""
    started = time.perf_counter()
    query = (
        request
        if isinstance(request, FactorQuery)
        else FactorQuery.model_validate(request)
    )
    output_start, output_end = normalize_date_range(query.start_date, query.end_date)
    calculation_start = (output_start - query.lookback).normalize()
    source_factors = query.source_factors()
    output_columns = [TIME_COLUMN, CODE_COLUMN, *query.factors, *query.derivatives]
    dates = get_trading_dates(calculation_start, output_end)
    definitions = {
        name: derivative.model_dump(mode="json")
        for name, derivative in query.derivatives.items()
    }

    owns_session = session is None
    current_session = create_session() if owns_session else session
    try:
        current_session.upload(
            {
                "coreQueryStart": calculation_start,
                "coreQueryEndExclusive": output_end + timedelta(days=1),
                "coreQueryCodes": np.asarray(query.codes, dtype=str),
                "coreQueryFactors": np.asarray(source_factors, dtype=str),
                "coreQueryDates": dates.to_numpy(dtype="datetime64[ms]"),
                "coreDslDefinitionsJson": json.dumps(definitions, ensure_ascii=False, separators=(",", ":")),
                "coreDslFilters": np.asarray(query.filters, dtype=str),
                "coreDslOutputColumns": np.asarray(output_columns, dtype=str),
                "coreOutputStart": output_start,
                "coreOutputEndExclusive": output_end + timedelta(days=1),
            }
        )
        current_session.run(build_script())
        current_session.run(
            f"""
            coreQuerySource = build_factor_source(
                {CORE_TABLE},
                coreQueryCodes,
                coreQueryFactors,
                coreQueryDates,
                coreQueryStart,
                coreQueryEndExclusive
            )
            """
        )
        for factor in source_factors:
            name = json.dumps(factor, ensure_ascii=False)
            if factor == IS_ST_FACTOR or factor.startswith(WEIGHT_PREFIX):
                current_session.run(
                    f"""
                    coreQuerySource = fill_null_column(
                        coreQuerySource,
                        {name},
                        0.0
                    )
                    """
                )

            elif factor in FINANCIAL_FACTORS:
                current_session.run(
                    f"""
                    coreQuerySource = forward_fill_column(
                        coreQuerySource,
                        {name},
                        coreQuerySource.code,
                        coreQuerySource.time
                    )
                    """
                )

        current_session.run(
            """
            coreQuerySource = finalize_factor_source(
                coreQuerySource,
                coreQueryFactors
            )

            coreDslComputed = compute_factors(
                coreQuerySource,
                fromStdJson(coreDslDefinitionsJson)
            )

            coreDslFiltered = filter_factors(
                coreDslComputed,
                coreDslFilters
            )

            coreDslOutput = project_factor_output(
                coreDslFiltered,
                coreDslOutputColumns,
                coreOutputStart,
                coreOutputEndExclusive
            )
            """
        )

        source_rows = current_session.run("coreQuerySource.rows()")
        computed_rows = current_session.run("coreDslComputed.rows()")
        result = current_session.run("coreDslOutput")

        if computed_rows != source_rows:
            raise RuntimeError(
                "DolphinDB DSL 计算改变了行数："
                f"输入 {source_rows:,} 行，输出 {computed_rows:,} 行"
            )
        if not isinstance(result, pd.DataFrame):
            raise TypeError(
                "DolphinDB 查询必须返回 DataFrame，"
                f"当前为 {type(result).__name__}"
            )
        if tuple(result.columns) != tuple(output_columns):
            raise ValueError(
                "DolphinDB 查询返回列不符合契约："
                f"期望 {output_columns}，实际 {list(result.columns)}"
            )
        logger.success(
            f"因子查询完成，结果={result.shape}，"
            f"耗时 {time.perf_counter() - started:.2f} 秒"
        )
        return result.reset_index(drop=True)
    except Exception as error:
        logger.exception(f"因子查询失败：{error}")
        raise
    finally:
        if owns_session:
            current_session.close()


__all__ = ["execute_query"]
