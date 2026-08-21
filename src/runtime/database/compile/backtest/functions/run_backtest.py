"""定义创建并运行 DolphinDB Backtest 引擎的入口函数。"""

from runtime.database.compile import DolphinDBFunction

from .lifecycle import (
    CALLBACK_OR_DEFAULT,
    NOOP_CONTEXT_CALLBACK,
    NOOP_EVENT_CALLBACK,
    NOOP_MESSAGE_CALLBACK,
)
from .scheduler import (
    AFTER_TRADING_WITH_SCHEDULER,
    BEFORE_TRADING_WITH_SCHEDULER,
    FINALIZE_WITH_SCHEDULER,
    INITIALIZE_WITH_SCHEDULER,
    ON_SNAPSHOT_WITH_SCHEDULER,
)

RUN_BACKTEST = DolphinDBFunction(
    module="backtest",
    definition="""
    def run_backtest(name, mutable config, message, initialize_callback, before_trading_callback, on_bar_callback, on_snapshot_callback, on_order_callback, on_trade_callback, after_trading_callback, finalize_callback) {
        /*
        使用给定配置、完整消息表和全部生命周期回调创建并运行 Backtest 引擎。

        函数先规范插件配置并为缺失的生命周期回调填入空函数，随后创建引擎、
        追加行情消息并发送结束标记。合成快照按同一时间戳整批触发 onSnapshot；策略通过
        getLastData 或 getHistoryData 显式读取当前消息日期以前的数据。
        */
        if (message.rows() == 0) {
            throw "DSL 构造的回测 msg 表为空"
        }
        config["dataType"] = 1
        config["matchingMode"] = 1
        config["frequency"] = 0
        config["callbackForSnapshot"] = 0
        config["msgAsPiecesOnSnapshot"] = true
        config["matchingRatio"] = 0.0
        config["orderBookMatchingRatio"] = 1.0
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
        replay_dates = exec distinct date(timestamp)
        from message
        order by date(timestamp)
        initialize = initialize_with_scheduler{
            ,
            initialize,
            replay_dates
        }
        before_trading = before_trading_with_scheduler{
            ,
            before_trading
        }
        on_snapshot = on_snapshot_with_scheduler{
            ,
            ,
            ,
            on_snapshot
        }
        after_trading = after_trading_with_scheduler{
            ,
            after_trading
        }
        finalize = finalize_with_scheduler{, finalize}
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
        AFTER_TRADING_WITH_SCHEDULER,
        BEFORE_TRADING_WITH_SCHEDULER,
        FINALIZE_WITH_SCHEDULER,
        INITIALIZE_WITH_SCHEDULER,
        ON_SNAPSHOT_WITH_SCHEDULER,
    ),
)
