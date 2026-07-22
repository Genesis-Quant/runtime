"""从统一因子长表构造日频 source，并在 DolphinDB 中执行 DSL。"""

import json
import time
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)

from core.query.dolphindb.script import build_script
from core.query.operator import Derivative
from core.utils import (
    CODE_COLUMN,
    CODES,
    CORE_COLUMNS,
    FACTOR_COLUMN,
    IS_ST_FACTOR,
    TIME_COLUMN,
    VALUE_COLUMN,
    WEIGHT_PREFIX,
    get_trading_dates,
    logger,
    normalize_date_range,
)

from core.database.session import (
    CORE_TABLE,
    create_session,
)

# 保留原名称供现有调用方使用，实际列契约统一由 utils.schema 定义。
LONG_COLUMNS = CORE_COLUMNS
KEY_COLUMNS = (TIME_COLUMN, CODE_COLUMN)
RESERVED_NAMES = frozenset(KEY_COLUMNS)


class FactorQuery(BaseModel):
    """统一因子查询和可选 DSL 计算参数。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    start_date: str = Field(
        ...,
        description="查询闭区间开始日期，格式为 YYYY-MM-DD。",
        examples=["2025-01-01"],
    )
    end_date: str = Field(
        ...,
        description="查询闭区间结束日期，格式为 YYYY-MM-DD。",
        examples=["2025-12-31"],
    )
    lookback: timedelta = Field(
        default=timedelta(0),
        ge=timedelta(0),
        description=(
            "计算前额外加载的历史时长；结果仍从 start_date 开始返回。"
        ),
        examples=["30D", "P30D"],
    )
    codes: list[str] = Field(
        ...,
        description="需要查询的股票代码；必须显式提供，空列表表示全市场。",
        examples=[["000001.SZ", "600000.SH"]],
    )
    factors: list[str] = Field(
        default_factory=list,
        description="需要直接输出的数据库 factor。",
        examples=[["close", "is_st", "weight_000300SH"]],
    )
    derivatives: dict[str, Derivative] = Field(
        default_factory=dict,
        description="需要在 DolphinDB 中计算并输出的命名派生因子。",
    )
    filters: list[str] = Field(
        default_factory=list,
        description=(
            "DSL 计算完成后的布尔过滤列；仅返回所有过滤列均为 true 的行。"
        ),
    )

    @field_validator("lookback", mode="before")
    @classmethod
    def parse_lookback(cls, value: Any) -> timedelta:
        """接受 timedelta 或 Pydantic TimeDelta 字符串。"""
        if isinstance(value, timedelta):
            result = value
        elif isinstance(value, str):
            try:
                result = TypeAdapter(timedelta).validate_python(value)
            except ValueError as error:
                raise ValueError(f"lookback 不是有效 TimeDelta：{value!r}") from error
        else:
            raise ValueError("lookback 必须是 timedelta 或 TimeDelta 字符串")
        if result < timedelta(0):
            raise ValueError("lookback 不能小于 0")
        return result

    @model_validator(mode="after")
    def validate_query(self) -> "FactorQuery":
        """规范名称并校验日期、输出列和派生列冲突。"""
        normalize_date_range(self.start_date, self.end_date)

        self.codes = normalize_names(self.codes, "codes")
        if not self.codes:
            self.codes = list(CODES)

        self.factors = normalize_names(self.factors, "factors")
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
        self.filters = normalize_names(self.filters, "filters")

        if not self.factors and not self.derivatives:
            raise ValueError("factors 和 derivatives 至少提供一项")
        if invalid := set(self.factors) & RESERVED_NAMES:
            raise ValueError(f"factors 不能使用保留名称：{sorted(invalid)}")
        if invalid := set(self.derivatives) & RESERVED_NAMES:
            raise ValueError(
                f"derivatives 不能使用保留名称：{sorted(invalid)}"
            )
        if overlap := set(self.factors) & set(self.derivatives):
            raise ValueError(
                f"factors 与 derivatives 名称冲突：{sorted(overlap)}"
            )
        return self


def normalize_names(values: list[str], location: str) -> list[str]:
    """清理字符串列表，在保持顺序的同时去重并拒绝空值。"""
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            raise ValueError(f"{location} 必须全部是字符串")
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{location} 不能包含空值")
        if normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result


def visit_operand(value: Any, names: set[str]) -> None:
    """递归收集 fields 和 on 中作为列引用使用的字符串。"""
    if isinstance(value, str):
        names.add(value)
        return
    if isinstance(value, Derivative):
        for field_name in type(value.fields).model_fields:
            visit_operand(getattr(value.fields, field_name), names)
        on = getattr(value, "on", None)
        if on is not None:
            visit_operand(on, names)
        return
    if isinstance(value, (list, tuple)):
        for operand in value:
            visit_operand(operand, names)


def derivative_factors(
    derivatives: dict[str, Derivative],
) -> set[str]:
    """返回命名派生图引用的原始 factor，不包含命名中间结果。"""
    references: set[str] = set()
    for derivative in derivatives.values():
        visit_operand(derivative, references)
    return references - set(derivatives) - RESERVED_NAMES


def empty_long() -> pd.DataFrame:
    """返回符合统一长表 dtype 约定的空 DataFrame。"""
    return pd.DataFrame(
        {
            TIME_COLUMN: pd.Series(dtype="datetime64[ns]"),
            CODE_COLUMN: pd.Series(dtype="object"),
            FACTOR_COLUMN: pd.Series(dtype="object"),
            VALUE_COLUMN: pd.Series(dtype="float64"),
        }
    )


def empty_source(factors: list[str]) -> pd.DataFrame:
    """返回带 time、code 和指定 factor 的空日频宽表。"""
    columns: dict[str, pd.Series] = {
        TIME_COLUMN: pd.Series(dtype="datetime64[ns]"),
        CODE_COLUMN: pd.Series(dtype="object"),
    }
    columns.update(
        (factor, pd.Series(dtype="float64"))
        for factor in factors
    )
    return pd.DataFrame(columns)


def select_columns(
    value: Any,
    columns: tuple[str, ...],
    context: str,
) -> pd.DataFrame:
    """校验 DolphinDB 表响应严格符合列契约。"""
    if not isinstance(value, pd.DataFrame):
        raise TypeError(
            f"DolphinDB {context} 必须返回 DataFrame，"
            f"当前为 {type(value).__name__}"
        )
    actual_columns = tuple(value.columns)
    if actual_columns != columns:
        raise ValueError(
            f"DolphinDB {context} 返回列不符合契约："
            f"期望 {list(columns)}，实际 {list(actual_columns)}"
        )
    return value


def zero_fill_factor(factor: str) -> bool:
    """判断 factor 的缺失值是否表示当日状态为 0。"""
    return factor == IS_ST_FACTOR or factor.startswith(WEIGHT_PREFIX)


def forward_fill_factor(factor: str) -> bool:
    """判断 factor 是否为应按公告时间向后生效的财报字段。"""
    from core.workers.stock_financial import FINANCIAL_FACTORS

    return factor in FINANCIAL_FACTORS


def check_long(data: pd.DataFrame, context: str) -> pd.DataFrame:
    """校验统一长表的结构和 dtype，不重复转换、清洗或去重。"""
    result = select_columns(data, CORE_COLUMNS, context)
    if not pd.api.types.is_datetime64_any_dtype(result[TIME_COLUMN]):
        raise ValueError(
            f"{context} 的 {TIME_COLUMN} 列必须为 datetime64 类型"
        )
    if not pd.api.types.is_float_dtype(result[VALUE_COLUMN]):
        raise ValueError(f"{context} 的 {VALUE_COLUMN} 列必须为 float 类型")
    return result


def check_universe(data: pd.DataFrame) -> pd.DataFrame:
    """校验完整交易日日历的结构和 time dtype。"""
    result = select_columns(data, KEY_COLUMNS, "股票交易日日历")
    if not pd.api.types.is_datetime64_any_dtype(result[TIME_COLUMN]):
        raise ValueError(
            f"股票交易日日历的 {TIME_COLUMN} 列必须为 datetime64 类型"
        )
    return result


def build_source(
    data: pd.DataFrame,
    universe: pd.DataFrame,
    factors: list[str],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """按完整交易日日历和各字段填充规则构造日频 DSL 宽表。

    区间内的稀疏事件日期会加入内部填充时间线，使周末财报能在下一交易日
    生效。财报字段按股票前填，ST 和指数权重补零，价格、每日指标及未知
    字段不填充；完成填充后仅保留交易日行。
    """
    start, end = normalize_date_range(start, end)
    factors = normalize_names(factors, "factors")
    universe_rows = check_universe(universe)
    if universe_rows.empty:
        return empty_source(factors)

    values = check_long(data, "区间因子数据")
    if not values.empty:
        universe_codes = set(universe_rows[CODE_COLUMN])
        values = values[
            values[CODE_COLUMN].isin(universe_codes)
            & values[FACTOR_COLUMN].isin(factors)
        ]

    # 事件行只负责推进前值，只有行情锚点行会进入最终结果。
    selected_keys = universe_rows.copy()
    selected_keys["selected"] = True
    if values.empty:
        source = selected_keys
    else:
        event_keys = values.loc[:, list(KEY_COLUMNS)].copy()
        event_keys["selected"] = False
        timeline = (
            pd.concat([selected_keys, event_keys], ignore_index=True)
            .drop_duplicates(list(KEY_COLUMNS), keep="first")
        )
        wide = (
            values.pivot(
                index=list(KEY_COLUMNS),
                columns=FACTOR_COLUMN,
                values=VALUE_COLUMN,
            )
            .reset_index()
        )
        wide.columns.name = None
        source = timeline.merge(wide, how="left", on=list(KEY_COLUMNS))

    for factor in factors:
        if factor not in source.columns:
            source[factor] = np.nan
    source = source.sort_values([CODE_COLUMN, TIME_COLUMN]).reset_index(drop=True)

    zero_factors = [factor for factor in factors if zero_fill_factor(factor)]
    forward_factors = [
        factor for factor in factors if forward_fill_factor(factor)
    ]
    if zero_factors:
        source[zero_factors] = source[zero_factors].fillna(0.0)
    if forward_factors:
        source[forward_factors] = (
            source.groupby(CODE_COLUMN, sort=False)[forward_factors].ffill()
        )

    end_exclusive = end + timedelta(days=1)
    selected = source["selected"] & source[TIME_COLUMN].ge(start)
    selected &= source[TIME_COLUMN].lt(end_exclusive)
    return (
        source.loc[selected, [*KEY_COLUMNS, *factors]]
        .sort_values([CODE_COLUMN, TIME_COLUMN])
        .reset_index(drop=True)
    )


def query_source(
    request: FactorQuery | dict[str, Any],
    *,
    session: Any | None = None,
    required_factors: list[str] | None = None,
) -> pd.DataFrame:
    """查询原始 factor 和 DSL 依赖，返回可直接上传的日频宽表。"""
    started = time.perf_counter()
    query = (
        request
        if isinstance(request, FactorQuery)
        else FactorQuery.model_validate(request)
    )
    output_start, end = normalize_date_range(
        query.start_date,
        query.end_date,
    )
    calculation_start = (output_start - query.lookback).normalize()
    factors = normalize_names(
        [*query.factors, *(required_factors or [])],
        "factors",
    )
    if invalid := set(factors) & RESERVED_NAMES:
        raise ValueError(f"required_factors 不能使用保留名称：{sorted(invalid)}")

    logger.info(
        f"查询 source：计算区间={calculation_start:%Y-%m-%d} 至 "
        f"{end:%Y-%m-%d}，输出起点={output_start:%Y-%m-%d}，"
        f"股票={len(query.codes):,}，factor={factors}"
    )
    owns_session = session is None
    trading_dates = get_trading_dates(calculation_start, end)
    if trading_dates.empty:
        result = empty_source(factors)
        logger.success(
            f"source 查询完成，结果={result.shape}，"
            f"耗时 {time.perf_counter() - started:.2f} 秒"
        )
        return result

    current_session = create_session() if owns_session else session
    try:
        end_exclusive = end + timedelta(days=1)
        current_session.upload(
            {
                "coreQueryStart": calculation_start,
                "coreQueryEndExclusive": end_exclusive,
                "coreQueryCodes": np.asarray(query.codes, dtype=str),
            }
        )

        universe = pd.MultiIndex.from_product(
            [query.codes, trading_dates],
            names=[CODE_COLUMN, TIME_COLUMN],
        ).to_frame(index=False)[[TIME_COLUMN, CODE_COLUMN]]

        current = empty_long()
        if factors:
            current_session.upload(
                {"coreQueryFactors": np.asarray(factors, dtype=str)}
            )
            current = select_columns(
                current_session.run(
                    f"""
                    select {TIME_COLUMN}, {CODE_COLUMN}, {FACTOR_COLUMN}, {VALUE_COLUMN}
                    from {CORE_TABLE}
                    where {TIME_COLUMN} >= coreQueryStart
                      and {TIME_COLUMN} < coreQueryEndExclusive
                      and {FACTOR_COLUMN} in symbol(coreQueryFactors)
                      and {CODE_COLUMN} in symbol(coreQueryCodes)
                    """
                ),
                CORE_COLUMNS,
                "区间因子查询",
            )

        result = build_source(
            current,
            universe,
            factors,
            start=calculation_start,
            end=end,
        )
        logger.success(
            f"source 查询完成，结果={result.shape}，"
            f"耗时 {time.perf_counter() - started:.2f} 秒"
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
    """查询日频 source，在同一会话计算 DSL，并返回请求的输出列。"""
    started = time.perf_counter()
    query = (
        request
        if isinstance(request, FactorQuery)
        else FactorQuery.model_validate(request)
    )
    output_start, output_end = normalize_date_range(
        query.start_date,
        query.end_date,
    )
    dependency_names = derivative_factors(query.derivatives)
    dependency_names.update(
        set(query.filters) - set(query.derivatives) - RESERVED_NAMES
    )
    dependencies = sorted(dependency_names)
    logger.info(
        f"执行因子查询：原始 factor={query.factors}，"
        f"派生 factor={list(query.derivatives)}，filters={query.filters}，"
        f"依赖={dependencies}"
    )

    owns_session = session is None
    current_session = create_session() if owns_session else session
    try:
        source = query_source(
            query,
            session=current_session,
            required_factors=dependencies,
        )
        output_columns = [
            TIME_COLUMN,
            CODE_COLUMN,
            *query.factors,
            *query.derivatives,
        ]
        if not query.derivatives and not query.filters:
            computed = source
        else:
            definitions = {
                name: derivative.model_dump(mode="json")
                for name, derivative in query.derivatives.items()
            }
            logger.debug(
                f"加载 DolphinDB DSL，计算 {len(definitions):,} 个派生 factor，"
                f"应用 {len(query.filters):,} 个 filter"
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
                    "coreDslFilters": np.asarray(query.filters, dtype=str),
                }
            )
            computed_rows, computed = current_session.run(
                """
                coreDslDefinitions = fromStdJson(coreDslDefinitionsJson)
                coreDslComputed = compute_factors(coreDslSource, coreDslDefinitions)
                coreDslFiltered = filter_factors(coreDslComputed, coreDslFilters)
                (coreDslComputed.rows(), coreDslFiltered)
                """
            )
            if not isinstance(computed, pd.DataFrame):
                raise TypeError(
                    "DolphinDB DSL 计算必须返回 DataFrame，"
                    f"当前为 {type(computed).__name__}"
                )
            if computed_rows != len(source):
                raise RuntimeError(
                    "DolphinDB DSL 计算改变了行数："
                    f"输入 {len(source):,} 行，输出 {computed_rows:,} 行"
                )
        required_columns = set(output_columns) | set(query.filters)
        if missing := required_columns - set(computed.columns):
            raise RuntimeError(
                f"DolphinDB DSL 结果缺少输出列或过滤列：{sorted(missing)}"
            )

        output_rows = computed[TIME_COLUMN].ge(output_start)
        output_rows &= computed[TIME_COLUMN].lt(
            output_end + timedelta(days=1)
        )
        result = (
            computed.loc[output_rows, output_columns]
            .sort_values([CODE_COLUMN, TIME_COLUMN])
            .reset_index(drop=True)
        )
        logger.success(
            f"因子查询完成，结果={result.shape}，"
            f"耗时 {time.perf_counter() - started:.2f} 秒"
        )
        return result
    except Exception as error:
        logger.exception(f"因子查询失败：{error}")
        raise
    finally:
        if owns_session:
            current_session.close()


def available_factors(*, session: Any | None = None) -> list[str]:
    """返回统一长表中当前至少存储过一行数据的全部 factor。"""
    owns_session = session is None
    current_session = create_session() if owns_session else session
    try:
        result = current_session.run(
            f"select distinct {FACTOR_COLUMN} from {CORE_TABLE} "
            f"order by {FACTOR_COLUMN}"
        )
        if not isinstance(result, pd.DataFrame):
            raise TypeError(
                "DolphinDB factor 元数据查询必须返回 DataFrame，"
                f"当前为 {type(result).__name__}"
            )
        if tuple(result.columns) != (FACTOR_COLUMN,):
            raise ValueError(
                "DolphinDB factor 元数据查询返回列不符合契约："
                f"期望 {[FACTOR_COLUMN]}，实际 {list(result.columns)}"
            )

        factors = result[FACTOR_COLUMN].tolist()
        if any(
            not isinstance(factor, str)
            or not factor
            or factor != factor.strip()
            for factor in factors
        ):
            raise ValueError("DolphinDB factor 元数据包含无效 factor")
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
    "query_source",
]
