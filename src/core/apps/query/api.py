"""在 DolphinDB 内完成统一因子查询、填充和 DSL 计算。"""

import json
import re
import time
from datetime import timedelta
from typing import Any

import numpy as np

from core.database import CORE_TABLE, create_session
from core.database.session import has_session_variable, redirect_session_output
from core.utils import CODE_COLUMN, IS_ST_FACTOR, TIME_COLUMN, WEIGHT_PREFIX, get_trading_dates, logger, normalize_date_range
from core.workers import FINANCIAL_FACTORS

from . import result, schema

REFERENCE_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


def build_query_table(
        request: schema.FactorQuery | dict[str, Any],
        *,
        session: Any,
        source_ref: str = "coreQuerySource",
        computed_ref: str = "coreQueryUnfilteredResult",
        filtered_ref: str = "coreQueryFilteredResult",
) -> tuple[schema.FactorQuery, list[str]]:
    """在会话中构造命名结果表，按变量名生成或复用基础源表。"""
    for label, reference in (
            ("computed_ref", computed_ref),
            ("filtered_ref", filtered_ref),
            ("source_ref", source_ref),
    ):
        if REFERENCE_PATTERN.fullmatch(reference) is None:
            raise ValueError(f"{label} 不是合法的 DolphinDB 变量名：{reference!r}")
    if len({computed_ref, filtered_ref, source_ref}) != 3:
        raise ValueError("computed_ref、filtered_ref 和 source_ref 不能相同")

    query = request if isinstance(request, schema.FactorQuery) else schema.FactorQuery.model_validate(request)
    output_start, output_end = normalize_date_range(query.start_date, query.end_date)
    calculation_start = (output_start - query.lookback).normalize()
    source_factors = query.source_factors()
    output_columns = [TIME_COLUMN, CODE_COLUMN, *query.factors, *query.derivatives]
    dates = get_trading_dates(calculation_start, output_end)
    definitions = {name: derivative.model_dump(mode="json") for name, derivative in query.derivatives.items()}

    session.upload(
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
    logger.info("session.run: 加载 query 模块")
    session.run("use query")
    if not has_session_variable(session, source_ref):
        logger.info(f"session.run: 查询基础因子表 {source_ref}")
        session.run(
            f"""
            {source_ref} = build_factor_source(
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
            if factor == IS_ST_FACTOR:
                logger.info(f"session.run: 填充 {source_ref}.{factor}")
                session.run(
                    f"""
                    {source_ref} = fill_null_column(
                        {source_ref},
                        {name},
                        0.0
                    )
                    """
                )
            elif factor.startswith(WEIGHT_PREFIX):
                logger.info(f"session.run: 填充并前向填充 {source_ref}.{factor}")
                session.run(
                    f"""
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
                    """
                )
            elif factor in FINANCIAL_FACTORS:
                logger.info(f"session.run: 前向填充 {source_ref}.{factor}")
                session.run(
                    f"""
                    {source_ref} = forward_fill_column(
                        {source_ref},
                        {name},
                        {source_ref}.code,
                        {source_ref}.time
                    )
                    """
                )
        logger.info(f"session.run: 整理基础因子表 {source_ref}")
        session.run(
            f"""
            {source_ref} = finalize_factor_source(
                {source_ref},
                coreQueryFactors
            )
            """
        )

    logger.info(f"session.run: 计算 {computed_ref} 并生成 {filtered_ref}")
    session.run(
        f"""
        {computed_ref} = compute_factors(
            {source_ref},
            fromStdJson(coreDslDefinitionsJson)
        )

        {filtered_ref} = filter_factors(
            {computed_ref},
            coreDslFilters
        )
        """
    )

    logger.info(f"session.run: 读取 {source_ref} 行数")
    source_rows = session.run(f"{source_ref}.rows()")
    logger.info(f"session.run: 读取 {computed_ref} 行数")
    computed_rows = session.run(f"{computed_ref}.rows()")
    if computed_rows != source_rows:
        raise RuntimeError(f"DolphinDB DSL 计算改变了行数：输入 {source_rows:,} 行，输出 {computed_rows:,} 行")
    return query, output_columns


def execute_query(request: schema.FactorQuery | dict[str, Any], *, session: Any | None = None) -> result.QueryResult:
    """在服务端生成查询结果，并把当前会话移交给惰性结果对象。"""
    started = time.perf_counter()
    owns_session = session is None
    current_session = create_session() if owns_session else session
    redirect_session_output(current_session)
    try:
        query, output_columns = build_query_table(request, session=current_session)
        logger.info("session.run: 生成查询最终结果 coreQueryResultData")
        current_session.run(
            """
            coreQueryResultData = project_factor_output(
                coreQueryFilteredResult,
                coreDslOutputColumns,
                coreOutputStart,
                coreOutputEndExclusive
            )
            """
        )
        logger.success(f"因子查询已在 DolphinDB 会话中生成，耗时 {time.perf_counter() - started:.2f} 秒")
        return result.QueryResult(session=current_session, query=query, output_columns=output_columns)
    except Exception as error:
        logger.exception(f"因子查询失败：{error}")
        if owns_session:
            current_session.close()
        raise

__all__ = ["build_query_table", "execute_query"]
