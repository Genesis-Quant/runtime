"""从统一长表构造 DSL source，并在 DolphinDB 中执行派生因子。"""

from datetime import timedelta
import json
import time
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from config import DOLPHIN
from core.dolphindb.script import build_script
from core.operators import Derivative
from core.utils import logger, normalize_date_range
from .session import CORE_TABLE, IS_ST_FACTOR, WEIGHT_PREFIX, create_session


LONG_COLUMNS = ("time", "code", "factor", "value")


class FactorQuery(BaseModel):
    """统一因子查询和可选 DSL 计算参数。"""

    model_config = ConfigDict(extra="forbid")

    start_date: str = Field(
        ...,
        description="查询闭区间开始日期，格式为 YYYY-MM-DD。",
        examples=["2024-01-01"],
    )
    end_date: str = Field(
        ...,
        description="查询闭区间结束日期，格式为 YYYY-MM-DD。",
        examples=["2024-12-31"],
    )
    codes: list[str] | None = Field(
        default=None,
        description="股票代码；NULL 表示查询区间内全部股票。",
        examples=[["000001.SZ", "600000.SH"]],
    )
    factors: list[str] = Field(
        default_factory=list,
        description="需要直接输出的原始 factor。",
        examples=[["close", "is_st", "weight_000300SH"]],
    )
    derivatives: dict[str, Derivative] = Field(
        default_factory=dict,
        description="需要在 DolphinDB 中计算并输出的命名派生因子。",
    )

    @model_validator(mode="after")
    def validate_query(self) -> "FactorQuery":
        """校验日期、名称、股票代码和输出冲突。"""
        normalize_date_range(self.start_date, self.end_date)
        if self.codes is not None:
            normalized_codes = _normalize_names(self.codes, "codes")
            if not normalized_codes:
                raise ValueError("codes 不能为空")
            self.codes = normalized_codes
        self.factors = _normalize_names(self.factors, "factors")
        normalized_derivatives: dict[str, Derivative] = {}
        for name, derivative in self.derivatives.items():
            normalized = name.strip()
            if not normalized:
                raise ValueError("derivatives 不能包含空名称")
            if normalized in normalized_derivatives:
                raise ValueError(
                    f"derivatives 名称去除首尾空格后重复：{normalized!r}"
                )
            normalized_derivatives[normalized] = derivative
        self.derivatives = normalized_derivatives
        if not self.factors and not self.derivatives:
            raise ValueError("factors 和 derivatives 至少提供一项")
        derivative_names = set(self.derivatives)
        if invalid := derivative_names & {"time", "code"}:
            raise ValueError(f"派生因子不能使用保留名称：{sorted(invalid)}")
        if overlap := derivative_names & set(self.factors):
            raise ValueError(
                f"factors 与 derivatives 名称冲突：{sorted(overlap)}"
            )
        return self


def _normalize_names(values: list[str], location: str) -> list[str]:
    """清理名称列表、保持顺序去重并拒绝空值。"""
    result: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise ValueError(f"{location} 必须全部是字符串")
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{location} 不能包含空值")
        if normalized not in result:
            result.append(normalized)
    return result


def _visit_operand(value: Any, names: set[str]) -> None:
    """递归收集字段和 on 中作为列引用使用的字符串。"""
    if isinstance(value, str):
        names.add(value)
    elif isinstance(value, Derivative):
        for operand in value.fields.__dict__.values():
            _visit_operand(operand, names)
        if hasattr(value, "on"):
            _visit_operand(value.on, names)
    elif isinstance(value, (list, tuple)):
        for operand in value:
            _visit_operand(operand, names)


def derivative_factors(
    derivatives: dict[str, Derivative],
) -> set[str]:
    """返回命名派生图实际引用的原始 factor，不包含命名因子。"""
    references: set[str] = set()
    for derivative in derivatives.values():
        _visit_operand(derivative, references)
    return references - set(derivatives) - {"time", "code"}


def _empty_long() -> pd.DataFrame:
    """返回带统一列名的空长表。"""
    return pd.DataFrame(columns=LONG_COLUMNS)


def _reindex_long(value: Any) -> pd.DataFrame:
    """把 DolphinDB 空响应或表响应规范为四列 DataFrame。"""
    if value is None:
        return _empty_long()
    return value.reindex(columns=LONG_COLUMNS)


def fetch_query_parts(
    session: Any,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    codes: list[str] | None,
    factors: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """分别查询区间值、普通因子基准值和 time/code 行宇宙。"""
    uploads: dict[str, Any] = {
        "coreQueryStart": start,
        "coreQueryEnd": end + timedelta(days=1) - timedelta(milliseconds=1),
        "coreQueryAnchorFactors": np.asarray(
            [DOLPHIN.CALENDAR_FACTOR], dtype=str
        ),
    }
    code_clause = ""
    if codes is not None:
        uploads["coreQueryCodes"] = np.asarray(codes, dtype=str)
        code_clause = " and code in symbol(coreQueryCodes)"
    session.upload(uploads)

    current = _empty_long()
    baseline = _empty_long()
    if factors:
        session.upload({"coreQueryFactors": np.asarray(factors, dtype=str)})
        current = _reindex_long(
            session.run(
                f"""
select time, code, factor, value
from {CORE_TABLE}
where time >= coreQueryStart and time <= coreQueryEnd
  and factor in symbol(coreQueryFactors){code_clause}
order by code, time, factor
"""
            )
        )
        carry = [
            factor
            for factor in factors
            if factor != IS_ST_FACTOR and not factor.startswith(WEIGHT_PREFIX)
        ]
        if carry:
            session.upload({"coreQueryCarryFactors": np.asarray(carry, dtype=str)})
            baseline = _reindex_long(
                session.run(
                    f"""
select time, code, factor, value
from {CORE_TABLE}
where time < coreQueryStart
  and factor in symbol(coreQueryCarryFactors){code_clause}
context by code, factor
having time == max(time)
"""
                )
            )

    universe = session.run(
        f"""
select distinct time, code
from {CORE_TABLE}
where time >= coreQueryStart and time <= coreQueryEnd
  and factor in symbol(coreQueryAnchorFactors){code_clause}
order by code, time
"""
    )
    if universe is None:
        universe = pd.DataFrame(columns=["time", "code"])
    else:
        universe = universe.reindex(columns=["time", "code"])
    return current, baseline, universe


def build_source(
    current: pd.DataFrame,
    baseline: pd.DataFrame,
    universe: pd.DataFrame,
    factors: list[str],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """把长表和基准值整理为可直接传给 DSL 的 time/code 宽表。"""
    populated = [frame for frame in (baseline, current) if not frame.empty]
    value_rows = (
        pd.concat(populated, ignore_index=True)
        if populated
        else _empty_long()
    )
    key_frames = [universe.reindex(columns=["time", "code"])]
    if not value_rows.empty:
        key_frames.append(value_rows[["time", "code"]])
    keys = pd.concat(key_frames, ignore_index=True)
    if keys.empty:
        return pd.DataFrame(columns=["time", "code", *factors])
    keys["time"] = pd.to_datetime(keys["time"], errors="coerce")
    keys["code"] = keys["code"].astype("string")
    keys = keys.dropna().drop_duplicates()

    if value_rows.empty:
        source = keys
    else:
        value_rows = value_rows.copy()
        value_rows["time"] = pd.to_datetime(value_rows["time"], errors="coerce")
        value_rows["code"] = value_rows["code"].astype("string")
        value_rows["factor"] = value_rows["factor"].astype("string")
        value_rows["value"] = pd.to_numeric(value_rows["value"], errors="coerce")
        wide = (
            value_rows.dropna(subset=["time", "code", "factor"])
            .drop_duplicates(["time", "code", "factor"], keep="last")
            .pivot(index=["time", "code"], columns="factor", values="value")
            .reset_index()
        )
        wide.columns.name = None
        source = keys.merge(wide, how="left", on=["time", "code"])

    for factor in factors:
        if factor not in source.columns:
            source[factor] = np.nan
    source = source.sort_values(["code", "time"]).reset_index(drop=True)
    exact = [
        factor
        for factor in factors
        if factor == IS_ST_FACTOR or factor.startswith(WEIGHT_PREFIX)
    ]
    carry = [factor for factor in factors if factor not in exact]
    if exact:
        source[exact] = source[exact].fillna(0.0)
    if carry:
        source[carry] = source.groupby("code", sort=False)[carry].ffill()
    selected = source["time"].between(
        start,
        end + timedelta(days=1) - timedelta(milliseconds=1),
    )
    return (
        source.loc[selected, ["time", "code", *factors]]
        .sort_values(["code", "time"])
        .reset_index(drop=True)
    )


def query_source(
    request: FactorQuery | dict[str, Any],
    *,
    session: Any | None = None,
    required_factors: list[str] | None = None,
) -> pd.DataFrame:
    """查询并返回宽表 source；可额外指定 DSL 内部依赖 factors。"""
    started = time.perf_counter()
    query = (
        request
        if isinstance(request, FactorQuery)
        else FactorQuery.model_validate(request)
    )
    start, end = normalize_date_range(query.start_date, query.end_date)
    factors = _normalize_names(
        [*query.factors, *(required_factors or [])],
        "factors",
    )
    code_count = "全部" if query.codes is None else f"{len(query.codes):,}"
    logger.info(
        f"查询 source：{start:%Y-%m-%d} 至 {end:%Y-%m-%d}，"
        f"股票={code_count}，factor={factors}"
    )
    owns_session = session is None
    current_session = create_session() if owns_session else session
    try:
        current, baseline, universe = fetch_query_parts(
            current_session,
            start=start,
            end=end,
            codes=query.codes,
            factors=factors,
        )
        result = build_source(
            current,
            baseline,
            universe,
            factors,
            start=start,
            end=end,
        )
        elapsed = time.perf_counter() - started
        logger.success(
            f"source 查询完成，结果={result.shape}，耗时 {elapsed:.2f} 秒"
        )
        return result
    finally:
        if owns_session:
            current_session.close()


def execute_query(
    request: FactorQuery | dict[str, Any],
    *,
    session: Any | None = None,
) -> pd.DataFrame:
    """将查询宽表作为 source，在同一 DolphinDB 会话执行命名 DSL。"""
    started = time.perf_counter()
    query = (
        request
        if isinstance(request, FactorQuery)
        else FactorQuery.model_validate(request)
    )
    dependencies = sorted(derivative_factors(query.derivatives))
    logger.info(
        f"执行因子查询：原始 factor={query.factors}，"
        f"派生 factor={list(query.derivatives)}，依赖={dependencies}"
    )
    owns_session = session is None
    current_session = create_session() if owns_session else session
    try:
        source = query_source(
            query,
            session=current_session,
            required_factors=dependencies,
        )
        output_columns = ["time", "code", *query.factors, *query.derivatives]
        if source.empty:
            result = pd.DataFrame(columns=output_columns)
        elif not query.derivatives:
            result = source.loc[:, output_columns]
        else:
            definitions = {
                name: derivative.model_dump(mode="json")
                for name, derivative in query.derivatives.items()
            }
            logger.debug(
                f"加载 DolphinDB DSL 并计算 {len(definitions):,} 个派生 factor"
            )
            current_session.run(build_script())
            current_session.upload(
                {
                    "coreDslSource": source,
                    "coreDslDefinitionsJson": json.dumps(
                        definitions,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                }
            )
            computed = current_session.run(
                """
coreDslDefinitions = fromStdJson(coreDslDefinitionsJson)
compute_factors(coreDslSource, coreDslDefinitions)
"""
            )
            result = (
                computed.loc[:, output_columns]
                .sort_values(["code", "time"])
                .reset_index(drop=True)
            )
        elapsed = time.perf_counter() - started
        logger.success(
            f"因子查询完成，结果={result.shape}，耗时 {elapsed:.2f} 秒"
        )
        return result
    except Exception as error:
        logger.exception(f"因子查询失败：{error}")
        raise
    finally:
        if owns_session:
            current_session.close()


def available_factors(*, session: Any | None = None) -> list[str]:
    """返回统一长表当前实际存储的全部 factor。"""
    owns_session = session is None
    current_session = create_session() if owns_session else session
    try:
        result = current_session.run(
            f"select distinct factor from {CORE_TABLE} order by factor"
        )
        if result is None or result.empty:
            logger.debug("DolphinDB 当前没有已存储 factor")
            return []
        factors = result["factor"].astype(str).tolist()
        logger.debug(f"DolphinDB 当前存储 {len(factors):,} 个 factor")
        return factors
    finally:
        if owns_session:
            current_session.close()


__all__ = [
    "FactorQuery",
    "LONG_COLUMNS",
    "available_factors",
    "build_source",
    "derivative_factors",
    "execute_query",
    "fetch_query_parts",
    "query_source",
]
