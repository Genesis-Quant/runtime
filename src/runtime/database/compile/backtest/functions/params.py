"""定义回测策略参数访问函数。"""

from runtime.database.compile import DolphinDBFunction


GET_PARAMS = DolphinDBFunction(
    module="backtest",
    definition="""
    def getParams() {
        return objByName("coreBacktestParams")
    }
    """,
)
