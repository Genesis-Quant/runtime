"""在 DolphinDB 内完成统一因子查询、填充和 DSL 计算。"""

import json
import re
import time
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd

from core.database import CORE_TABLE, create_session
from core.utils import (
    CODE_COLUMN,
    IS_ST_FACTOR,
    TIME_COLUMN,
    WEIGHT_PREFIX,
    get_trading_dates,
    logger,
    normalize_date_range,
)
from core.workers import FINANCIAL_FACTORS

from .schema import FactorQuery

REFERENCE_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


def build_query_table(
    request: FactorQuery | dict[str, Any],
    *,
    session: Any,
    computed_ref: str,
    filtered_ref: str,
    source_ref: str | None = None,
) -> tuple[FactorQuery, list[str]]:
    """在会话中构造命名结果表，并可复用已完成填充的基础源表。"""
    for label, reference in (
        ("computed_ref", computed_ref),
        ("filtered_ref", filtered_ref),
        ("source_ref", source_ref),
    ):
        if reference is None:
            continue
        if REFERENCE_PATTERN.fullmatch(reference) is None:
            raise ValueError(f"{label} 不是合法的 DolphinDB 变量名：{reference!r}")
    references = [
        reference
        for reference in (computed_ref, filtered_ref, source_ref)
        if reference is not None
    ]
    if len(references) != len(set(references)):
        raise ValueError("computed_ref、filtered_ref 和 source_ref 不能相同")

    query = (
        request
        if isinstance(request, FactorQuery)
        else FactorQuery.model_validate(request)
    )
    output_start, output_end = normalize_date_range(
        query.start_date,
        query.end_date,
    )
    calculation_start = (output_start - query.lookback).normalize()
    source_factors = query.source_factors()
    output_columns = [
        TIME_COLUMN,
        CODE_COLUMN,
        *query.factors,
        *query.derivatives,
    ]
    dates = get_trading_dates(calculation_start, output_end)
    definitions = {
        name: derivative.model_dump(mode="json")
        for name, derivative in query.derivatives.items()
    }

    session.upload(
        {
            "coreQueryStart": calculation_start,
            "coreQueryEndExclusive": output_end + timedelta(days=1),
            "coreQueryCodes": np.asarray(query.codes, dtype=str),
            "coreQueryFactors": np.asarray(source_factors, dtype=str),
            "coreQueryDates": dates.to_numpy(dtype="datetime64[ms]"),
            "coreDslDefinitionsJson": json.dumps(
                definitions,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "coreDslFilters": np.asarray(query.filters, dtype=str),
            "coreDslOutputColumns": np.asarray(output_columns, dtype=str),
            "coreOutputStart": output_start,
            "coreOutputEndExclusive": output_end + timedelta(days=1),
        }
    )
    session.run("use query")
    query_source_ref = source_ref or "coreQuerySource"
    if source_ref is None:
        session.run(
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
            if factor == IS_ST_FACTOR:
                session.run(
                    f"""
                    coreQuerySource = fill_null_column(
                        coreQuerySource,
                        {name},
                        0.0
                    )
                    """
                )
            elif factor.startswith(WEIGHT_PREFIX):
                session.run(
                    f"""
                    coreQuerySource = fill_observed_group_null_column(
                        coreQuerySource,
                        {name},
                        coreQuerySource.time,
                        0.0
                    )
                    coreQuerySource = forward_fill_column(
                        coreQuerySource,
                        {name},
                        coreQuerySource.code,
                        coreQuerySource.time
                    )
                    """
                )
            elif factor in FINANCIAL_FACTORS:
                session.run(
                    f"""
                    coreQuerySource = forward_fill_column(
                        coreQuerySource,
                        {name},
                        coreQuerySource.code,
                        coreQuerySource.time
                    )
                    """
                )
        session.run(
            """
            coreQuerySource = finalize_factor_source(
                coreQuerySource,
                coreQueryFactors
            )
            """
        )
    else:
        source_columns = set(
            np.asarray(
                session.run(f"columnNames({source_ref})")
            ).astype(str)
        )
        required_columns = {TIME_COLUMN, CODE_COLUMN, *source_factors}
        if missing := required_columns - source_columns:
            raise ValueError(
                f"复用源表 {source_ref} 缺少列：{sorted(missing)}"
            )

    session.run(
        f"""
        {computed_ref} = compute_factors(
            {query_source_ref},
            fromStdJson(coreDslDefinitionsJson)
        )

        {filtered_ref} = filter_factors(
            {computed_ref},
            coreDslFilters
        )
        """
    )

    source_rows = session.run(f"{query_source_ref}.rows()")
    computed_rows = session.run(f"{computed_ref}.rows()")
    if computed_rows != source_rows:
        raise RuntimeError(
            "DolphinDB DSL 计算改变了行数："
            f"输入 {source_rows:,} 行，输出 {computed_rows:,} 行"
        )
    return query, output_columns


def execute_query(
    request: FactorQuery | dict[str, Any],
    *,
    session: Any | None = None,
) -> pd.DataFrame:
    """在同一 DolphinDB 会话中依次完成查询、填充、DSL 计算和筛选。"""
    started = time.perf_counter()
    owns_session = session is None
    current_session = create_session() if owns_session else session
    try:
        unfiltered_data_ref = "coreQueryUnfilteredFactorData"
        filtered_data_ref = "coreQueryFilteredFactorData"
        _, output_columns = build_query_table(
            request,
            session=current_session,
            computed_ref=unfiltered_data_ref,
            filtered_ref=filtered_data_ref,
        )
        result = current_session.run(
            f"""
            project_factor_output(
                {filtered_data_ref},
                coreDslOutputColumns,
                coreOutputStart,
                coreOutputEndExclusive
            )
            """
        )

        if not isinstance(result, pd.DataFrame):
            raise TypeError(
                f"DolphinDB 查询必须返回 DataFrame，当前为 {type(result).__name__}"
            )
        if tuple(result.columns) != tuple(output_columns):
            raise ValueError(
                "DolphinDB 查询返回列不符合契约："
                f"期望 {output_columns}，实际 {list(result.columns)}"
            )
        logger.success(
            f"因子查询完成，结果 {result.shape}，"
            f"耗时 {time.perf_counter() - started:.2f} 秒"
        )
        return result.reset_index(drop=True)
    except Exception as error:
        logger.exception(f"因子查询失败：{error}")
        raise
    finally:
        if owns_session:
            current_session.close()


__all__ = ["build_query_table", "execute_query"]
