"""使用因子 DSL 构造日频消息，并运行 DolphinDB Backtest 策略。"""

from collections.abc import Mapping
import time
from typing import Any, TypeAlias
from uuid import uuid4

import numpy as np
import pandas as pd

from core.database import create_session
from core.query.api import build_query_table
from core.query.dolphindb import (
    DolphinDBFunction,
    collect_functions,
    render_functions,
)
from core.query.schema import (
    FactorQuery,
    derivative_output_kind,
)
from core.utils import CODE_COLUMN, TIME_COLUMN, logger, normalize_date_range

from .schema import BacktestResult

Callback: TypeAlias = str | DolphinDBFunction

CALLBACK_NAMES = (
    "initialize",
    "beforeTrading",
    "onBar",
    "onSnapshot",
    "onOrder",
    "onTrade",
    "afterTrading",
    "finalize",
)
CALLBACK_PARAMETERS = {
    "initialize": "mutable context",
    "beforeTrading": "mutable context",
    "onBar": "mutable context, msg, indicator",
    "onSnapshot": "mutable context, msg, indicator",
    "onOrder": "mutable context, order",
    "onTrade": "mutable context, trade",
    "afterTrading": "mutable context",
    "finalize": "mutable context",
}
DAILY_REQUIRED_COLUMNS = (
    "open",
    "low",
    "high",
    "close",
    "volume",
    "upLimitPrice",
    "downLimitPrice",
    "prevClosePrice",
)
SELECTION_COLUMN = "coreBacktestSelected"
SYSTEM_COLUMNS = frozenset(("symbol", "tradeTime", SELECTION_COLUMN))
RESERVED_CONFIG = frozenset(
    ("startDate", "endDate", "strategyGroup", "dataType", "msgAsTable")
)
DEFAULT_CONFIG = {
    "cash": 1_000_000.0,
    "commission": 0.0,
    "tax": 0.0,
    "matchingMode": 2,
}


def _prepare_callbacks(
    callbacks: Mapping[str, Callback],
    *,
    token: str,
) -> tuple[str, dict[str, str], str]:
    """规范回调定义，补齐旧版引擎要求的空回调。"""
    unknown = set(callbacks) - set(CALLBACK_NAMES)
    if unknown:
        raise ValueError(f"未知回调函数：{sorted(unknown)}")
    if "onBar" not in callbacks:
        raise ValueError("日频回测必须传入 onBar 回调函数")

    functions: dict[str, DolphinDBFunction] = {}
    for callback_name in CALLBACK_NAMES:
        callback = callbacks.get(callback_name)
        if callback is None:
            callback = (
                f"def core_backtest_{callback_name}"
                f"({CALLBACK_PARAMETERS[callback_name]}) {{ return NULL }}"
            )
        function = (
            callback
            if isinstance(callback, DolphinDBFunction)
            else DolphinDBFunction(callback)
        )
        expected_count = len(CALLBACK_PARAMETERS[callback_name].split(","))
        if len(function.parameters) != expected_count:
            raise ValueError(
                f"{callback_name} 回调参数数量应为 {expected_count}，"
                f"实际为 {len(function.parameters)}"
            )
        functions[callback_name] = function

    definitions = render_functions(collect_functions(functions.values()))
    names = {
        callback_name: function.name for callback_name, function in functions.items()
    }
    user_on_bar = names["onBar"]
    wrapper_name = f"core_backtest_on_bar_{token}"
    context_key = f"coreBacktestPreviousMessage_{token}"
    definitions += f"""

def {wrapper_name}(mutable context, msg, indicator) {{
    selectedMessage = msg[msg.{SELECTION_COLUMN} == 1]
    dropColumns!(selectedMessage, `{SELECTION_COLUMN})

    if ("{context_key}" in context) {{
        previousMessage = context["{context_key}"]
        if (previousMessage.rows() > 0) {{
            {user_on_bar}(context, previousMessage, indicator)
        }}
    }}
    context["{context_key}"] = selectedMessage
}}
"""
    names["onBar"] = wrapper_name
    return definitions, names, context_key


def _load_plugins(session: Any) -> None:
    """按依赖顺序加载撮合引擎和回测插件。"""
    loaded = session.run("getLoadedPlugins()")
    loaded_names = (
        set(loaded["plugin"].astype(str))
        if isinstance(loaded, pd.DataFrame) and "plugin" in loaded
        else set()
    )
    for plugin in ("MatchingEngineSimulator", "Backtest"):
        if plugin not in loaded_names:
            session.run(f'loadPlugin("{plugin}")')


def _as_frame(value: Any) -> pd.DataFrame:
    """把插件对空表返回的空容器统一为 DataFrame。"""
    if isinstance(value, pd.DataFrame):
        return value.reset_index(drop=True)
    if value is None or (isinstance(value, (list, tuple, dict)) and not value):
        return pd.DataFrame()
    raise TypeError(f"DolphinDB Backtest 输出必须是表，实际为 {type(value).__name__}")


def _select_codes(
    request: FactorQuery | dict[str, Any],
    *,
    session: Any,
) -> list[str]:
    """执行选股 DSL，并返回结果中去重、排序后的股票代码。"""
    build_query_table(request, session=session)
    selected = session.run(
        f"""
        select distinct {CODE_COLUMN}
        from coreDslOutput
        where not isNull({CODE_COLUMN})
        order by {CODE_COLUMN}
        """
    )
    if not isinstance(selected, pd.DataFrame):
        raise TypeError(
            "codes DSL 的去重结果必须是 DataFrame，"
            f"实际为 {type(selected).__name__}"
        )
    if tuple(selected.columns) != (CODE_COLUMN,):
        raise ValueError(
            "codes DSL 的去重结果列不符合契约："
            f"期望 [{CODE_COLUMN!r}]，实际 {list(selected.columns)}"
        )

    codes = selected[CODE_COLUMN].astype(str).tolist()
    if not codes:
        raise ValueError("codes DSL 没有选出任何股票")
    logger.info(f"codes DSL 选出 {len(codes):,} 只股票")
    return codes


def run_backtest(
    request: FactorQuery | dict[str, Any],
    callbacks: Mapping[str, Callback],
    *,
    codes_query: FactorQuery | dict[str, Any] | None = None,
    name: str | None = None,
    config: Mapping[str, Any] | None = None,
    session: Any | None = None,
) -> BacktestResult:
    """用 DSL 输出作为完整 msg 表，同步运行一次股票日频回测。

    ``codes_query`` 存在时，先执行该 DSL，并把结果中的去重代码作为正式
    ``request`` 的股票范围。
    框架在执行层缓存当日经过 filters 的完整消息，并在下一交易日调用
    ``onBar``；回调看不到下一日行情，因此 DSL 不需要自行 ``shift(1)``。
    ``onBar`` 必须接收 ``(mutable context, msg, indicator)``。插件会缓冲最后
    一个时间点，因此查询区间应在最后一个需要触发策略的交易日之后再包含一根
    真实日线。
    """
    started = time.perf_counter()
    engine_name = name or f"coreBacktest_{uuid4().hex}"
    if not engine_name.strip():
        raise ValueError("回测引擎名称不能为空")

    user_config = dict(config or {})
    if reserved := set(user_config) & RESERVED_CONFIG:
        raise ValueError(
            f"以下回测配置由框架根据查询固定生成，不能传入：{sorted(reserved)}"
        )
    merged_config = {**DEFAULT_CONFIG, **user_config}
    for config_name in (
        "cash",
        "commission",
        "tax",
        "matchingRatio",
        "orderBookMatchingRatio",
    ):
        if config_name in merged_config:
            merged_config[config_name] = float(merged_config[config_name])

    owns_session = session is None
    current_session = create_session() if owns_session else session
    engine_created = False
    try:
        query = (
            request
            if isinstance(request, FactorQuery)
            else FactorQuery.model_validate(request)
        )
        if codes_query is not None:
            query = query.model_copy(
                update={
                    "codes": _select_codes(
                        codes_query,
                        session=current_session,
                    )
                }
            )
        if unsupported := [
            code for code in query.codes if not code.endswith((".SH", ".SZ"))
        ]:
            raise ValueError(
                f"股票回测当前只支持 .SH 和 .SZ 代码：{unsupported[:10]}"
            )

        query, output_columns = build_query_table(
            query,
            session=current_session,
        )
        if overlap := set(output_columns) & SYSTEM_COLUMNS:
            raise ValueError(
                "以下列由回测框架生成，DSL 不能重复定义："
                f"{sorted(overlap)}"
            )
        if missing := set(DAILY_REQUIRED_COLUMNS) - set(output_columns):
            raise ValueError(
                f"日频 msg 缺少必需的 factor 或命名派生因子：{sorted(missing)}"
            )

        extension_columns = [
            column
            for column in output_columns
            if column not in (TIME_COLUMN, CODE_COLUMN)
        ]
        user_message_columns = [
            "symbol",
            "tradeTime",
            *extension_columns,
        ]
        message_columns = [
            *user_message_columns,
            SELECTION_COLUMN,
        ]
        callback_script, callback_names, callback_context_key = _prepare_callbacks(
            callbacks,
            token=uuid4().hex,
        )
        bool_columns = [
            column
            for column, derivative in query.derivatives.items()
            if derivative_output_kind(derivative) == "BOOL"
        ]
        output_start, output_end = normalize_date_range(
            query.start_date,
            query.end_date,
        )
        backtest_config = {
            **merged_config,
            "startDate": output_start.to_datetime64().astype("datetime64[D]"),
            "endDate": output_end.to_datetime64().astype("datetime64[D]"),
            "strategyGroup": "stock",
            "dataType": 4,
            "msgAsTable": True,
        }
        current_session.upload(
            {
                "coreBacktestName": engine_name,
                "coreBacktestConfig": backtest_config,
                "coreBacktestColumns": np.asarray(
                    message_columns,
                    dtype=str,
                ),
                "coreBacktestBoolColumns": np.asarray(
                    bool_columns,
                    dtype=str,
                ),
            }
        )
        current_session.run(
            """
            coreBacktestMsg = project_factor_output(
                coreDslComputed,
                coreDslOutputColumns,
                coreOutputStart,
                coreOutputEndExclusive
            )
            coreBacktestSelectedRows = select
                time,
                code,
                int(1) as coreBacktestSelected
            from coreDslOutput
            coreBacktestMsg = lj(coreBacktestMsg, coreBacktestSelectedRows, `time`code)
            replaceColumn!(
                coreBacktestMsg,
                `coreBacktestSelected,
                nullFill(coreBacktestMsg.coreBacktestSelected, int(0))
            )

            coreBacktestValidRows = take(true, coreBacktestMsg.rows())
            for (column in `open`low`high`close`volume`upLimitPrice`downLimitPrice`prevClosePrice) {
                coreBacktestValidRows = coreBacktestValidRows &&
                    !isNull(coreBacktestMsg[column])
            }
            coreBacktestMsg = coreBacktestMsg[coreBacktestValidRows]
            rename!(
                coreBacktestMsg,
                `code`time,
                `symbol`tradeTime
            )
            replaceColumn!(
                coreBacktestMsg,
                `symbol,
                symbol(
                    strReplace(
                        strReplace(
                            string(coreBacktestMsg.symbol),
                            ".SZ",
                            ".XSHE"
                        ),
                        ".SH",
                        ".XSHG"
                    )
                )
            )
            replaceColumn!(
                coreBacktestMsg,
                `tradeTime,
                temporalAdd(
                    timestamp(coreBacktestMsg.tradeTime),
                    15,
                    "h"
                )
            )
            replaceColumn!(
                coreBacktestMsg,
                `volume,
                long(coreBacktestMsg.volume)
            )
            for (column in `open`low`high`close`upLimitPrice`downLimitPrice`prevClosePrice) {
                replaceColumn!(
                    coreBacktestMsg,
                    column,
                    double(coreBacktestMsg[column])
                )
            }
            for (column in coreBacktestBoolColumns) {
                replaceColumn!(
                    coreBacktestMsg,
                    column,
                    int(coreBacktestMsg[column])
                )
            }
            reorderColumns!(
                coreBacktestMsg,
                symbol(coreBacktestColumns)
            )
            coreBacktestMsg.sortBy!(`tradeTime`symbol)
            """
        )
        message_rows = int(current_session.run("coreBacktestMsg.rows()"))
        if message_rows == 0:
            raise ValueError("DSL 构造的回测 msg 表为空")

        _load_plugins(current_session)
        current_session.run(callback_script)
        current_session.run(
            f"""
            coreBacktestIntConfigNames = [
                "dataType",
                "matchingMode",
                "frequency",
                "latency",
                "callbackForSnapshot",
                "outputQueuePosition"
            ]
            for (configName in coreBacktestIntConfigNames) {{
                if (configName in coreBacktestConfig) {{
                    coreBacktestConfig[configName] = int(
                        coreBacktestConfig[configName]
                    )
                }}
            }}
            coreBacktestEngine = Backtest::createBacktestEngine(
                coreBacktestName,
                coreBacktestConfig,
                ,
                {callback_names["initialize"]},
                {callback_names["beforeTrading"]},
                {callback_names["onBar"]},
                {callback_names["onSnapshot"]},
                {callback_names["onOrder"]},
                {callback_names["onTrade"]},
                {callback_names["afterTrading"]},
                {callback_names["finalize"]}
            )
            """
        )
        engine_created = True
        current_session.run(
            """
            Backtest::appendQuotationMsg(
                coreBacktestEngine,
                coreBacktestMsg
            )
            Backtest::appendEndMarker(coreBacktestEngine)
            """
        )

        context = current_session.run("Backtest::getContextDict(coreBacktestEngine)")
        if isinstance(context, dict):
            context.pop("engine", None)
            context.pop(callback_context_key, None)

        backtest_result = BacktestResult(
            name=engine_name,
            message_rows=message_rows,
            trade_details=_as_frame(
                current_session.run("Backtest::getTradeDetails(coreBacktestEngine)")
            ),
            daily_positions=_as_frame(
                current_session.run("Backtest::getDailyPosition(coreBacktestEngine)")
            ),
            daily_portfolios=_as_frame(
                current_session.run(
                    "Backtest::getDailyTotalPortfolios(coreBacktestEngine)"
                )
            ),
            return_summary=_as_frame(
                current_session.run("Backtest::getReturnSummary(coreBacktestEngine)")
            ),
            daily_trading_statistics=_as_frame(
                current_session.run(
                    "Backtest::getDailyTradingStatistics(coreBacktestEngine)"
                )
            ),
            engine_stat=_as_frame(
                current_session.run(
                    "Backtest::getBacktestEngineStat(coreBacktestEngine)"
                )
            ),
            context=context,
        )
        logger.success(
            f"回测完成：name={engine_name}，msg={message_rows:,} 行，"
            f"成交明细={len(backtest_result.trade_details):,} 行，"
            f"耗时={time.perf_counter() - started:.2f} 秒"
        )
        return backtest_result
    except Exception as error:
        logger.exception(f"回测失败：name={engine_name}，{error}")
        raise
    finally:
        if engine_created:
            try:
                current_session.run("Backtest::dropBacktestEngine(coreBacktestEngine)")
            except Exception:
                logger.exception(f"清理回测引擎失败：name={engine_name}")
        if owns_session:
            current_session.close()


__all__ = [
    "BacktestResult",
    "Callback",
    "run_backtest",
]
