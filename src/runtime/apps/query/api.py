"""在 DolphinDB 内完成统一因子查询、填充和 DSL 计算。"""

import json
import threading
from datetime import date, timedelta
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
    DateLike,
    RateLimiter,
    Retry,
    get_codes,
    get_pro,
    logger,
    normalize_date_range,
    normalize_str_list,
    validate_dolphindb_references,
)
from runtime.workers import available_factors
from runtime.workers.stock_financial import FINANCIAL_FACTORS

from .result import QueryResult
from .schema import QUERY_RESERVED_REFERENCES, FactorQuery

SOURCE_REF = "coreQuerySourceData"
COMPUTED_REF = "coreQueryComputedData"
FILTERED_REF = "coreQueryFilteredData"
DATA_REF = "coreQueryData"

trading_calendar_cache = pd.DatetimeIndex([])
trading_calendar_cache_start: pd.Timestamp | None = None
trading_calendar_cache_end: pd.Timestamp | None = None
trading_calendar_cache_date: date | None = None
trading_calendar_lock = threading.Lock()
trading_calendar_retry = Retry(
    max_retries=5,
    retry_interval=2,
    limiter=RateLimiter(0),
)


def get_trading_dates(
        start_date: DateLike,
        end_date: DateLike,
) -> pd.DatetimeIndex:
    """返回查询区间内的上交所开放日，同一天复用缓存。"""
    global trading_calendar_cache
    global trading_calendar_cache_start
    global trading_calendar_cache_end
    global trading_calendar_cache_date

    start, end = normalize_date_range(start_date, end_date)
    current_date = date.today()

    with trading_calendar_lock:
        cache_current = trading_calendar_cache_date == current_date
        cache_covers_range = (
            cache_current
            and trading_calendar_cache_start is not None
            and trading_calendar_cache_end is not None
            and trading_calendar_cache_start <= start
            and trading_calendar_cache_end >= end
        )
        if not cache_covers_range:
            request_start = (
                min(start, trading_calendar_cache_start)
                if cache_current and trading_calendar_cache_start is not None
                else start
            )
            request_end = (
                max(end, trading_calendar_cache_end)
                if cache_current and trading_calendar_cache_end is not None
                else end
            )

            def request_calendar() -> pd.DatetimeIndex:
                response = get_pro().trade_cal(
                    exchange="SSE",
                    start_date=request_start.strftime("%Y%m%d"),
                    end_date=request_end.strftime("%Y%m%d"),
                    fields="cal_date,is_open",
                )
                if response is None:
                    raise RuntimeError("trade_cal 返回 None")
                if not isinstance(response, pd.DataFrame):
                    raise TypeError("trade_cal 返回值必须是 DataFrame")
                if response.empty:
                    raise ValueError("trade_cal 返回空数据")
                required = {"cal_date", "is_open"}
                if missing := required - set(response.columns):
                    raise ValueError(f"trade_cal 返回结果缺少列：{sorted(missing)}")
                is_open = pd.to_numeric(response["is_open"], errors="coerce")
                if is_open.isna().any():
                    raise ValueError("trade_cal 返回了无效 is_open")
                dates = pd.to_datetime(
                    response.loc[is_open.eq(1), "cal_date"],
                    format="%Y%m%d",
                    errors="coerce",
                )
                if dates.isna().any():
                    raise ValueError("trade_cal 返回了无效 cal_date")
                return pd.DatetimeIndex(dates.drop_duplicates().sort_values())

            trading_calendar_cache = trading_calendar_retry(
                request_calendar,
                context=f"trade_cal[{request_start:%Y-%m-%d}~{request_end:%Y-%m-%d}]",
            )
            trading_calendar_cache_start = request_start
            trading_calendar_cache_end = request_end
            trading_calendar_cache_date = current_date

        selected = trading_calendar_cache[
            (trading_calendar_cache >= start)
            & (trading_calendar_cache <= end)
        ]
        return selected.copy()


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
    codes = query.codes or list(get_codes())
    output_columns = [TIME_COLUMN, CODE_COLUMN, *query.factors, *query.derivatives]
    dates = get_trading_dates(calculation_start, output_end)
    definitions = {name: derivative.model_dump(mode="json") for name, derivative in query.derivatives.items()}

    session.upload({
        "coreQueryStart": calculation_start,
        "coreQueryEnd": output_end + timedelta(days=1),
        "coreQueryCodes": np.asarray(codes, dtype=str),
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
) -> list[str]:
    """执行第一阶段查询，并返回结果中去重后的股票代码。"""
    query = validate_factor_query(request)
    build_query_table(query, session=session, source_ref=source_ref, computed_ref=computed_ref, filtered_ref=filtered_ref, data_ref=data_ref)
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
    current_session = create_session() if owns_session else session
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
