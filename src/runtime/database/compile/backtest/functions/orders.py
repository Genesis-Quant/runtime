"""定义按目标持仓和目标市值下单的回测工具函数。"""

from runtime.database.compile import DolphinDBFunction

from .data import CAN_TRADE
from .portfolio import GET_AVAILABLE_CASH, GET_POSITIONS, GET_TOTAL_EQUITY


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

ORDER_TARGET_PERCENT = DolphinDBFunction(
    module="backtest",
    definition="""
    def order_target_percent(mutable context, msg, stockCode, targetPercent, orderLabel="order_target_percent") {
        /* 将指定证券调整到当前组合总权益的目标比例。 */
        normalizedPercent = double(targetPercent)
        if (
            isNull(normalizedPercent) ||
            isNanInf(normalizedPercent) ||
            normalizedPercent < 0 ||
            normalizedPercent > 1
        ) {
            throw "targetPercent 必须是 [0, 1] 内的有限数值"
        }
        return order_target_value(
            context,
            msg,
            stockCode,
            get_total_equity(context) * normalizedPercent,
            orderLabel
        )
    }
    """,
    dependencies=(ORDER_TARGET_VALUE, GET_TOTAL_EQUITY),
)

ORDER_TARGET_PORTFOLIO = DolphinDBFunction(
    module="backtest",
    definition="""
    def order_target_portfolio(mutable context, msg, targetWeights, orderLabel="order_target_portfolio") {
        /*
        按目标权重字典批量调整股票组合，未出现在字典中的现有持仓目标为零。

        函数先提交减仓，再按实时可用现金提交加仓；当前快照不可交易的证券会被
        跳过。存在延迟或未成交订单时，应在后续快照再次调用以继续向目标收敛。
        */
        if (form(targetWeights) != form(dict(STRING, ANY))) {
            throw "targetWeights 必须是代码到权重的字典"
        }
        targetCodes = string(targetWeights.keys())
        weights = double(targetWeights.values())
        if (countNanInf(weights, true) > 0 || any(weights < 0)) {
            throw "targetWeights 的权重必须是非负有限数值"
        }
        if (sum(weights) > 1.0 + 1e-10) {
            throw "targetWeights 的权重总和不能超过 1"
        }
        for (stockCode in targetCodes) {
            if (!endsWith(stockCode, ".XSHG") && !endsWith(stockCode, ".XSHE")) {
                throw "targetWeights 代码必须使用 XSHG/XSHE 格式"
            }
        }

        positions = get_positions(context)
        allCodes = array(STRING, 0)
        allCodes.append!(targetCodes)
        if (positions.rows() > 0) {
            allCodes.append!(string(positions.symbol))
        }
        allCodes = distinct(allCodes)
        totalEquity = get_total_equity(context)
        orderIds = array(LONG, 0)
        config = Backtest::getConfig(context.engine)
        commission = double(config["commission"])
        minimumFeeEnabled = bool(
            config["enableMinimumPerTransactionFee"]
        )

        // 先处理清仓和减仓，避免用尚未释放的资金计算后续买单。
        for (stockCode in allCodes) {
            if (!can_trade(msg, stockCode, 3)) continue
            currentPosition = Backtest::getPosition(
                context.engine,
                stockCode
            )
            currentAmount = long(nullFill(
                currentPosition.longPosition.sum(),
                0
            ))
            if (currentAmount <= 0) continue
            messageIndex = find(string(msg.symbol), stockCode)
            lastPrice = double(msg.lastPrice[messageIndex])
            targetWeight = iif(
                stockCode in targetCodes,
                double(targetWeights[stockCode]),
                0.0
            )
            targetValue = totalEquity * targetWeight
            if (targetValue >= double(currentAmount) * lastPrice) continue
            orderId = order_target_value(
                context,
                msg,
                stockCode,
                targetValue,
                orderLabel
            )
            if (!isNull(orderId)) orderIds.append!(long(orderId))
        }

        // 卖单在当前盘口成交后重新读取现金；资金不足时只提交可负担的整手数量。
        for (stockCode in targetCodes) {
            if (!can_trade(msg, stockCode, 1)) continue
            messageIndex = find(string(msg.symbol), stockCode)
            lastPrice = double(msg.lastPrice[messageIndex])
            offerPrice = double(msg.offerPrice[0][messageIndex])
            currentPosition = Backtest::getPosition(
                context.engine,
                stockCode
            )
            currentAmount = long(nullFill(
                currentPosition.longPosition.sum(),
                0
            ))
            targetAmount = long(floor(
                totalEquity * double(targetWeights[stockCode]) /
                lastPrice /
                100.0
            )) * 100l
            requiredAmount = targetAmount - currentAmount
            if (requiredAmount <= 0) continue

            availableCash = get_available_cash(context)
            cashValueLimit = availableCash / (1.0 + commission)
            if (minimumFeeEnabled) {
                cashValueLimit = min(
                    cashValueLimit,
                    max(availableCash - 5.0, 0.0)
                )
            }
            affordableAmount = long(floor(
                cashValueLimit /
                offerPrice /
                100.0
            )) * 100l
            submittedAmount = min(requiredAmount, affordableAmount)
            if (submittedAmount <= 0) continue
            orderId = order_target(
                context,
                msg,
                stockCode,
                currentAmount + submittedAmount,
                orderLabel
            )
            if (!isNull(orderId)) orderIds.append!(long(orderId))
        }
        return orderIds
    }
    """,
    dependencies=(
        CAN_TRADE,
        GET_AVAILABLE_CASH,
        GET_POSITIONS,
        GET_TOTAL_EQUITY,
        ORDER_TARGET_VALUE,
    ),
)
