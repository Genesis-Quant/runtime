"""定义回测数据集与执行参数。"""

import math
from numbers import Integral, Real
from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from runtime.utils import normalize_dolphindb_functions

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
CALLBACK_PARAMETER_COUNTS = {
    "initialize": 1,
    "beforeTrading": 1,
    "onBar": 3,
    "onSnapshot": 3,
    "onOrder": 2,
    "onTrade": 2,
    "afterTrading": 1,
    "finalize": 1,
}
BACKTEST_BOOLEAN_CONFIGS = frozenset({
    "enableIndicatorOptimize",
    "isBacktestMode",
    "addTimeColumnInIndicator",
    "enableSubscriptionToTickQuotes",
    "outputOrderInfo",
    "repayWithoutMarginBuy",
    "outputSeqNum",
    "outputTradeSeqNum",
    "multiAssetQuoteUnifiedInput",
    "enableAlgoOrder",
    "immediateOrderConfirmation",
    "immediateCancel",
    "enableMinimumPerTransactionFee",
    "enableSellCloseRestrict",
})


class BacktestParameters(BaseModel):
    """保存 Python 回测入口完成解析和规范化后的参数。"""

    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)

    config: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "用户可配置的资金、费用、syntheticSpread 和输出选项。当前不支持 benchmark；"
            "日期、策略类型、快照 dataType/matchingMode、回调模式及两种撮合比例由 Runtime 固定。"
        ),
    )

    params: dict[str, Any] = Field(
        default_factory=dict,
        description="传给策略的简单参数字典，可在回调中通过 getParams() 读取。",
    )

    codes_query: FactorQuery | None = Field(
        default=None,
        description="可选第一阶段选股 DSL；结果中的 code 去重后作为 dataset_query 的候选代码。"
    )

    dataset_query: FactorQuery = Field(
        ...,
        description="第二阶段策略数据 DSL；保留自身 filters，以第一阶段候选代码生成动态股票池。"
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

    utils: str = Field(
        default="",
        description="在生命周期回调注册前原样执行的 DolphinDB 脚本。",
    )

    callbacks: dict[CallbackName, str] = Field(
        ...,
        description=(
            "必须且只能包含 initialize、beforeTrading、onBar、onSnapshot、onOrder、"
            "onTrade、afterTrading、finalize；值为同名完整 DolphinDB def。"
        ),
    )

    @model_validator(mode="after")
    def validate_dataset_query_contract(self) -> "BacktestParameters":
        """校验股票范围和框架保留列。"""
        if self.adj is not None:
            if "adj_factor" in self.dataset_query.derivatives:
                raise ValueError("adj 不允许使用名为 adj_factor 的派生因子")
        output_columns = set(self.dataset_query.factors) | set(self.dataset_query.derivatives)
        if overlap := output_columns & {"symbol", "tradeTime"}:
            raise ValueError(f"以下列由回测框架生成，DSL 不能重复定义：{sorted(overlap)}")
        if self.codes_query is None:
            if not self.dataset_query.codes:
                raise ValueError("codes_query 为空时 dataset_query.codes 不能为空")
            unsupported_codes = [code for code in self.dataset_query.codes if not code.endswith((".SH", ".SZ"))]
            if unsupported_codes:
                raise ValueError(f"股票回测当前只支持 .SH 和 .SZ 代码：{unsupported_codes[:10]}")
        return self

    @field_validator("config", mode="before")
    @classmethod
    def validate_config(cls, value: Any) -> dict[str, Any]:
        """拒绝框架保留配置，并校验已知 Backtest 插件配置。"""
        if value is None:
            value = {}
        if not isinstance(value, dict):
            raise ValueError("config 必须是 dict[str, Any]")
        if "benchmark" in value:
            raise ValueError("当前回测不支持 config['benchmark']")
        if reserved := set(value) & {
            "startDate", "endDate", "strategyGroup", "dataType", "msgAsTable",
            "matchingMode", "frequency", "callbackForSnapshot",
            "msgAsPiecesOnSnapshot", "matchingRatio", "orderBookMatchingRatio",
        }:
            raise ValueError(f"以下配置由回测框架根据查询生成，不能传入：{sorted(reserved)}")

        result = {
            "cash": 1_000_000.0,
            "commission": 0.0,
            "tax": 0.0,
            "enableMinimumPerTransactionFee": True,
            **value
        }
        for name in ("cash", "commission", "tax", "syntheticSpread"):
            if name not in result:
                continue
            if isinstance(result[name], bool) or not isinstance(result[name], Real):
                raise ValueError(f"config[{name!r}] 必须是数值")
            result[name] = float(result[name])
            if not math.isfinite(result[name]):
                raise ValueError(f"config[{name!r}] 不能是 NaN 或正负无穷")
        if result["cash"] <= 0:
            raise ValueError("config['cash'] 必须大于 0")
        for name in ("commission", "tax"):
            if name in result and result[name] < 0:
                raise ValueError(f"config[{name!r}] 不能小于 0")
        if "syntheticSpread" in result and not 0 <= result["syntheticSpread"] < 1:
            raise ValueError("config['syntheticSpread'] 必须位于 [0, 1)")
        if "outputQueuePosition" in result:
            value = result["outputQueuePosition"]
            if isinstance(value, bool) or not isinstance(value, Integral):
                raise ValueError("config['outputQueuePosition'] 必须是整数")
            result["outputQueuePosition"] = int(value)
            if result["outputQueuePosition"] not in {0, 1, 2}:
                raise ValueError("config['outputQueuePosition'] 只能是 [0, 1, 2]")
        if "latency" in result:
            value = result["latency"]
            if isinstance(value, bool) or not isinstance(value, Integral):
                raise ValueError("config['latency'] 必须是整数")
            result["latency"] = int(value)
            if result["latency"] < 0:
                raise ValueError("config['latency'] 不能小于 0")
        for name in BACKTEST_BOOLEAN_CONFIGS & set(result):
            if not isinstance(result[name], bool):
                raise ValueError(f"config[{name!r}] 必须是 bool")
        return result

    @field_validator("callbacks", mode="before")
    @classmethod
    def validate_callbacks(cls, value: Any) -> dict[str, str]:
        return normalize_dolphindb_functions(
            value,
            "callbacks",
            parameter_counts=CALLBACK_PARAMETER_COUNTS,
        )

__all__ = ["CallbackName", "Adj", "BacktestParameters", "CALLBACK_PARAMETER_COUNTS"]
