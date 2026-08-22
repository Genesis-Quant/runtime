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

GET_PARAM = DolphinDBFunction(
    module="backtest",
    definition="""
    def getParam(key) {
        /* 按名称读取一个策略参数；参数不存在时立即报错。 */
        if (form(key) != 0 || !(type(key) in [STRING, SYMBOL])) {
            throw "策略参数 key 必须是标量 STRING 或 SYMBOL"
        }
        parameterKey = string(key)
        if (isNull(parameterKey) || parameterKey == "") {
            throw "策略参数 key 不能为空"
        }
        parameters = getParams()
        if (!(parameterKey in string(parameters.keys()))) {
            throw "策略参数不存在：" + parameterKey
        }
        return parameters[parameterKey]
    }
    """,
    dependencies=(GET_PARAMS,),
)
