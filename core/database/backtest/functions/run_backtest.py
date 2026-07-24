"""定义创建并运行 DolphinDB Backtest 引擎的入口函数。"""

from core.database.compile import DolphinDBFunction

from .lifecycle import (
    CALLBACK_OR_DEFAULT,
    NOOP_CONTEXT_CALLBACK,
    NOOP_EVENT_CALLBACK,
    NOOP_MESSAGE_CALLBACK,
)

RUN_BACKTEST = DolphinDBFunction(
    module="backtest",
    definition="""
    def run_backtest(name, mutable config, message, unfiltered_factor_data, filtered_factor_data, initialize_callback, before_trading_callback, on_bar_callback, on_snapshot_callback, on_order_callback, on_trade_callback, after_trading_callback, finalize_callback) {
        /*
        使用给定配置、完整消息表和全部生命周期回调创建并运行 Backtest 引擎。

        函数先规范插件配置并为缺失的生命周期回调填入空函数，随后创建引擎、
        追加行情消息并发送结束标记。onBar 使用插件原始回调时点；策略通过
        getLastData 或 getHistoryData 显式读取当前消息日期以前的数据。
        unfiltered_factor_data 和 filtered_factor_data 分别是 filters 前、
        filters 后的 DSL 因子结果表。
        */
        if (message.rows() == 0) {
            throw "DSL 构造的回测 msg 表为空"
        }
        int_config_names = [
            "dataType",
            "matchingMode",
            "frequency",
            "latency",
            "callbackForSnapshot",
            "outputQueuePosition"
        ]
        for (config_name in int_config_names) {
            if (config_name in config) {
                config[config_name] = int(config[config_name])
            }
        }

        initialize = callback_or_default(
            initialize_callback,
            noop_context_callback
        )
        before_trading = callback_or_default(
            before_trading_callback,
            noop_context_callback
        )
        on_bar = callback_or_default(
            on_bar_callback,
            noop_message_callback
        )
        on_snapshot = callback_or_default(
            on_snapshot_callback,
            noop_message_callback
        )
        on_order = callback_or_default(
            on_order_callback,
            noop_event_callback
        )
        on_trade = callback_or_default(
            on_trade_callback,
            noop_event_callback
        )
        after_trading = callback_or_default(
            after_trading_callback,
            noop_context_callback
        )
        finalize = callback_or_default(
            finalize_callback,
            noop_context_callback
        )
        engine = Backtest::createBacktestEngine(
            name,
            config,
            ,
            initialize,
            before_trading,
            on_bar,
            on_snapshot,
            on_order,
            on_trade,
            after_trading,
            finalize
        )
        strategy_context = Backtest::getContextDict(engine)
        strategy_context["coreBacktestUnfilteredFactorData"] =
            unfiltered_factor_data
        strategy_context["coreBacktestFilteredFactorData"] =
            filtered_factor_data
        try {
            Backtest::appendQuotationMsg(engine, message)
            Backtest::appendEndMarker(engine)
        } catch (error) {
            Backtest::dropBacktestEngine(engine)
            throw error
        }
        return engine
    }
    """,
    dependencies=(
        CALLBACK_OR_DEFAULT,
        NOOP_CONTEXT_CALLBACK,
        NOOP_EVENT_CALLBACK,
        NOOP_MESSAGE_CALLBACK,
    ),
)

__all__ = ["RUN_BACKTEST"]
