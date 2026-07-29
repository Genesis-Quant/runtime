"""定义回测回调读取昨日截面和历史数据的工具函数。"""

from core.database.compile import DolphinDBFunction


GET_HISTORY_DATA = DolphinDBFunction(
    module="backtest",
    definition="""
    def getHistoryData(context, msg, filter=true) {
        /*
        返回严格早于当前 onBar 消息日期的 DSL 数据。

        filter=true 读取 filters 后的数据，false 读取 filters 前的数据。
        两张结果表由 run_backtest 写入回测 context；msg 只用于确定当前回调
        日期。
        */
        source = context[
            iif(
                filter,
                "coreBacktestFilteredFactorData",
                "coreBacktestUnfilteredFactorData"
            )
        ]
        current_date = date(msg.tradeTime[0])
        return select *
        from source
        where date(time) < current_date
    }
    """,
)

GET_LAST_DATA = DolphinDBFunction(
    module="backtest",
    definition="""
    def getLastData(context, msg, filter=true) {
        // 返回严格早于当前消息日期的最后一个实际存在的 DSL 截面。
        history = getHistoryData(context, msg, filter)
        if (history.rows() == 0) return history
        last_time = max(history.time)
        return select *
        from history
        where time == last_time
    }
    """,
    dependencies=(GET_HISTORY_DATA,),
)
