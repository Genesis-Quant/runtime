"""定义回测策略参数访问函数。"""

from runtime.database.compile import DolphinDBFunction


GET_PARAMS = DolphinDBFunction(
    module="backtest",
    definition="""
    def getParams() {
        /* 返回 run_backtest 上传的只读策略参数字典。 */
        return objByName("coreBacktestParams")
    }
    """,
)
