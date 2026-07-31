"""定义回测数据集与执行参数。"""

from collections.abc import Mapping
import re
from textwrap import dedent
from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..query.schema import FactorQuery

CallbackName: TypeAlias = Literal[
    "initialize",
    "beforeTrading",
    "onBar",
    "onSnapshot",
    "onOrder",
    "onTrade",
    "afterTrading",
    "finalize",
]
Adj: TypeAlias = Literal["hfq", "qfq"]


class BacktestParameters(BaseModel):
    """保存 Python 回测入口完成解析和规范化后的参数。"""

    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)

    name: str = Field(
        min_length=1,
        description="回测引擎名称。"
    )

    config: dict[str, Any] = Field(
        default_factory=dict,
        description="初始资金、费用和撮合等 Backtest 配置。"
    )

    codes_query: FactorQuery | None = Field(
        default=None,
        description="可选选股 DSL；结果中的 code 去重后作为正式回测股票范围。"
    )

    dataset_query: FactorQuery = Field(
        ...,
        description="用于筛选回测行情并计算策略数据的因子 DSL。"
    )

    adj: Adj | None = Field(
        default=None,
        description="价格复权方式；None 不复权，hfq 后复权，qfq 前复权。",
    )

    annual_trading_days: int = Field(
        default=250,
        ge=1,
        description="计算年化收益率和年化波动率使用的每年交易日数。"
    )

    risk_free_rate: float = Field(
        default=0.04,
        allow_inf_nan=False,
        description="计算 Sharpe 比率使用的年化无风险收益率。"
    )

    source_ref: str = Field(
        default="coreBacktestSource",
        description="基础因子查询结果变量名；存在则复用，不存在则生成。"
    )

    message_ref: str = Field(
        default="coreBacktestMessage",
        description="日频消息查询结果变量名；存在则复用，不存在则生成。"
    )

    utils: dict[str, str] | None = Field(default_factory=dict)

    callbacks: dict[CallbackName, str]

    @model_validator(mode="after")
    def validate_dataset_query_contract(self) -> "BacktestParameters":
        """补充复权因子，并校验股票范围和框架保留列。"""
        if self.adj is not None:
            if "adj_factor" in self.dataset_query.derivatives:
                raise ValueError("adj 不允许使用名为 adj_factor 的派生因子")
            if "adj_factor" not in self.dataset_query.factors:
                self.dataset_query = self.dataset_query.model_copy(
                    update={
                        "factors": [
                            *self.dataset_query.factors,
                            "adj_factor",
                        ]
                    }
                )
        output_columns = set(self.dataset_query.factors) | set(self.dataset_query.derivatives)
        if overlap := output_columns & {"symbol", "tradeTime"}:
            raise ValueError(f"以下列由回测框架生成，DSL 不能重复定义：{sorted(overlap)}")
        if self.codes_query is None:
            unsupported_codes = [code for code in self.dataset_query.codes if not code.endswith((".SH", ".SZ"))]
            if unsupported_codes:
                raise ValueError(f"股票回测当前只支持 .SH 和 .SZ 代码：{unsupported_codes[:10]}")
        return self

    @field_validator("config")
    @classmethod
    def validate_config(cls, value: dict[str, Any]) -> dict[str, Any]:
        """拒绝框架保留配置，并规范需要浮点数的插件配置。"""
        if reserved := set(value) & {"startDate", "endDate", "strategyGroup", "dataType", "msgAsTable"}:
            raise ValueError(f"以下配置由回测框架根据查询生成，不能传入：{sorted(reserved)}")

        result = {
            "cash": 1_000_000.0,
            "commission": 0.0,
            "tax": 0.0,
            "matchingMode": 2,
            **value
        }
        for name in ("cash", "commission", "tax", "matchingRatio", "orderBookMatchingRatio"):
            if name not in result:
                continue
            if isinstance(result[name], bool):
                raise ValueError(f"config[{name!r}] 必须是数值")
            try:
                result[name] = float(result[name])
            except (TypeError, ValueError) as error:
                raise ValueError(f"config[{name!r}] 必须是数值") from error
        return result

    @field_validator("dataset_query", mode="after")
    @classmethod
    def validate_dataset_query(cls, value: FactorQuery) -> FactorQuery:
        """自动加入构造日频消息所需的原始行情因子。"""
        merged = list(
            set(value.factors) |
            {"open", "low", "high", "close", "vol", "up_limit", "down_limit", "pre_close"}
        )

        if len(merged) != len(value.factors):
            value = value.model_copy(update={"factors": merged})
        return value

    @field_validator("source_ref", "message_ref")
    @classmethod
    def validate_reference(cls, value: str) -> str:
        """校验可复用 DolphinDB 会话变量名，防止脚本注入。"""
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", value) is None:
            raise ValueError(f"不是合法的 DolphinDB 变量名：{value!r}")
        return value

    @field_validator("utils")
    @classmethod
    def validate_utils(cls, value: dict[str, str] | None) -> dict[str, str]:
        """要求工具函数映射键与实际函数名一致。"""
        if value is None:
            return {}
        return {
            name: dedent(definition).strip()
            for name, definition in value.items()
        }

    @field_validator("callbacks")
    @classmethod
    def validate_callbacks(cls, value: dict[CallbackName, str]) -> dict[CallbackName, str]:
        return {
            name: dedent(definition).strip()
            for name, definition in value.items()
        }


__all__ = ["CallbackName", "Adj", "BacktestParameters"]
