"""定义因子分析查询和预处理参数。"""

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from ..query import FactorQuery


class FactorAnalysisParameters(BaseModel):
    """保存一次多因子分析完成规范化后的全部参数。"""

    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)

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
        description="是否执行内置 MAD 去极值、标准化、市值与行业中性化及分组。"
    )

    market_value_column: str = Field(
        default="circ_mv",
        min_length=1,
        description="用于中性化和分组收益加权的市值列。",
    )

    industry_level: Literal["industry", "sector"] = Field(
        default="industry",
        description="启用内置预处理时用于中性化的 Tushare 行业层级。"
    )

    @model_validator(mode="after")
    def add_required_query_columns(self) -> "FactorAnalysisParameters":
        """把直接因子、收益率和市值列自动加入 dataset_query。"""
        required = [*self.factor_columns, *self.return_columns, self.market_value_column]
        outputs = set(self.dataset_query.factors) | set(self.dataset_query.derivatives)
        missing = [name for name in required if name not in outputs]
        if missing:
            self.dataset_query = self.dataset_query.model_copy(
                update={"factors": [*self.dataset_query.factors, *missing]}
            )
        return self

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
