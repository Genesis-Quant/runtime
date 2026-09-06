"""定义创建并运行 DolphinDB Backtest 引擎的入口函数。"""

from runtime.database.compile import DolphinDBFunction

RUN_BACKTEST = DolphinDBFunction(
    module="backtest",
    definition="""
    def run_backtest(name, mutable config, message, initialize_callback, before_trading_callback, on_bar_callback, on_snapshot_callback, on_order_callback, on_trade_callback, after_trading_callback, finalize_callback) {
        /*
        使用给定配置、完整消息表和全部生命周期回调创建并运行 Backtest 引擎。

        函数先规范插件配置，随后使用全部必填生命周期回调创建引擎、
        追加行情消息并发送快照 END 消息。合成快照按同一时间戳整批触发 onSnapshot；策略通过
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

        engine = Backtest::createBacktestEngine(
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
)
