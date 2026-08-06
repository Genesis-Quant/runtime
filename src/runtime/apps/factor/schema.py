"""定义因子分析查询和预处理参数。"""

from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from runtime.utils import normalize_str, normalize_str_list

from ..query.schema import FactorQuery


class FactorAnalysisParameters(BaseModel):
    """保存一次多因子分析完成规范化后的全部参数。"""

    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)

    codes_query: FactorQuery | None = Field(
        default=None,
        description="可选第一阶段选股 DSL；结果中的 code 去重后作为 dataset_query 的 codes。",
    )

    dataset_query: FactorQuery = Field(
        ...,
        description="第二阶段因子 DSL；保留自身 filters，以第一阶段候选代码生成动态股票池。",
    )

    factor_columns: list[str] = Field(
        ...,
        min_length=1,
        description="需要评价的原始因子列或 DSL 手动预处理结果列。",
    )

    return_columns: list[str] = Field(
        ...,
        min_length=1,
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

    @model_validator(mode="before")
    @classmethod
    def add_required_query_columns(cls, data: Any) -> Any:
        """在 FactorQuery 校验前补齐因子、收益率和市值列。"""
        if not isinstance(data, dict):
            return data
        factor_columns = normalize_str_list(data.get("factor_columns"), "factor_columns", reject_duplicates=True)
        return_columns = normalize_str_list(data.get("return_columns"), "return_columns", reject_duplicates=True)
        market_value_column = normalize_str(data.get("market_value_column", "circ_mv"), "market_value_column")
        result: dict[str, Any] = {**data, "factor_columns": factor_columns, "return_columns": return_columns, "market_value_column": market_value_column}
        dataset_query = data.get("dataset_query")
        if isinstance(dataset_query, FactorQuery):
            query_data = dataset_query.model_dump(mode="python")
        elif isinstance(dataset_query, dict):
            query_data = dataset_query
        else:
            return result
        factors = query_data.get("factors") or []
        derivatives = query_data.get("derivatives") or {}
        if not isinstance(factors, list) or not isinstance(derivatives, dict):
            return result
        required = [*factor_columns, *return_columns, market_value_column]
        outputs = {name.strip() for name in factors if isinstance(name, str)} | {
            name.strip() for name in derivatives if isinstance(name, str)
        }
        merged = list(factors)
        for name in required:
            if name not in outputs:
                merged.append(name)
                outputs.add(name)
        result["dataset_query"] = FactorQuery.model_validate({**query_data, "factors": merged})
        return result

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
        if self.market_value_column in return_set:
            raise ValueError(
                "market_value_column 不能同时作为收益率列"
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
            if "industry" in outputs:
                raise ValueError(
                    "dataset_query 不能定义由因子分析添加的行业列 'industry'"
                )
        elif missing := generated - outputs:
            raise ValueError(
                "关闭内置预处理时 dataset_query 必须输出对应分组列："
                f"{sorted(missing)}"
            )
        return self


__all__ = ["FactorAnalysisParameters"]
