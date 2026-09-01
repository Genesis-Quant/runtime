"""在 DolphinDB 内完成统一因子查询、填充和 DSL 计算。"""

import json
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd

from runtime.database import CORE_TABLE, create_session
from runtime.database.session import has_session_variable, redirect_session_output
from runtime.utils import (
    CODE_COLUMN,
    IS_ST_FACTOR,
    TIME_COLUMN,
    WEIGHT_PREFIX,
    logger,
    normalize_date_range,
    normalize_str_list,
    validate_dolphindb_references,
)
from runtime.workers import available_factors
from runtime.workers.industry import INDUSTRY_FACTORS
from runtime.workers.stock_financial import FINANCIAL_FACTORS

from .result import QueryResult
from .schema import QUERY_RESERVED_REFERENCES, FactorQuery

SOURCE_REF = "coreQuerySourceData"
COMPUTED_REF = "coreQueryComputedData"
FILTERED_REF = "coreQueryFilteredData"
DATA_REF = "coreQueryData"
QUERY_SESSION_MAX_TIME = 5 * 60


def load_market_axis(
        session: Any,
        start: pd.Timestamp,
        end: pd.Timestamp,
        *,
        log_progress: bool = True,
) -> tuple[list[str], pd.DatetimeIndex]:
    """从业务因子表的收盘价记录读取查询股票域和真实交易日。"""
    session.upload({"coreAxisStart": start, "coreAxisEnd": end + timedelta(days=1)})
    if log_progress:
        logger.info("session.run: 从业务因子表读取股票域")
    codes = [
        str(code)
        for code in session.run(f"""
            exec distinct string(code)
            from {CORE_TABLE}
            where factor = `close,
                  time >= coreAxisStart,
                  time < coreAxisEnd
        """)
    ]
    if log_progress:
        logger.info("session.run: 从业务因子表读取交易日")
    dates = pd.DatetimeIndex(session.run(f"""
        exec distinct date(time)
        from {CORE_TABLE}
        where factor = `close,
              time >= coreAxisStart,
              time < coreAxisEnd
        order by date(time)
    """))
    if not codes or dates.empty:
        raise ValueError(
            f"业务因子表在 {start:%Y-%m-%d} 至 {end:%Y-%m-%d} 没有收盘价数据"
        )
    return codes, dates


def validate_factor_query(request: FactorQuery | dict[str, Any]) -> FactorQuery:
    """校验查询模型，同时拒绝接口声明之外的运行时类型。"""
    if isinstance(request, FactorQuery):
        return request
    if isinstance(request, dict):
        return FactorQuery.model_validate(request)
    raise TypeError("request 必须是 FactorQuery 或 dict[str, Any]")


def build_query_table(
        query: FactorQuery,
        *,
        session: Any,
        source_ref: str = SOURCE_REF,
        computed_ref: str = COMPUTED_REF,
        filtered_ref: str = FILTERED_REF,
        data_ref: str = DATA_REF,
        log_progress: bool = True,
) -> list[str]:
    validate_dolphindb_references({
        "source_ref": source_ref,
        "computed_ref": computed_ref,
        "filtered_ref": filtered_ref,
        "data_ref": data_ref,
    }, reserved=QUERY_RESERVED_REFERENCES)
    output_start, output_end = normalize_date_range(query.start_date, query.end_date)
    calculation_start = (output_start - query.lookback).normalize()
    source_factors = query.source_factors()
    if unknown := set(source_factors) - set(available_factors()):
        raise ValueError(f"查询包含 Worker 未声明的字段：{sorted(unknown)}")
    output_columns = [TIME_COLUMN, CODE_COLUMN, *query.factors, *query.derivatives]
    seed_factors = [
        factor
        for factor in source_factors
        if factor in INDUSTRY_FACTORS
    ]
    market_codes, dates = load_market_axis(
        session,
        calculation_start,
        output_end,
        log_progress=log_progress,
    )
    codes = query.codes or market_codes
    definitions = {name: derivative.model_dump(mode="json") for name, derivative in query.derivatives.items()}

    session.upload({
        "coreQueryStart": calculation_start,
        "coreQueryEnd": output_end + timedelta(days=1),
        "coreQueryCodes": np.asarray(codes, dtype=str),
        "coreQueryFactors": np.asarray(source_factors, dtype=str),
        "coreQuerySeedFactors": np.asarray(
            seed_factors,
            dtype=str,
        ),
        "coreQueryDates": dates.to_numpy(dtype="datetime64[ms]"),

        "coreDslDefinitionsJson": json.dumps(definitions, ensure_ascii=False, separators=(",", ":")),
        "coreDslFilters": np.asarray(query.filters, dtype=str),
        "coreDslOutputColumns": np.asarray(output_columns, dtype=str),

        "coreOutputStart": output_start,
        "coreOutputEnd": output_end + timedelta(days=1),
    })

    if log_progress:
        logger.info("session.run: 加载 query 模块")
    session.run("use query")

    if not has_session_variable(session, source_ref, log_progress=log_progress):
        if log_progress:
            logger.info(f"session.run: 查询基础因子表 {source_ref}")
        session.run(f"""
            {source_ref} = build_factor_source(
                {CORE_TABLE},
                coreQueryCodes,
                coreQueryFactors,
                coreQueryDates,
                coreQueryStart,
                coreQueryEnd,
                coreQuerySeedFactors
            )
        """)

        for factor in source_factors:
            name = json.dumps(factor, ensure_ascii=False)
            if factor == IS_ST_FACTOR:
                if log_progress:
                    logger.info(f"session.run: 填充 {source_ref}.{factor}")
                session.run(f"""
                    {source_ref} = fill_null_column(
                        {source_ref},
                        {name},
                        0.0
                    )
                """)
            elif factor.startswith(WEIGHT_PREFIX):
                if log_progress:
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
            elif factor in FINANCIAL_FACTORS or factor in INDUSTRY_FACTORS:
                if log_progress:
                    logger.info(f"session.run: 前向填充 {source_ref}.{factor}")
                session.run(f"""
                    {source_ref} = forward_fill_column(
                        {source_ref},
                        {name},
                        {source_ref}.code,
                        {source_ref}.time
                    )
                """)

        if log_progress:
            logger.info(f"session.run: 整理基础因子表 {source_ref}")
        session.run(f"""
            {source_ref} = finalize_factor_source(
                {source_ref},
                coreQueryFactors
            )
        """)

    if log_progress:
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

    if log_progress:
        logger.info(f"session.run: 投影 {filtered_ref} 生成 {data_ref}")
    session.run(f"""
        {data_ref} = project_factor_output(
            {filtered_ref},
            coreDslOutputColumns,
            coreOutputStart,
            coreOutputEnd
        )
    """)

    return output_columns


def execute_codes_query(
        request: FactorQuery | dict[str, Any],
        *,
        session: Any,
        source_ref: str,
        computed_ref: str,
        filtered_ref: str,
        data_ref: str,
        log_progress: bool = True,
) -> list[str]:
    """执行第一阶段查询，并返回结果中去重后的股票代码。"""
    query = validate_factor_query(request)
    build_query_table(
        query,
        session=session,
        source_ref=source_ref,
        computed_ref=computed_ref,
        filtered_ref=filtered_ref,
        data_ref=data_ref,
        log_progress=log_progress,
    )
    if log_progress:
        logger.info(f"session.run: 从 {data_ref} 提取去重股票代码")
    selected_codes = session.run(f"exec distinct {CODE_COLUMN} from {data_ref} where not isNull({CODE_COLUMN}) order by {CODE_COLUMN}")
    if not isinstance(selected_codes, np.ndarray):
        raise TypeError(f"codes_query 必须返回一维代码向量，实际为 {type(selected_codes).__name__}")
    if selected_codes.ndim != 1:
        raise ValueError(f"codes_query 必须返回一维代码向量，实际维数为 {selected_codes.ndim}")
    codes = normalize_str_list(selected_codes.astype(str).tolist(), "codes_query", reject_duplicates=True)
    if not codes:
        raise ValueError("codes_query 没有选出任何股票")
    unsupported = [code for code in codes if not code.endswith((".SH", ".SZ"))]
    if unsupported:
        raise ValueError(f"codes_query 只能返回 .SH 和 .SZ 股票代码：{unsupported[:10]}")
    if log_progress:
        logger.info(f"codes_query 选出 {len(codes):,} 只股票")
    return codes


def execute_query(
        request: FactorQuery | dict[str, Any],
        *,
        session: Any | None = None
) -> QueryResult:
    """在服务端生成查询结果，并把当前会话移交给惰性结果对象。"""
    query = validate_factor_query(request)
    owns_session = session is None
    current_session = (
        create_session(max_time=QUERY_SESSION_MAX_TIME)
        if owns_session
        else session
    )
    redirect_session_output(current_session)

    try:
        build_query_table(query, session=current_session)
        logger.success("因子查询已在 DolphinDB 会话中生成")
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
