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
FUNCTION_PATTERN = re.compile(r"^def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")
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
RESERVED_CONFIG = frozenset(("startDate", "endDate", "strategyGroup", "dataType", "msgAsTable"))
DEFAULT_CONFIG = {
    "cash": 1_000_000.0,
    "commission": 0.0,
    "tax": 0.0,
    "matchingMode": 2,
}
FLOAT_CONFIG = ("cash", "commission", "tax", "matchingRatio", "orderBookMatchingRatio")


def function_name(definition: str) -> str:
    """从 DolphinDB 函数定义中读取函数名。"""
    match = FUNCTION_PATTERN.match(dedent(definition).strip())
    if match is None:
        raise ValueError("函数必须以完整的 DolphinDB def 定义开头")
    return match.group(1)


class BacktestParameters(BaseModel):
    """保存 Python 回测入口完成解析和规范化后的参数。"""

    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)

    dataset_query: FactorQuery = Field(..., description="用于筛选回测行情并计算策略数据的因子 DSL。")
    codes_query: FactorQuery | None = Field(default=None, description="可选选股 DSL；结果中的 code 去重后作为正式回测股票范围。")
    adj: Adj | None = Field(
        default=None,
        description="价格复权方式；None 不复权，hfq 后复权，qfq 前复权。",
    )
    name: str | None = Field(default=None, min_length=1, description="可选回测引擎名称。")
    config: dict[str, Any] = Field(default_factory=dict, description="初始资金、费用和撮合等 Backtest 配置。")
    annual_trading_days: int = Field(default=250, ge=1, description="计算年化收益率和年化波动率使用的每年交易日数。")
    risk_free_rate: float = Field(default=0.04, allow_inf_nan=False, description="计算 Sharpe 比率使用的年化无风险收益率。")
    callbacks: dict[CallbackName, str]
    utils: dict[str, str] = Field(default_factory=dict)
    source_ref: str = Field(default="coreBacktestSource", description="基础因子查询结果变量名；存在则复用，不存在则生成。")
    message_ref: str = Field(default="coreBacktestMessage", description="日频消息查询结果变量名；存在则复用，不存在则生成。")

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
            raise ValueError(f"以下配置由回测框架根据查询生成，不能传入：{sorted(reserved)}")

        result = {**DEFAULT_CONFIG, **value}
        for name in FLOAT_CONFIG:
            if name not in result:
                continue
            if isinstance(result[name], bool):
                raise ValueError(f"config[{name!r}] 必须是数值")
            try:
                result[name] = float(result[name])
            except (TypeError, ValueError) as error:
                raise ValueError(f"config[{name!r}] 必须是数值") from error
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

    @field_validator("dataset_query", mode="before")
    @classmethod
    def validate_dataset_query(cls, value: Any) -> Any:
        """只接受字典，并在参数模型校验时转换为 FactorQuery。"""
        if not isinstance(value, dict):
            raise ValueError("dataset_query 必须是 dict[str, Any]")
        return value

    @field_validator("codes_query", mode="before")
    @classmethod
    def validate_codes_query(cls, value: Any) -> Any:
        """只接受字典，并在字段校验时转换为 FactorQuery。"""
        if value is not None and not isinstance(value, dict):
            raise ValueError("codes_query 必须是 dict[str, Any] 或 None")
        return value

    @model_validator(mode="after")
    def validate_dataset_query_contract(self) -> "BacktestParameters":
        """校验股票范围和日频行情列是否符合回测入口契约。"""
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
        if overlap := output_columns & SYSTEM_COLUMNS:
            raise ValueError(f"以下列由回测框架生成，DSL 不能重复定义：{sorted(overlap)}")
        if missing := DAILY_REQUIRED_COLUMNS - output_columns:
            raise ValueError(f"日频消息缺少必需的 factor 或派生因子：{sorted(missing)}")
        if self.codes_query is None:
            unsupported_codes = [code for code in self.dataset_query.codes if not code.endswith((".SH", ".SZ"))]
            if unsupported_codes:
                raise ValueError(f"股票回测当前只支持 .SH 和 .SZ 代码：{unsupported_codes[:10]}")
        return self

    @field_validator("source_ref", "message_ref")
    @classmethod
    def validate_reference(cls, value: str) -> str:
        """校验可复用 DolphinDB 会话变量名，防止脚本注入。"""
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", value) is None:
            raise ValueError(f"不是合法的 DolphinDB 变量名：{value!r}")
        return value

    @field_validator("callbacks", mode="before")
    @classmethod
    def parse_callbacks(cls, value: Any) -> Any:
        """把回调 Mapping 规范为字典。"""
        return dict(value) if isinstance(value, Mapping) else value

    @field_validator("callbacks")
    @classmethod
    def validate_callbacks(cls, value: dict[CallbackName, str]) -> dict[CallbackName, str]:
        """校验并整理回调函数定义字符串。"""
        result: dict[CallbackName, str] = {}
        for name, definition in value.items():
            normalized = dedent(definition).strip()
            actual_name = function_name(normalized)
            if actual_name != name:
                raise ValueError(f"callbacks[{name!r}] 必须定义函数 {name!r}，实际为 {actual_name!r}")
            result[name] = normalized
        return result

    @field_validator("utils", mode="before")
    @classmethod
    def parse_utils(cls, value: Any) -> Any:
        """把可选工具函数 Mapping 规范为字典。"""
        if value is None:
            return {}
        return dict(value) if isinstance(value, Mapping) else value

    @field_validator("utils")
    @classmethod
    def validate_utils(cls, value: dict[str, str]) -> dict[str, str]:
        """要求工具函数映射键与实际函数名一致。"""
        result: dict[str, str] = {}
        for name, definition in value.items():
            if not name.strip():
                raise ValueError("utils 的键必须是非空函数名")
            normalized = dedent(definition).strip()
            actual_name = function_name(normalized)
            if name != actual_name:
                raise ValueError(f"utils[{name!r}] 定义的函数名是 {actual_name!r}")
            result[name] = normalized
        return result


__all__ = ["CallbackName"]
