"""定义按目标持仓和目标市值下单的回测工具函数。"""

from runtime.database.compile import DolphinDBFunction


ORDER_TARGET = DolphinDBFunction(
    module="backtest",
    definition="""
    def order_target(mutable context, msg, stockCode, targetAmount, orderLabel="order_target") {
        /*
        将指定证券的多头持仓调整到目标股数。

        targetAmount 是精确目标股数，允许卖出不足一手的剩余持仓。买单使用
        卖一价，卖单使用买一价，确保限价单能够参与盘口撮合。
        */
        messageIndex = find(symbol(string(msg.symbol)), stockCode)
        if (messageIndex >= msg.rows()) throw "股票不在当前快照中"
        if (isNull(targetAmount) || targetAmount < 0) throw "targetAmount 必须是非负数"
        normalizedTargetAmount = long(targetAmount)
        if (double(normalizedTargetAmount) != double(targetAmount)) throw "targetAmount 必须是整数"

        currentPosition = Backtest::getPosition(context.engine, msg.symbol[messageIndex])
        currentAmount = long(nullFill(currentPosition.longPosition.sum(), 0))
        difference = normalizedTargetAmount - currentAmount
        quantity = long(abs(difference))
        if (quantity == 0) return NULL

        if (difference > 0) {
            orderPrice = double(msg.offerPrice[0][messageIndex])
            direction = 1
        } else {
            orderPrice = double(msg.bidPrice[0][messageIndex])
            direction = 3
        }
        if (isNull(orderPrice) || orderPrice <= 0) throw "快照一档价格无效"
        return Backtest::submitOrder(
            context.engine,
            (msg.symbol[messageIndex], msg.timestamp[0], 5, orderPrice, quantity, direction),
            orderLabel
        )
    }
    """,
)

ORDER_TARGET_VALUE = DolphinDBFunction(
    module="backtest",
    definition="""
    def order_target_value(mutable context, msg, stockCode, targetValue, orderLabel="order_target_value") {
        /* 使用当前快照 lastPrice 将目标市值换算成目标股数并下单。 */
        messageIndex = find(symbol(string(msg.symbol)), stockCode)
        if (messageIndex >= msg.rows()) throw "股票不在当前快照中"
        if (isNull(targetValue) || targetValue < 0) throw "targetValue 必须是非负数"
        lotSize = 100l
        lastPrice = double(msg.lastPrice[messageIndex])
        if (isNull(lastPrice) || lastPrice <= 0) throw "快照 lastPrice 无效"

        currentPosition = Backtest::getPosition(context.engine, msg.symbol[messageIndex])
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
