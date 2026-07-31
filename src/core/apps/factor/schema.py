"""定义因子分析查询和预处理参数。"""

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from ..query import FactorQuery


def _normalize_columns(value: Any, location: str) -> list[str]:
    """校验列名列表，清理首尾空格并保持顺序去重。"""
    if not isinstance(value, list):
        raise ValueError(f"{location} 必须是 list[str]")
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{location} 必须全部是字符串")
        column = item.strip()
        if not column:
            raise ValueError(f"{location} 不能包含空列名")
        if column in seen:
            raise ValueError(f"{location} 不能包含重复列名：{column!r}")
        result.append(column)
        seen.add(column)
    if not result:
        raise ValueError(f"{location} 至少需要一列")
    return result


class FactorAnalysisParameters(BaseModel):
    """保存一次多因子分析完成规范化后的全部参数。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        validate_default=True,
    )

    dataset_query: FactorQuery = Field(
        ...,
        description="用于生成原始因子、收益率和市值的因子 DSL。",
    )
    factor_columns: list[str] = Field(
        ...,
        description="需要评价的原始因子列或 DSL 手动预处理结果列。",
    )
    return_columns: list[str] = Field(
        ...,
        description="用于计算 IC 和分组收益的收益率列。",
    )
    n_groups: int = Field(
        default=5,
        ge=2,
        description="按每日因子值划分的等数量组数。",
    )
    preprocess: bool = Field(
        default=True,
        description=(
            "是否执行内置 MAD 去极值、标准化、市值与行业中性化及分组。"
        ),
    )
    market_value_column: str = Field(
        default="circ_mv",
        min_length=1,
        description="用于中性化和分组收益加权的市值列。",
    )
    industry_level: Literal["industry", "sector"] = Field(
        default="industry",
        description=(
            "启用内置预处理时用于中性化的 Tushare 行业层级。"
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def add_required_query_columns(cls, value: Any) -> Any:
        """把直接因子、收益率和市值列自动加入 dataset_query。"""
        if not isinstance(value, dict):
            return value
        result = dict(value)
        factor_columns = _normalize_columns(
            result.get("factor_columns"),
            "factor_columns",
        )
        return_columns = _normalize_columns(
            result.get("return_columns"),
            "return_columns",
        )
        market_value = result.get("market_value_column", "circ_mv")
        if not isinstance(market_value, str) or not market_value.strip():
            raise ValueError("market_value_column 必须是非空字符串")
        market_value = market_value.strip()
        result["factor_columns"] = factor_columns
        result["return_columns"] = return_columns
        result["market_value_column"] = market_value

        dataset_query = result.get("dataset_query")
        required = [*factor_columns, *return_columns, market_value]
        if isinstance(dataset_query, FactorQuery):
            dataset_query = dataset_query.model_dump()

        if not isinstance(dataset_query, dict):
            return result
        query = dict(dataset_query)
        factors = query.get("factors", [])
        derivatives = query.get("derivatives", {})
        if not isinstance(factors, list):
            raise ValueError("dataset_query.factors 必须是 list[str]")
        if not isinstance(derivatives, dict):
            raise ValueError("dataset_query.derivatives 必须是 JSON 对象")
        normalized_factors = {
            item.strip()
            for item in factors
            if isinstance(item, str)
        }
        normalized_derivatives = {
            name.strip()
            for name in derivatives
            if isinstance(name, str)
        }
        outputs = normalized_factors | normalized_derivatives
        query["factors"] = [
            *factors,
            *(name for name in required if name not in outputs),
        ]
        result["dataset_query"] = query
        return result

    @field_validator("factor_columns", "return_columns")
    @classmethod
    def validate_columns(
        cls,
        value: list[str],
        info: Any,
    ) -> list[str]:
        """在模型边界再次保证列名列表已经规范化。"""
        return _normalize_columns(value, info.field_name)

    @field_validator("market_value_column")
    @classmethod
    def validate_market_value_column(cls, value: str) -> str:
        """拒绝空白市值列名。"""
        normalized = value.strip()
        if not normalized:
            raise ValueError("market_value_column 不能为空")
        return normalized

    @model_validator(mode="after")
    def validate_analysis_contract(self) -> "FactorAnalysisParameters":
        """校验列角色冲突和预处理新增列冲突。"""
        factor_set = set(self.factor_columns)
        return_set = set(self.return_columns)
        if overlap := factor_set & return_set:
            raise ValueError(
                "factor_columns 与 return_columns 不能重叠："
                f"{sorted(overlap)}"
            )
        if self.market_value_column in factor_set:
            raise ValueError(
                "market_value_column 不能同时作为待分析因子"
            )

        outputs = set(self.dataset_query.factors) | set(
            self.dataset_query.derivatives
        )
        generated = {
            f"{factor}_group"
            for factor in self.factor_columns
        }
        if self.preprocess:
            if overlap := outputs & generated:
                raise ValueError(
                    "启用内置预处理时 dataset_query 不能包含分组列："
                    f"{sorted(overlap)}"
                )
            if self.industry_level in outputs:
                raise ValueError(
                    "dataset_query 不能定义由因子分析添加的行业列："
                    f"{self.industry_level!r}"
                )
        elif missing := generated - outputs:
            raise ValueError(
                "关闭内置预处理时 dataset_query 必须输出对应分组列："
                f"{sorted(missing)}"
            )
        return self


__all__ = ["FactorAnalysisParameters"]
