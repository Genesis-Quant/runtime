"""定义中国股票回测使用的交易日历函数。"""

from runtime.database.compile import DolphinDBFunction


GET_TRADING_DAYS = DolphinDBFunction(
    module="backtest",
    definition="""
    def get_trading_days(startDate, endDate, exchange="XSHG") {
        /* 返回闭区间内指定交易所的交易日。 */
        normalizedExchange = upper(string(exchange))
        if (!(normalizedExchange in ["XSHG", "XSHE"])) {
            throw "exchange 只能是 XSHG 或 XSHE"
        }
        normalizedStart = date(startDate)
        normalizedEnd = date(endDate)
        if (isNull(normalizedStart) || isNull(normalizedEnd)) {
            throw "startDate 和 endDate 不能为空"
        }
        if (normalizedStart > normalizedEnd) {
            throw "startDate 不能晚于 endDate"
        }
        return getMarketCalendar(
            normalizedExchange,
            normalizedStart,
            normalizedEnd
        )
    }
    """,
)

IS_TRADING_DAY = DolphinDBFunction(
    module="backtest",
    definition="""
    def is_trading_day(targetDate, exchange="XSHG") {
        /* 判断日期是否为指定交易所的交易日。 */
        normalizedDate = date(targetDate)
        if (isNull(normalizedDate)) throw "targetDate 不能为空"
        return size(get_trading_days(
            normalizedDate,
            normalizedDate,
            exchange
        )) == 1
    }
    """,
    dependencies=(GET_TRADING_DAYS,),
)

SHIFT_TRADING_DAY = DolphinDBFunction(
    module="backtest",
    definition="""
    def shift_trading_day(targetDate, offset, exchange="XSHG") {
        /* 按交易所日历偏移日期；offset 可以为正、负或零。 */
        normalizedExchange = upper(string(exchange))
        if (!(normalizedExchange in ["XSHG", "XSHE"])) {
            throw "exchange 只能是 XSHG 或 XSHE"
        }
        normalizedDate = date(targetDate)
        if (isNull(normalizedDate)) throw "targetDate 不能为空"
        normalizedOffset = int(offset)
        if (isNull(offset) || double(normalizedOffset) != double(offset)) {
            throw "offset 必须是整数"
        }
        if (normalizedOffset == 0) {
            if (!is_trading_day(normalizedDate, normalizedExchange)) {
                throw "offset 为 0 时 targetDate 必须是交易日"
            }
            return normalizedDate
        }
        return temporalAdd(
            normalizedDate,
            normalizedOffset,
            normalizedExchange
        )
    }
    """,
    dependencies=(IS_TRADING_DAY,),
)

PREVIOUS_TRADING_DAY = DolphinDBFunction(
    module="backtest",
    definition="""
    def previous_trading_day(targetDate, count=1, exchange="XSHG") {
        /* 返回 targetDate 之前第 count 个交易日。 */
        normalizedCount = int(count)
        if (
            isNull(count) ||
            double(normalizedCount) != double(count) ||
            normalizedCount <= 0
        ) {
            throw "count 必须是正整数"
        }
        return shift_trading_day(
            date(targetDate),
            -normalizedCount,
            exchange
        )
    }
    """,
    dependencies=(SHIFT_TRADING_DAY,),
)

NEXT_TRADING_DAY = DolphinDBFunction(
    module="backtest",
    definition="""
    def next_trading_day(targetDate, count=1, exchange="XSHG") {
        /* 返回 targetDate 之后第 count 个交易日。 */
        normalizedCount = int(count)
        if (
            isNull(count) ||
            double(normalizedCount) != double(count) ||
            normalizedCount <= 0
        ) {
            throw "count 必须是正整数"
        }
        return shift_trading_day(
            date(targetDate),
            normalizedCount,
            exchange
        )
    }
    """,
    dependencies=(SHIFT_TRADING_DAY,),
)
