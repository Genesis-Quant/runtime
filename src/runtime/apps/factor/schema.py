"""定义因子分析查询和预处理参数。"""

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from ..query.schema import FactorQuery

FactorIndustryColumn = Literal[
    "industry",
    "industry_l0",
    "industry_l1",
    "industry_l2",
    "industry_l3",
]
FACTOR_INDUSTRY_COLUMNS: tuple[FactorIndustryColumn, ...] = (
    "industry",
    "industry_l0",
    "industry_l1",
    "industry_l2",
    "industry_l3",
)


class FactorReturnSpec(BaseModel):
    """定义一个分析收益列的收益口径和观测周期。"""

    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)

    kind: Literal["simple", "log"] = Field(
        ...,
        description="收益列口径；simple 为简单收益率，log 为对数收益率。",
    )
    periods: int = Field(
        ...,
        ge=1,
        description="单个收益观测覆盖的交易期数；大于 1 时不计算重叠分组收益的复利指标。",
    )


class FactorAnalysisParameters(BaseModel):
    """保存一次多因子分析完成规范化后的全部参数。"""

    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)

    codes_query: FactorQuery | None = Field(
        default=None,
        description="可选第一阶段选股 DSL；结果中的 code 去重后作为 dataset_query 的 codes。",
    )

    dataset_query: FactorQuery = Field(
        ...,
        description=(
            "因子数据 DSL；codes_query 非空时使用第一阶段候选代码，"
            "codes_query 为空且 codes=[] 时查询全市场。"
        ),
    )

    factor_columns: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "需要评价的原始因子列或 DSL 手动预处理结果列；"
            "分析时仅保留这些列在预处理后均非 NULL 的股票行。"
        ),
    )

    return_columns: list[str] = Field(
        ...,
        min_length=1,
        description="用于计算 IC 和分组收益的收益率列。",
    )

    return_specs: dict[str, FactorReturnSpec] = Field(
        description=(
            "每个收益列的收益口径与覆盖期数；键必须与 return_columns 完全一致。"
        ),
    )

    n_groups: int = Field(
        default=5,
        ge=2,
        description="按每日因子值划分的等数量组数。",
    )

    n_select: int = Field(
        default=10,
        ge=1,
        description=(
            "每日按因子值额外选择最小和最大的 N 支股票，作为分组收益曲线的首尾端。"
        ),
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

    industry_column: FactorIndustryColumn = Field(
        default="industry",
        description=(
            "用于行业中性化的分类列；industry 为静态行业映射，"
            "industry_l0 至 industry_l3 为动态行业分类。"
        ),
    )

    @field_validator("factor_columns", "return_columns")
    @classmethod
    def validate_column_names(cls, value: list[str]) -> list[str]:
        """拒绝需要 Runtime 猜测或规范化的列名。"""
        if any(not name or name != name.strip() for name in value):
            raise ValueError("列名不能为空或包含首尾空格")
        if len(set(value)) != len(value):
            raise ValueError("列名不能重复")
        return value

    @field_validator("market_value_column")
    @classmethod
    def validate_market_value_column(cls, value: str) -> str:
        """要求调用方提交可直接执行的市值列名。"""
        if value != value.strip():
            raise ValueError("market_value_column 不能包含首尾空格")
        return value

    @model_validator(mode="after")
    def validate_analysis_contract(self) -> "FactorAnalysisParameters":
        """校验列角色冲突和预处理新增列冲突。"""
        factor_set = set(self.factor_columns)
        return_set = set(self.return_columns)
        if set(self.return_specs) != return_set:
            raise ValueError(
                "return_specs 的键必须与 return_columns 完全一致："
                f"{sorted(return_set)}"
            )
        if overlap := factor_set & return_set:
            raise ValueError(
                "factor_columns 与 return_columns 不能重叠："
                f"{sorted(overlap)}"
            )
        if self.market_value_column in factor_set:
            raise ValueError(
                "market_value_column 不能同时作为待分析因子"
            )
        if self.market_value_column in return_set:
            raise ValueError(
                "market_value_column 不能同时作为收益率列"
            )
        if self.preprocess and self.industry_column in factor_set:
            raise ValueError(
                "industry_column 不能同时作为待分析因子"
            )
        if self.preprocess and self.industry_column in return_set:
            raise ValueError(
                "industry_column 不能同时作为收益率列"
            )

        outputs = set(self.dataset_query.factors) | set(
            self.dataset_query.derivatives
        )
        required = factor_set | return_set | {self.market_value_column}
        if self.preprocess and self.industry_column != "industry":
            required.add(self.industry_column)
        if missing := required - outputs:
            raise ValueError(
                "dataset_query 缺少因子分析所需输出列："
                f"{sorted(missing)}"
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
            if self.industry_column == "industry" and "industry" in outputs:
                raise ValueError(
                    "dataset_query 不能定义由因子分析添加的行业列 'industry'"
                )
        elif missing := generated - outputs:
            raise ValueError(
                "关闭内置预处理时 dataset_query 必须输出对应分组列："
                f"{sorted(missing)}"
            )
        return self

__all__ = [
    "FACTOR_INDUSTRY_COLUMNS",
    "FactorAnalysisParameters",
    "FactorIndustryColumn",
    "FactorReturnSpec",
]
