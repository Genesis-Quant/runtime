"""定义回测请求与执行结果。"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, get_args, Literal, TypeAlias

import pandas as pd
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from core.database.compile import DolphinDBFunction
from core.query import FactorQuery

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
Callback: TypeAlias = str | DolphinDBFunction
Utility: TypeAlias = str | DolphinDBFunction

CALLBACK_NAMES = get_args(CallbackName)
DAILY_REQUIRED_COLUMNS = frozenset(
    (
        "open",
        "low",
        "high",
        "close",
        "volume",
        "upLimitPrice",
        "downLimitPrice",
        "prevClosePrice",
    )
)
SYSTEM_COLUMNS = frozenset(("symbol", "tradeTime"))
RESERVED_CONFIG = frozenset(
    ("startDate", "endDate", "strategyGroup", "dataType", "msgAsTable")
)
DEFAULT_CONFIG = {
    "cash": 1_000_000.0,
    "commission": 0.0,
    "tax": 0.0,
    "matchingMode": 2,
}
FLOAT_CONFIG = (
    "cash",
    "commission",
    "tax",
    "matchingRatio",
    "orderBookMatchingRatio",
)


class BacktestArguments(BaseModel):
    """集中校验查询、引擎名称和插件配置等公共回测参数。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        validate_default=True,
    )

    codes_query: FactorQuery | None = Field(
        default=None,
        description="可选选股 DSL；结果中的 code 去重后作为正式回测股票范围。",
    )
    query: FactorQuery = Field(
        ...,
        description="用于筛选回测行情并计算策略数据的因子 DSL。",
    )
    name: str | None = Field(
        default=None,
        min_length=1,
        description="可选回测引擎名称。",
    )
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="初始资金、费用和撮合等 Backtest 配置。",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        """拒绝仅包含空白字符的引擎名称。"""
        if value is not None and not value.strip():
            raise ValueError("回测引擎名称不能为空")
        return value

    @field_validator("config")
    @classmethod
    def validate_config(cls, value: dict[str, Any]) -> dict[str, Any]:
        """拒绝框架保留配置，并规范需要浮点数的插件配置。"""
        if reserved := set(value) & RESERVED_CONFIG:
            raise ValueError(
                "以下配置由回测框架根据查询生成，不能传入："
                f"{sorted(reserved)}"
            )

        result = {**DEFAULT_CONFIG, **value}
        for name in FLOAT_CONFIG:
            if name not in result:
                continue
            if isinstance(result[name], bool):
                raise ValueError(f"config[{name!r}] 必须是数值")
            try:
                result[name] = float(result[name])
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"config[{name!r}] 必须是数值"
                ) from error
        return result

    @field_validator("config", mode="before")
    @classmethod
    def parse_config(cls, value: Any) -> Any:
        """在 Pydantic 内把可选 Mapping 规范为配置字典。"""
        if value is None:
            return {}
        if isinstance(value, Mapping):
            return dict(value)
        return value

    @model_validator(mode="after")
    def validate_query_contract(self) -> "BacktestArguments":
        """校验股票范围和日频行情列是否符合回测入口契约。"""
        output_columns = set(self.query.factors) | set(
            self.query.derivatives
        )
        if overlap := output_columns & SYSTEM_COLUMNS:
            raise ValueError(
                "以下列由回测框架生成，DSL 不能重复定义："
                f"{sorted(overlap)}"
            )
        if missing := DAILY_REQUIRED_COLUMNS - output_columns:
            raise ValueError(
                "日频消息缺少必需的 factor 或派生因子："
                f"{sorted(missing)}"
            )
        if self.codes_query is None:
            unsupported_codes = [
                code
                for code in self.query.codes
                if not code.endswith((".SH", ".SZ"))
            ]
            if unsupported_codes:
                raise ValueError(
                    "股票回测当前只支持 .SH 和 .SZ 代码："
                    f"{unsupported_codes[:10]}"
                )
        return self


class BacktestParameters(BacktestArguments):
    """保存 Python 回测入口完成解析和规范化后的参数。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        validate_default=True,
        arbitrary_types_allowed=True,
    )

    callbacks: dict[CallbackName, DolphinDBFunction]
    utils: dict[str, DolphinDBFunction] = Field(default_factory=dict)

    @field_validator("callbacks", mode="before")
    @classmethod
    def parse_callbacks(cls, value: Any) -> Any:
        """把回调定义字符串转换为可编译的 DolphinDBFunction。"""
        if not isinstance(value, Mapping):
            return value
        return {
            name: (
                DolphinDBFunction(function)
                if isinstance(function, str)
                else function
            )
            for name, function in value.items()
        }

    @field_validator("utils", mode="before")
    @classmethod
    def parse_utils(cls, value: Any) -> Any:
        """把可选工具函数映射转换为 DolphinDBFunction 字典。"""
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            return value
        return {
            name: (
                DolphinDBFunction(function)
                if isinstance(function, str)
                else function
            )
            for name, function in value.items()
        }

    @field_validator("utils")
    @classmethod
    def validate_utils(
        cls,
        value: dict[str, DolphinDBFunction],
    ) -> dict[str, DolphinDBFunction]:
        """要求工具函数映射键与实际函数名一致。"""
        for name, function in value.items():
            if not name.strip():
                raise ValueError("utils 的键必须是非空函数名")
            if name != function.name:
                raise ValueError(
                    f"utils[{name!r}] 定义的函数名是 {function.name!r}"
                )
        return value


class BacktestRunRequest(BacktestArguments):
    """描述 FastAPI 接收的一次同步日频回测请求。"""

    callbacks: dict[CallbackName, str] = Field(
        ...,
        description="DolphinDB 回调名称到函数定义的映射。",
    )
    utils: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "自定义工具函数名称到独立 DolphinDB 函数定义的映射；"
            "内置 getLastData 和 getHistoryData 无需传入。"
        ),
    )

    @field_validator("callbacks")
    @classmethod
    def validate_callback_definitions(
        cls,
        value: dict[str, str],
    ) -> dict[str, str]:
        """校验 HTTP 回调函数定义。"""
        for definition in value.values():
            DolphinDBFunction(definition)
        return value

    @field_validator("utils")
    @classmethod
    def validate_utility_definitions(
        cls,
        value: dict[str, str],
    ) -> dict[str, str]:
        """校验 HTTP 工具函数定义及映射名称。"""
        for name, definition in value.items():
            function = DolphinDBFunction(definition)
            if not name.strip():
                raise ValueError("utils 的键必须是非空函数名")
            if name != function.name:
                raise ValueError(
                    f"utils[{name!r}] 定义的函数名是 "
                    f"{function.name!r}"
                )
        return value


@dataclass(frozen=True, slots=True)
class BacktestResult:
    """保存一次已结束回测的标准输出。"""

    name: str
    message_rows: int
    trade_details: pd.DataFrame
    daily_positions: pd.DataFrame
    daily_portfolios: pd.DataFrame
    return_summary: pd.DataFrame
    daily_trading_statistics: pd.DataFrame
    engine_stat: pd.DataFrame
    context: Any


__all__ = [
    "BacktestArguments",
    "BacktestParameters",
    "BacktestResult",
    "BacktestRunRequest",
    "Callback",
    "CallbackName",
    "Utility",
]
