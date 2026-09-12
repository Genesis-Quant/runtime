"""定义创建并运行 DolphinDB Backtest 引擎的入口函数。"""

from runtime.database.compile import DolphinDBFunction

CREATE_BACKTEST_ENGINE = DolphinDBFunction(
    module="backtest",
    definition="""
    def create_backtest_engine(name, mutable config, initialize_callback, before_trading_callback, on_bar_callback, on_snapshot_callback, on_order_callback, on_trade_callback, after_trading_callback, finalize_callback) {
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

        return Backtest::createBacktestEngine(
            name,
            config,
            ,
            initialize_callback,
            before_trading_callback,
            on_bar_callback,
            on_snapshot_callback,
            on_order_callback,
            on_trade_callback,
            after_trading_callback,
            finalize_callback
        )
    }
    """,
)

RUN_BACKTEST = DolphinDBFunction(
    module="backtest",
    definition="""
    def run_backtest(name, mutable config, message, initialize_callback, before_trading_callback, on_bar_callback, on_snapshot_callback, on_order_callback, on_trade_callback, after_trading_callback, finalize_callback) {
        /* 日线合成快照的原有回放入口。 */
        if (message.rows() == 0) {
            throw "DSL 构造的回测 msg 表为空"
        }
        engine = create_backtest_engine(
            name, config, initialize_callback, before_trading_callback,
            on_bar_callback, on_snapshot_callback, on_order_callback,
            on_trade_callback, after_trading_callback, finalize_callback
        )
        try {
            Backtest::appendQuotationMsg(engine, message)
            // Flush the last timestamp batch using the snapshot protocol. END
            // is a control message, not a quote and cannot provide liquidity.
            lastRow = imax(message.timestamp)
            endMessage = message[lastRow:(lastRow + 1)]
            update endMessage set symbol="END", timestamp=timestamp+1
            Backtest::appendQuotationMsg(engine, endMessage)
        } catch (error) {
            Backtest::dropBacktestEngine(engine)
            throw error
        }
        return engine
    }
    """,
    dependencies=(CREATE_BACKTEST_ENGINE,),
)
