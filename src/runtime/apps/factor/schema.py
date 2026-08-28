"""定义因子分析查询和预处理参数。"""

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from runtime.utils import normalize_str, normalize_str_list

from ..query.schema import FactorQuery


class FactorReturnSpec(BaseModel):
    """定义一个分析收益列的收益口径和观测周期。"""

    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)

    kind: Literal["simple", "log"] = Field(
        default="simple",
        description="收益列口径；simple 为简单收益率，log 为对数收益率。",
    )
    periods: int = Field(
        default=1,
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
        description="需要评价的原始因子列或 DSL 手动预处理结果列。",
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

    @model_validator(mode="before")
    @classmethod
    def add_required_query_columns(cls, data: Any) -> Any:
        """在 FactorQuery 校验前补齐因子、收益率和市值列。"""
        if not isinstance(data, dict):
            return data
        factor_columns = normalize_str_list(data.get("factor_columns"), "factor_columns", reject_duplicates=True)
        return_columns = normalize_str_list(data.get("return_columns"), "return_columns", reject_duplicates=True)
        market_value_column = normalize_str(data.get("market_value_column", "circ_mv"), "market_value_column")
        result: dict[str, Any] = {
            **data,
            "factor_columns": factor_columns,
            "return_columns": return_columns,
            "market_value_column": market_value_column,
        }
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


def validate_historical_factor_analysis_parameters(
    data: Any,
) -> FactorAnalysisParameters:
    """校验已持久化参数，并仅为旧记录补充可精确推断的收益口径。"""
    if isinstance(data, FactorAnalysisParameters):
        return data
    if not isinstance(data, dict) or "return_specs" in data:
        return FactorAnalysisParameters.model_validate(data)

    return_columns = normalize_str_list(
        data.get("return_columns"),
        "return_columns",
        reject_duplicates=True,
    )
    return FactorAnalysisParameters.model_validate({
        **data,
        "return_specs": infer_historical_return_specs(
            data.get("dataset_query"),
            return_columns,
        ),
    })


def infer_historical_return_specs(
    dataset_query: Any,
    return_columns: list[str],
) -> dict[str, dict[str, Any]]:
    query = (
        dataset_query.model_dump(mode="python")
        if isinstance(dataset_query, FactorQuery)
        else dataset_query
    )
    derivatives = query.get("derivatives") if isinstance(query, dict) else None
    return {
        column: infer_historical_return_spec(
            column,
            derivatives.get(column) if isinstance(derivatives, dict) else None,
        )
        for column in return_columns
    }


def infer_historical_return_spec(
    column: str,
    node: Any,
) -> dict[str, Any]:
    """从 Runtime 曾生成的两类收益表达式中恢复收益口径。"""
    if not isinstance(node, dict):
        raise_historical_return_spec_error(column)
    operation = node.get("op")
    fields = node.get("fields")
    params = node.get("params")
    if operation == "unary.pct_change" and isinstance(params, dict):
        configured = params.get("periods")
        if (
            isinstance(configured, int)
            and not isinstance(configured, bool)
            and configured != 0
        ):
            return {"kind": "simple", "periods": abs(configured)}
        raise_historical_return_spec_error(column)
    if operation == "unary.log" and isinstance(fields, dict):
        periods = historical_return_expression_periods(fields.get("col"))
        if periods is not None:
            return {"kind": "log", "periods": periods}
    raise_historical_return_spec_error(column)


def historical_return_expression_periods(node: Any) -> int | None:
    if not isinstance(node, dict) or node.get("op") != "binary.div":
        return None
    fields = node.get("fields")
    if not isinstance(fields, dict):
        return None
    left = historical_shift(fields.get("left"))
    right = historical_shift(fields.get("right"))
    if left is None or right is None or left[0] != right[0]:
        return None
    distance = abs(left[1] - right[1])
    return distance or None


def historical_shift(node: Any) -> tuple[str, int] | None:
    if not isinstance(node, dict) or node.get("op") != "unary.shift":
        return None
    fields = node.get("fields")
    params = node.get("params")
    column = fields.get("col") if isinstance(fields, dict) else None
    periods = params.get("periods") if isinstance(params, dict) else None
    if (
        not isinstance(column, str)
        or not column
        or not isinstance(periods, int)
        or isinstance(periods, bool)
    ):
        return None
    return column, periods


def raise_historical_return_spec_error(column: str) -> None:
    raise ValueError(
        f"历史因子分析收益列 {column!r} 缺少 return_specs，且无法从 "
        "dataset_query.derivatives 精确推断；请显式补充 kind 和 periods"
    )


__all__ = [
    "FactorAnalysisParameters",
    "FactorReturnSpec",
    "validate_historical_factor_analysis_parameters",
]
