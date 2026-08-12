"""定义把日线行情转换为 Backtest 单档合成快照。"""

from runtime.database.compile import DolphinDBFunction

BUILD_BACKTEST_MESSAGE = DolphinDBFunction(
    module="backtest",
    definition="""
    def build_backtest_message(market_data, adj, synthetic_spread=0.0) {
        /*
        从完整股票范围的未筛选日线构造开盘、收盘单档合成快照。

        每个交易日生成 09:30 和 15:00 两条快照，盘口只有一档，买卖价格分别
        使用当日 open 和 close。盘口数量固定为十亿股/份，作为不会触发插件
        整数溢出的近似无限流动性；盘口撮合比例固定为 100%，不使用当天结束后
        才能确定的成交量。
        adj 为 hfq 或 qfq 时使用
        adj_factor 复权价格。synthetic_spread 表示合成买卖盘口的完整相对价差，
        买一和卖一分别位于 lastPrice 的下方和上方一半价差处。
        */
        if (!isNull(adj) && !(adj in ["hfq", "qfq"])) {
            throw "adj 只能是 hfq、qfq 或 NULL"
        }
        if (isNull(synthetic_spread) || synthetic_spread < 0 || synthetic_spread >= 1) {
            throw "synthetic_spread 必须位于 [0, 1)"
        }
        adjustment = take(1.0, market_data.rows())
        if (!isNull(adj)) {
            if (!("adj_factor" in columnNames(market_data))) {
                throw "复权行情缺少 adj_factor"
            }
            adjustment = double(market_data.adj_factor)
            if (adj == "qfq") {
                adjustment = adjustment /
                    contextby(last, adjustment, market_data.code)
            }
        }

        daily = select
            code,
            time,
            open,
            low,
            high,
            close,
            double(
                iif(
                    isNull(up_limit),
                    iif(
                        high > round(pre_close * 1.1, 3),
                        high,
                        round(pre_close * 1.1, 3)
                    ),
                    up_limit
                )
            ) as upLimitPrice,
            double(
                iif(
                    isNull(down_limit),
                    iif(
                        low < round(pre_close * 0.9, 3),
                        low,
                        round(pre_close * 0.9, 3)
                    ),
                    down_limit
                )
            ) as downLimitPrice,
            pre_close as prevClosePrice
        from market_data

        for (column in `open`low`high`close`upLimitPrice`downLimitPrice`prevClosePrice) {
            values = double(daily[column])
            if (!isNull(adj)) values = values * adjustment
            replaceColumn!(daily, column, values)
        }
        valid_rows = take(true, daily.rows())
        for (column in `open`low`high`close`upLimitPrice`downLimitPrice`prevClosePrice) {
            valid_rows = valid_rows && !isNull(daily[column])
        }
        daily = daily[valid_rows]
        if (daily.rows() == 0) throw "无法从日线构造合成快照"

        open_snapshot = select
            code,
            temporalAdd(temporalAdd(timestamp(time), 9, "h"), 30, "m") as timestamp,
            open as lastPrice,
            upLimitPrice,
            downLimitPrice,
            prevClosePrice
        from daily
        close_snapshot = select
            code,
            temporalAdd(timestamp(time), 15, "h") as timestamp,
            close as lastPrice,
            upLimitPrice,
            downLimitPrice,
            prevClosePrice
        from daily
        levels = unionAll(open_snapshot, close_snapshot)
        levels.sortBy!(`timestamp`code)
        ends = int(1..levels.rows())
        unlimited_quantity = take(1000000000l, levels.rows())
        codes = string(levels.code)
        if (any(!(endsWith(codes, ".XSHE") || endsWith(codes, ".XSHG")))) {
            throw "回测证券代码必须使用 XSHG/XSHE 格式"
        }
        message = table(
            symbol(codes) as symbol,
            symbol(iif(endsWith(codes, ".XSHE"), "XSHE", "XSHG")) as symbolSource,
            levels.timestamp as timestamp,
            double(levels.lastPrice) as lastPrice,
            double(levels.upLimitPrice) as upLimitPrice,
            double(levels.downLimitPrice) as downLimitPrice,
            unlimited_quantity as totalBidQty,
            unlimited_quantity as totalOfferQty,
            arrayVector(ends, round(double(levels.lastPrice) * (1.0 - synthetic_spread / 2.0), 3)) as bidPrice,
            arrayVector(ends, unlimited_quantity) as bidQty,
            arrayVector(ends, round(double(levels.lastPrice) * (1.0 + synthetic_spread / 2.0), 3)) as offerPrice,
            arrayVector(ends, unlimited_quantity) as offerQty,
            double(levels.prevClosePrice) as prevClosePrice
        )
        return message
    }
    """,
)
