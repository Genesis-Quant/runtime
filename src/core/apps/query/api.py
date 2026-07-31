"""在 DolphinDB 内完成统一因子查询、填充和 DSL 计算。"""

import re
import json
from typing import Any
from datetime import timedelta

import numpy as np

from core.database import CORE_TABLE, create_session
from core.database.session import has_session_variable, redirect_session_output
from core.utils import (
    CODE_COLUMN,
    logger,
    IS_ST_FACTOR,
    TIME_COLUMN,
    WEIGHT_PREFIX,
    get_trading_dates,
    normalize_date_range
)
from core.workers import FINANCIAL_FACTORS

from .result import QueryResult
from .schema import FactorQuery

REFERENCE_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]*")

SOURCE_REF = "coreQuerySourceData"
COMPUTED_REF = "coreQueryComputedData"
FILTERED_REF = "coreQueryFilteredData"
DATA_REF = "coreQueryData"


def build_query_table(
        query: FactorQuery,
        *,
        session: Any,
        source_ref: str = SOURCE_REF,
        computed_ref: str = COMPUTED_REF,
        filtered_ref: str = FILTERED_REF,
) -> list[str]:
    output_start, output_end = normalize_date_range(query.start_date, query.end_date)
    calculation_start = (output_start - query.lookback).normalize()
    source_factors = query.source_factors()
    output_columns = [TIME_COLUMN, CODE_COLUMN, *query.factors, *query.derivatives]
    dates = get_trading_dates(calculation_start, output_end)
    definitions = {name: derivative.model_dump(mode="json") for name, derivative in query.derivatives.items()}

    session.upload({
        "coreQueryStart": calculation_start,
        "coreQueryEnd": output_end + timedelta(days=1),
        "coreQueryCodes": np.asarray(query.codes, dtype=str),
        "coreQueryFactors": np.asarray(source_factors, dtype=str),
        "coreQueryDates": dates.to_numpy(dtype="datetime64[ms]"),

        "coreDslDefinitionsJson": json.dumps(definitions, ensure_ascii=False, separators=(",", ":")),
        "coreDslFilters": np.asarray(query.filters, dtype=str),
        "coreDslOutputColumns": np.asarray(output_columns, dtype=str),

        "coreOutputStart": output_start,
        "coreOutputEnd": output_end + timedelta(days=1),
    })

    logger.info("session.run: 加载 query 模块")
    session.run("use query")

    if not has_session_variable(session, source_ref):
        logger.info(f"session.run: 查询基础因子表 {source_ref}")
        session.run(f"""
            {source_ref} = build_factor_source(
                {CORE_TABLE},
                coreQueryCodes,
                coreQueryFactors,
                coreQueryDates,
                coreQueryStart,
                coreQueryEnd
            )
        """)

        for factor in source_factors:
            name = json.dumps(factor, ensure_ascii=False)
            if factor == IS_ST_FACTOR:
                logger.info(f"session.run: 填充 {source_ref}.{factor}")
                session.run(f"""
                    {source_ref} = fill_null_column(
                        {source_ref},
                        {name},
                        0.0
                    )
                """)
            elif factor.startswith(WEIGHT_PREFIX):
                logger.info(f"session.run: 填充并前向填充 {source_ref}.{factor}")
                session.run(f"""
                    {source_ref} = fill_observed_group_null_column(
                        {source_ref},
                        {name},
                        {source_ref}.time,
                        0.0
                    )
                    {source_ref} = forward_fill_column(
                        {source_ref},
                        {name},
                        {source_ref}.code,
                        {source_ref}.time
                    )
                """)
            elif factor in FINANCIAL_FACTORS:
                logger.info(f"session.run: 前向填充 {source_ref}.{factor}")
                session.run(f"""
                    {source_ref} = forward_fill_column(
                        {source_ref},
                        {name},
                        {source_ref}.code,
                        {source_ref}.time
                    )
                """)

        logger.info(f"session.run: 整理基础因子表 {source_ref}")
        session.run(f"""
            {source_ref} = finalize_factor_source(
                {source_ref},
                coreQueryFactors
            )
        """)

    logger.info(f"session.run: 计算 {computed_ref} 并生成 {filtered_ref}")
    session.run(f"""
        {computed_ref} = compute_factors(
            {source_ref},
            fromStdJson(coreDslDefinitionsJson)
        )

        {filtered_ref} = filter_factors(
            {computed_ref},
            coreDslFilters
        )
    """)

    return output_columns


def execute_query(
        request: FactorQuery | dict[str, Any],
        *,
        session: Any | None = None
) -> QueryResult:
    """在服务端生成查询结果，并把当前会话移交给惰性结果对象。"""
    owns_session = session is None
    current_session = create_session() if owns_session else session
    redirect_session_output(current_session)

    try:
        build_query_table(request, session=current_session)
        logger.info(f"session.run: 生成查询最终结果 {DATA_REF}")
        current_session.run(f"""
            {DATA_REF} = project_factor_output(
                {FILTERED_REF},
                coreDslOutputColumns,
                coreOutputStart,
                coreOutputEnd
            )
        """)

        logger.success(f"因子查询已在 DolphinDB 会话中生成")
        return QueryResult(
            session=current_session,
            source_ref=SOURCE_REF,
            computed_ref=COMPUTED_REF,
            filtered_ref=FILTERED_REF,
            data_ref=DATA_REF,
        )
    except Exception as error:
        logger.exception(f"因子查询失败：{error}")
        if owns_session:
            current_session.close()
        raise


__all__ = ["build_query_table", "execute_query"]
