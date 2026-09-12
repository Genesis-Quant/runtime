"""定义按目标持仓和目标市值下单的回测工具函数。"""

from runtime.database.compile import DolphinDBFunction


ORDER_QUOTE = DolphinDBFunction(
    module="backtest",
    definition="""
    def backtest_order_quote(msg, stockCode) {
        if ("coreBacktestSnapshotState" in objs(true).name) {
            state = objByName("coreBacktestSnapshotState")
            if (state["enabled"]) {
                quotes = state["quotes"]
                key = symbol([string(stockCode)])[0]
                if (!(key in quotes)) throw "该证券当日尚无可用快照："+string(stockCode)
                quote = quotes[key]
                if (date(quote[0])!=date(msg.timestamp[0]) || quote[0]>msg.timestamp[0]) {
                    throw "该证券没有当前时刻可见的当日报价："+string(stockCode)
                }
                return quote
            }
        }
        index = find(symbol(string(msg.symbol)), stockCode)
        if (index>=msg.rows()) throw "股票不在当前快照中"
        return [msg.timestamp[index],msg.lastPrice[index],msg.bidPrice[0][index],msg.offerPrice[0][index],msg.bidQty[0][index],msg.offerQty[0][index]]
    }
    """,
)


ORDER_TARGET = DolphinDBFunction(
    module="backtest",
    definition="""
    def order_target(mutable context, msg, stockCode, targetAmount, orderLabel="order_target") {
        /*
        将指定证券的多头持仓调整到目标股数。

        targetAmount 是精确目标股数，允许卖出不足一手的剩余持仓。买单使用
        卖一价，卖单使用买一价，确保限价单能够参与盘口撮合。
        */
        quote = backtest_order_quote(msg, stockCode)
        if (isNull(targetAmount) || targetAmount < 0) throw "targetAmount 必须是非负数"
        normalizedTargetAmount = long(targetAmount)
        if (double(normalizedTargetAmount) != double(targetAmount)) throw "targetAmount 必须是整数"

        currentPosition = Backtest::getPosition(context.engine, stockCode)
        currentAmount = long(nullFill(currentPosition.longPosition.sum(), 0))
        difference = normalizedTargetAmount - currentAmount
        quantity = long(abs(difference))
        if (quantity == 0) return NULL

        if (difference > 0) {
            orderPrice = double(quote[3])
            if (isNull(quote[5]) || quote[5]<=0) throw "快照卖一没有可成交数量："+string(stockCode)
            direction = 1
        } else {
            orderPrice = double(quote[2])
            if (isNull(quote[4]) || quote[4]<=0) throw "快照买一没有可成交数量："+string(stockCode)
            direction = 3
        }
        if (isNull(orderPrice) || orderPrice <= 0) throw "快照一档价格无效"
        return Backtest::submitOrder(
            context.engine,
            (stockCode, msg.timestamp[0], 5, orderPrice, quantity, direction),
            orderLabel
        )
    }
    """,
    dependencies=(ORDER_QUOTE,),
)

ORDER_TARGET_VALUE = DolphinDBFunction(
    module="backtest",
    definition="""
    def order_target_value(mutable context, msg, stockCode, targetValue, orderLabel="order_target_value") {
        /* 使用当前快照 lastPrice 将目标市值换算成目标股数并下单。 */
        quote = backtest_order_quote(msg, stockCode)
        if (isNull(targetValue) || targetValue < 0) throw "targetValue 必须是非负数"
        lotSize = 100l
        lastPrice = double(quote[1])
        if (isNull(lastPrice) || lastPrice <= 0) throw "快照 lastPrice 无效"

        currentPosition = Backtest::getPosition(context.engine, stockCode)
        currentAmount = long(nullFill(currentPosition.longPosition.sum(), 0))
        difference = double(targetValue) / lastPrice - currentAmount
        adjustment = long(floor(abs(difference) / lotSize)) * long(lotSize)
        targetAmount = iif(
            targetValue == 0,
            long(0),
            iif(difference < 0, currentAmount - adjustment, currentAmount + adjustment)
        )
        return order_target(
            context,
            msg,
            stockCode,
            targetAmount,
            orderLabel
        )
    }
    """,
    dependencies=(ORDER_TARGET,),
)
