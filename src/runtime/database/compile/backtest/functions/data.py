"""定义回测回调读取昨日截面和历史数据的工具函数。"""

from runtime.database.compile import DolphinDBFunction


GET_INDUSTRY = DolphinDBFunction(
    module="backtest",
    definition="""
    def getIndustry() {
        /* 返回与 Factor 研究同源、使用 XSHG/XSHE 代码的行业字典。 */
        return objByName("coreBacktestCodeToIndustry")
    }
    """,
)


GET_TRADE_DATES = DolphinDBFunction(
    module="backtest",
    definition="""
    def getTradeDates() {
        /* 返回当前回测实际回放的有序交易日期。 */
        return date(objByName("coreBacktestTradeDates"))
    }
    """,
)


GET_HISTORY_DATA = DolphinDBFunction(
    module="backtest",
    definition="""
    def getHistoryData(context, msg, filter=true, start=NULL, end=NULL) {
        /*
        返回严格早于当前 onSnapshot 消息日期的 DSL 数据。

        filter=true 读取 filters 后的数据，false 读取 filters 前的数据。
        两张结果表由 run_backtest 在当前 DolphinDB 会话中生成；msg 只用于确定
        当前回调日期。start 和 end 是可选闭区间边界，不会放宽严格历史边界。
        合成快照字段使用 timestamp。
        */
        source = objByName(
            iif(
                filter,
                "coreBacktestFilteredData",
                "coreBacktestComputedData"
            )
        )
        current_date = date(msg.timestamp[0])
        if (form(start) != 0) {
            throw "start 必须是 DATE 兼容的标量或 NULL"
        }
        if (form(end) != 0) {
            throw "end 必须是 DATE 兼容的标量或 NULL"
        }
        hasStart = !isNull(start)
        hasEnd = !isNull(end)
        normalizedStart = date()
        normalizedEnd = date()
        if (hasStart) {
            normalizedStart = date(start)
            if (isNull(normalizedStart)) {
                throw "start 必须是 DATE 兼容的标量或 NULL"
            }
        }
        if (hasEnd) {
            normalizedEnd = date(end)
            if (isNull(normalizedEnd)) {
                throw "end 必须是 DATE 兼容的标量或 NULL"
            }
        }
        if (hasStart && hasEnd) {
            if (normalizedStart > normalizedEnd) {
                throw "start 不能晚于 end"
            }
            return select *
            from source
            where date(time) < current_date,
                  date(time) >= normalizedStart,
                  date(time) <= normalizedEnd
        }
        if (hasStart) {
            return select *
            from source
            where date(time) < current_date,
                  date(time) >= normalizedStart
        }
        if (hasEnd) {
            return select *
            from source
            where date(time) < current_date,
                  date(time) <= normalizedEnd
        }
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
