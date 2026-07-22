"""定义统一因子查询请求及其依赖解析。"""

from datetime import timedelta
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)

from core.query.operator import Derivative
from core.utils import CODES, normalize_date_range

RESERVED_NAMES = frozenset(("time", "code"))


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
        description="计算前额外加载的历史时长；结果仍从 start_date 开始返回。",
        examples=["30D", "P30D"],
    )
    codes: list[str] = Field(
        ...,
        description="需要查询的股票代码；空列表表示全市场。",
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
        description="仅返回所有过滤列均为 true 的行。",
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
                raise ValueError(
                    f"lookback 不是有效 TimeDelta：{value!r}"
                ) from error
        else:
            raise ValueError("lookback 必须是 timedelta 或 TimeDelta 字符串")
        if result < timedelta(0):
            raise ValueError("lookback 不能小于 0")
        return result

    @model_validator(mode="after")
    def validate_query(self) -> "FactorQuery":
        """规范名称并校验日期、输出列和派生列冲突。"""
        normalize_date_range(self.start_date, self.end_date)
        self.codes = normalize_names(self.codes, "codes") or list(CODES)
        self.factors = normalize_names(self.factors, "factors")
        self.filters = normalize_names(self.filters, "filters")

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

    def source_factors(self) -> list[str]:
        """返回原始输出列、派生依赖和过滤依赖的有序并集。"""
        references: set[str] = set()

        def visit(value: Any) -> None:
            """递归收集 fields 和 on 中作为列引用使用的字符串。"""
            if isinstance(value, str):
                references.add(value)
            elif isinstance(value, Derivative):
                for field_name in type(value.fields).model_fields:
                    visit(getattr(value.fields, field_name))
                on = getattr(value, "on", None)
                if on is not None:
                    visit(on)
            elif isinstance(value, (list, tuple)):
                for operand in value:
                    visit(operand)

        for derivative in self.derivatives.values():
            visit(derivative)
        references -= set(self.derivatives) | RESERVED_NAMES
        references.update(
            set(self.filters) - set(self.derivatives) - RESERVED_NAMES
        )
        return normalize_names(
            [*self.factors, *sorted(references - set(self.factors))],
            "factors",
        )


__all__ = ["FactorQuery", "normalize_names"]
