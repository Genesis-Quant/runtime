"""定义回测账户、持仓和挂单的统一读取函数。"""

from runtime.database.compile import DolphinDBFunction


GET_PORTFOLIO = DolphinDBFunction(
    module="backtest",
    definition="""
    def get_portfolio(context) {
        /* 返回股票账户当前权益字典。 */
        return Backtest::getTotalPortfolios(context.engine)
    }
    """,
)

GET_TOTAL_EQUITY = DolphinDBFunction(
    module="backtest",
    definition="""
    def get_total_equity(context) {
        /* 返回股票账户当前总权益。 */
        portfolio = get_portfolio(context)
        if (!("totalEquity" in portfolio.keys())) {
            throw "当前账户权益缺少 totalEquity"
        }
        totalEquities = double(portfolio["totalEquity"])
        if (size(totalEquities) != 1) {
            throw "当前股票账户 totalEquity 数量必须为 1"
        }
        totalEquity = first(totalEquities)
        if (isNull(totalEquity) || totalEquity < 0) {
            throw "当前账户 totalEquity 无效"
        }
        return totalEquity
    }
    """,
    dependencies=(GET_PORTFOLIO,),
)

GET_POSITIONS = DolphinDBFunction(
    module="backtest",
    definition="""
    def get_positions(context) {
        /* 返回股票账户全部当前持仓表。 */
        return Backtest::getPosition(context.engine)
    }
    """,
)

GET_POSITION = DolphinDBFunction(
    module="backtest",
    definition="""
    def get_position(context, stockCode) {
        /* 返回指定证券的当前持仓字典。 */
        return Backtest::getPosition(
            context.engine,
            string(stockCode)
        )
    }
    """,
)

GET_AVAILABLE_CASH = DolphinDBFunction(
    module="backtest",
    definition="""
    def get_available_cash(context) {
        /* 返回股票账户当前可用现金。 */
        return double(Backtest::getAvailableCash(
            context.engine,
            "stock"
        ))
    }
    """,
)

GET_OPEN_ORDERS = DolphinDBFunction(
    module="backtest",
    definition="""
    def get_open_orders(context) {
        /* 返回当前全部未成交订单。 */
        return Backtest::getOpenOrders(context.engine)
    }
    """,
)
