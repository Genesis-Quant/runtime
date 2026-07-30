"""定义把未筛选行情转换为 Backtest 日频消息。"""

from core.database.compile import DolphinDBFunction

BUILD_BACKTEST_MESSAGE = DolphinDBFunction(
    module="backtest",
    definition="""
    def build_backtest_message(market_data, adj) {
        /*
        从完整股票范围的未筛选行情构造 Backtest 插件日频消息。

        msg 仅包含插件所需的行情字段，不包含策略 DSL 因子和派生列。
        原始因子 vol、up_limit、down_limit 和 pre_close 会在 select 时转换为
        插件列名；缺少任一必需行情字段的行会被删除。code 和 time 会转换为
        symbol 和 tradeTime。adj 为 hfq 或 qfq 时使用 adj_factor 复权价格。
        */
        if (!isNull(adj) && !(adj in ["hfq", "qfq"])) {
            throw "adj 只能是 hfq、qfq 或 NULL"
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

        message = select
            code,
            time,
            open,
            low,
            high,
            close,
            vol as volume,
            up_limit as upLimitPrice,
            down_limit as downLimitPrice,
            pre_close as prevClosePrice
        from market_data

        for (column in `open`low`high`close`upLimitPrice`downLimitPrice`prevClosePrice) {
            values = double(message[column])
            if (!isNull(adj)) values = values * adjustment
            replaceColumn!(message, column, values)
        }
        valid_rows = take(true, message.rows())
        for (column in `open`low`high`close`volume`upLimitPrice`downLimitPrice`prevClosePrice) {
            valid_rows = valid_rows && !isNull(message[column])
        }
        message = message[valid_rows]
        rename!(message, `code`time, `symbol`tradeTime)
        replaceColumn!(
            message,
            `symbol,
            symbol(
                strReplace(
                    strReplace(string(message.symbol), ".SZ", ".XSHE"),
                    ".SH",
                    ".XSHG"
                )
            )
        )
        replaceColumn!(
            message,
            `tradeTime,
            temporalAdd(timestamp(message.tradeTime), 15, "h")
        )
        replaceColumn!(message, `volume, long(message.volume))
        message.sortBy!(`tradeTime`symbol)
        return message
    }
    """,
)
