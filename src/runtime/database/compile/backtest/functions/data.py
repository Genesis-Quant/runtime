"""定义回测回调读取昨日截面和历史数据的工具函数。"""

from runtime.database.compile import DolphinDBFunction


GET_HISTORY_DATA = DolphinDBFunction(
    module="backtest",
    definition="""
    def getHistoryData(context, msg, filter=true) {
        /*
        返回严格早于当前 onSnapshot 消息日期的 DSL 数据。

        filter=true 读取 filters 后的数据，false 读取 filters 前的数据。
        两张结果表由 run_backtest 在当前 DolphinDB 会话中生成；msg 只用于确定
        当前回调日期。合成快照字段使用 timestamp。
        */
        source = objByName(
            iif(
                filter,
                "coreBacktestFilteredData",
                "coreBacktestComputedData"
            )
        )
        current_date = date(msg.timestamp[0])
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

HISTORY = DolphinDBFunction(
    module="backtest",
    definition="""
    def history(context, msg, count, codes=NULL, fields=NULL, filter=true) {
        /*
        返回当前消息日期以前最近 count 个实际截面的 DSL 数据。

        time 和 code 始终保留；fields 只控制其余数据列。count 按不同 time
        截面计数，不按自然日或单证券行数计数。
        */
        normalizedCount = int(count)
        if (
            isNull(count) ||
            double(normalizedCount) != double(count) ||
            normalizedCount <= 0
        ) {
            throw "count 必须是正整数"
        }
        source = objByName(
            iif(
                filter,
                "coreBacktestFilteredData",
                "coreBacktestComputedData"
            )
        )
        currentDate = date(msg.timestamp[0])
        if (!all(isNull(codes))) {
            requestedCodes = string(codes)
            selectedTimes = exec time
            from (
                select distinct time
                from source
                where date(time) < currentDate,
                    string(code) in requestedCodes
            )
            order by time desc
            limit normalizedCount
            result = select *
            from source
            where time in selectedTimes,
                string(code) in requestedCodes
        } else {
            selectedTimes = exec time
            from (
                select distinct time
                from source
                where date(time) < currentDate
            )
            order by time desc
            limit normalizedCount
            result = select *
            from source
            where time in selectedTimes
        }
        if (result.rows() > 0) {
            result.sortBy!(`time`code)
        }

        if (all(isNull(fields))) return result
        requestedFields = array(STRING, 0)
        for (field in string(fields)) {
            if (
                !(field in ["time", "code"]) &&
                !(field in requestedFields)
            ) requestedFields.append!(field)
        }
        outputColumns = array(STRING, 0)
        outputColumns.append!(["time", "code"])
        outputColumns.append!(requestedFields)
        missingColumns = outputColumns[
            !(outputColumns in columnNames(result))
        ]
        if (size(missingColumns) > 0) {
            throw "fields 包含不存在的列：" + concat(missingColumns, ",")
        }
        return table(result[symbol(outputColumns)])
    }
    """,
)

CURRENT_SNAPSHOT = DolphinDBFunction(
    module="backtest",
    definition="""
    def current_snapshot(msg, codes=NULL) {
        /* 返回当前 message 中指定证券的快照；codes 为空时返回完整快照。 */
        if (all(isNull(codes))) return msg
        return msg[string(msg.symbol) in string(codes)]
    }
    """,
)

CAN_TRADE = DolphinDBFunction(
    module="backtest",
    definition="""
    def can_trade(msg, stockCode, direction=0) {
        /*
        根据当前快照判断是否存在有效可撮合盘口。

        direction=0 只检查证券和最新价；1 检查买入盘口；3 检查卖出盘口。
        账户资金、可卖持仓和插件风控不属于本函数范围。
        */
        normalizedDirection = int(direction)
        if (!(normalizedDirection in [0, 1, 3])) {
            throw "direction 只能是 0、1 或 3"
        }
        messageIndex = find(string(msg.symbol), string(stockCode))
        if (messageIndex >= msg.rows()) return false

        lastPrice = double(msg.lastPrice[messageIndex])
        if (isNull(lastPrice) || lastPrice <= 0) return false
        if (normalizedDirection == 0) return true

        if (normalizedDirection == 1) {
            offerPrice = double(msg.offerPrice[0][messageIndex])
            offerQuantity = long(msg.offerQty[0][messageIndex])
            upLimitPrice = double(msg.upLimitPrice[messageIndex])
            return !isNull(offerPrice) && offerPrice > 0 &&
                !isNull(offerQuantity) && offerQuantity > 0 &&
                !isNull(upLimitPrice) && offerPrice <= upLimitPrice
        }

        bidPrice = double(msg.bidPrice[0][messageIndex])
        bidQuantity = long(msg.bidQty[0][messageIndex])
        downLimitPrice = double(msg.downLimitPrice[messageIndex])
        return !isNull(bidPrice) && bidPrice > 0 &&
            !isNull(bidQuantity) && bidQuantity > 0 &&
            !isNull(downLimitPrice) && bidPrice >= downLimitPrice
    }
    """,
)
