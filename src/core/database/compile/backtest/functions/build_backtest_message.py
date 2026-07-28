"""定义把未筛选行情转换为 Backtest 日频消息。"""

from core.database.compile import DolphinDBFunction

BUILD_BACKTEST_MESSAGE = DolphinDBFunction(
    module="backtest",
    definition="""
    def build_backtest_message(market_data) {
        /*
        从完整股票范围的未筛选行情构造 Backtest 插件日频消息。

        msg 仅包含插件所需的原始行情字段，不包含 DSL 因子和派生列。
        缺少任一必需行情字段的行会被删除，code 和 time 会转换为插件要求的
        symbol 和 tradeTime。
        */
        message = select
            code,
            time,
            open,
            low,
            high,
            close,
            volume,
            upLimitPrice,
            downLimitPrice,
            prevClosePrice
        from market_data

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
        for (column in `open`low`high`close`upLimitPrice`downLimitPrice`prevClosePrice) {
            replaceColumn!(message, column, double(message[column]))
        }
        message.sortBy!(`tradeTime`symbol)
        return message
    }
    """,
)

__all__ = ["BUILD_BACKTEST_MESSAGE"]
