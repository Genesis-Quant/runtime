# DolphinDB Backtest 股票日频插件说明

本文只说明 DolphinDB Backtest 插件的股票日频模式，不涉及外部查询系统或其他
封装。

文中的代码和输出全部来自同一次真实运行：

```text
DolphinDB Server:                2.00.18 2026.02.07 LINUX x86_64
Backtest Plugin:                 2.00.18.11
MatchingEngineSimulator Plugin:  2.00.18.11
引擎名称:                         backtest_doc_daily
股票:                             000001.XSHE
行情:                             2025-01-02 至 2025-01-10，共 7 行
最终状态:                         END
lastErrMsg:                       空
```

本次运行的完整流程是：

```text
加载插件
  -> 定义 config 和 8 个回调
  -> 构造日频行情表
  -> createBacktestEngine
  -> appendQuotationMsg
  -> appendEndMarker
  -> 获取回测结果
  -> dropBacktestEngine
```

完整可运行脚本位于第 15 节。

## 1. 加载插件

Backtest 依赖 MatchingEngineSimulator，因此先加载撮合插件：

```dos
loadPlugin("MatchingEngineSimulator")
loadPlugin("Backtest")
```

加载后检查版本：

```dos
select plugin, version
from getLoadedPlugins()
where plugin in ["Backtest", "MatchingEngineSimulator"]
order by plugin
```

实测输出：

```text
plugin                    version
Backtest                  2.00.18.11
MatchingEngineSimulator   2.00.18.11
```

## 2. 创建引擎

本文使用 `createBacktestEngine`：

```dos
Backtest::createBacktestEngine(
    name,
    config,
    [securityReference],
    initialize,
    beforeTrading,
    onTickOrOnBar,
    onSnapshot,
    onOrder,
    onTrade,
    afterTrading,
    finalize
)
```

### 2.1 初始化参数

| 位置 | 参数 | 含义 | 本次传入 |
| ---: | --- | --- | --- |
| 1 | `name` | 引擎名称，同一用户下应唯一 | `"backtest_doc_daily"` |
| 2 | `config` | 引擎配置字典 | 第 3 节的 `config` |
| 3 | `securityReference` | 证券基础信息表；股票模式可省略 | 留空 |
| 4 | `initialize` | 策略初始化回调 | `docInitialize` |
| 5 | `beforeTrading` | 每日盘前回调 | `docBeforeTrading` |
| 6 | `onTickOrOnBar` | 逐笔或 Bar 回调；日频传 `onBar` | `docOnBar` |
| 7 | `onSnapshot` | 快照回调 | `docOnSnapshot` |
| 8 | `onOrder` | 委托状态回调 | `docOnOrder` |
| 9 | `onTrade` | 成交回调 | `docOnTrade` |
| 10 | `afterTrading` | 每日盘后回调 | `docAfterTrading` |
| 11 | `finalize` | 回测结束回调 | `docFinalize` |

股票模式省略 `securityReference` 时，第三个位置为空，因此代码中会出现连续两个
逗号。

### 2.2 实测代码

```dos
engine = Backtest::createBacktestEngine(
    "backtest_doc_daily",
    config,
    ,
    docInitialize,
    docBeforeTrading,
    docOnBar,
    docOnSnapshot,
    docOnOrder,
    docOnTrade,
    docAfterTrading,
    docFinalize
)
```

### 2.3 实测结果

引擎创建后，以下调用均成功：

```dos
Backtest::getConfig(engine)
Backtest::appendQuotationMsg(engine, quotation)
Backtest::appendEndMarker(engine)
Backtest::getBacktestEngineStat(engine)
```

最终状态：

```text
name                status  lastErrMsg  snapshotTimestamp
backtest_doc_daily  END                 2025-01-10 15:00:00
```

`createBacktestEngine` 是旧版位置参数接口。新版插件另有
`createBacktester(name, config, eventCallbacks, ...)`，但本文没有混用两套接口。

## 3. `config` 配置

### 3.1 实测代码

```dos
config = dict(STRING, ANY)
config["startDate"] = 2025.01.02
config["endDate"] = 2025.01.10
config["strategyGroup"] = "stock"
config["cash"] = double(2000000)
config["commission"] = double(0.0003)
config["tax"] = double(0.001)
config["dataType"] = int(4)
config["msgAsTable"] = true
config["matchingMode"] = int(2)
```

### 3.2 参数说明

| 配置项 | 类型 | 本次值 | 含义 |
| --- | --- | ---: | --- |
| `startDate` | `DATE` | `2025.01.02` | 回测开始日期 |
| `endDate` | `DATE` | `2025.01.10` | 回测结束日期 |
| `strategyGroup` | `STRING`/`SYMBOL` | `"stock"` | 股票回测 |
| `cash` | `DOUBLE` | `2,000,000` | 初始资金 |
| `commission` | `DOUBLE` | `0.0003` | 手续费率 |
| `tax` | `DOUBLE` | `0.001` | 股票印花税率 |
| `dataType` | `INT` | `4` | 日频行情 |
| `msgAsTable` | `BOOL` | `true` | 行情回调中的 `msg` 使用表 |
| `matchingMode` | `INT` | `2` | 日频订单按开盘价撮合 |

日频 `matchingMode`：

| 值 | 撮合方式 |
| ---: | --- |
| `1` | 按收盘价撮合 |
| `2` | 按开盘价撮合 |
| `3` | 按委托价格成交 |

### 3.3 实测结果

```dos
Backtest::getConfig(engine)
```

返回：

```python
{
    "cash": 2000000.0,
    "commission": 0.0003,
    "dataType": 4,
    "endDate": "2025-01-10",
    "matchingMode": 2,
    "msgAsTable": True,
    "startDate": "2025-01-02",
    "strategyGroup": "stock",
    "tax": 0.001,
}
```

插件还支持 `benchmark`、`latency`、`stockDividend`、
`setLastDayPosition` 等配置。它们未参加本次运行，本文不为其伪造实测结果，具体
约束见文末官方配置文档。

## 4. 日频行情表

### 4.1 标准字段

本次成功输入的标准字段如下：

| 字段 | 类型 | 含义 | 第一行实测值 |
| --- | --- | --- | --- |
| `symbol` | `SYMBOL` | 股票代码；沪市 `.XSHG`，深市 `.XSHE` | `000001.XSHE` |
| `tradeTime` | `TIMESTAMP` | 行情时间 | `2025-01-02 15:00:00` |
| `open` | `DOUBLE` | 开盘价 | `11.73` |
| `low` | `DOUBLE` | 最低价 | `11.39` |
| `high` | `DOUBLE` | 最高价 | `11.77` |
| `close` | `DOUBLE` | 收盘价 | `11.43` |
| `volume` | `LONG` | 成交量 | `181959699` |
| `amount` | `DOUBLE` | 成交额 | `2102923.078` |
| `upLimitPrice` | `DOUBLE` | 涨停价 | `12.87` |
| `downLimitPrice` | `DOUBLE` | 跌停价 | `10.53` |
| `prevClosePrice` | `DOUBLE` | 前收盘价 | `11.70` |

`symbol` 必须放在第一列。

### 4.2 扩展字段规则

插件支持两类扩展字段：

| 类别 | 列名 | 类型 |
| --- | --- | --- |
| 普通标量扩展字段 | 任意 | `INT`、`DOUBLE` 或 `STRING` |
| 数组向量扩展字段 | 必须为 `signal` | `DOUBLE[]` |

这四种形式全部是可选的。插件不要求行情表必须存在 `signal`。

本次使用了四个有明确示例含义的扩展字段：

| 字段 | 类型 | 示例含义 | 第一行实测值 |
| --- | --- | --- | --- |
| `positionTarget` | `INT` | 示例目标持仓标记，1 表示买入 | `1` |
| `factorScore` | `DOUBLE` | 示例因子分数 | `0.82` |
| `marketRegime` | `STRING` | 示例市场状态 | `"bull"` |
| `signal` | `DOUBLE[]` | 示例二维数值信号 | `[0.10, 0.20]` |

`positionTarget`、`factorScore` 和 `marketRegime` 是示例策略自定义列，不是插件
保留字段；可以换成其他名字。只有数组向量列的名字固定为 `signal`。

### 4.3 实测构造代码

```dos
signalColumn = array(DOUBLE[], 0, 7).append!([
    0.10 0.20,
    0.20 0.30,
    0.30 0.40,
    0.40 0.50,
    0.50 0.60,
    0.60 0.70,
    0.70 0.80
])

tradeDates = timestamp([
    2025.01.02,
    2025.01.03,
    2025.01.06,
    2025.01.07,
    2025.01.08,
    2025.01.09,
    2025.01.10
])

quotation = table(
    symbol(take("000001.XSHE", 7)) as symbol,
    temporalAdd(tradeDates, 15, "h") as tradeTime,
    double([11.73, 11.44, 11.38, 11.42, 11.50, 11.50, 11.40]) as open,
    double([11.39, 11.36, 11.22, 11.37, 11.40, 11.35, 11.28]) as low,
    double([11.77, 11.54, 11.48, 11.53, 11.63, 11.50, 11.46]) as high,
    double([11.43, 11.38, 11.44, 11.51, 11.50, 11.40, 11.30]) as close,
    long([
        181959699, 115468044, 108553630, 74786288,
        106238601, 75148330, 79813351
    ]) as volume,
    double([
        2102923.078, 1320520.978, 1234305.778, 858329.049,
        1223598.997, 857836.086, 905005.041
    ]) as amount,
    double([12.87, 12.57, 12.52, 12.58, 12.66, 12.65, 12.54]) as upLimitPrice,
    double([10.53, 10.29, 10.24, 10.30, 10.36, 10.35, 10.26]) as downLimitPrice,
    double([11.70, 11.43, 11.38, 11.44, 11.51, 11.50, 11.40]) as prevClosePrice,
    int([1, 1, 0, 0, 1, 1, 0]) as positionTarget,
    double([0.82, 0.76, -0.15, -0.23, 0.61, 0.55, -0.31]) as factorScore,
    ["bull", "bull", "neutral", "bear", "bull", "neutral", "bear"] as marketRegime,
    signalColumn as signal
)
```

### 4.4 实测列类型

```dos
schema(quotation).colDefs
```

关键输出：

```text
name             typeString
symbol           SYMBOL
tradeTime        TIMESTAMP
open             DOUBLE
low              DOUBLE
high             DOUBLE
close            DOUBLE
volume           LONG
amount           DOUBLE
upLimitPrice     DOUBLE
downLimitPrice   DOUBLE
prevClosePrice   DOUBLE
positionTarget   INT
factorScore      DOUBLE
marketRegime     STRING
signal           DOUBLE[]
```

该表成功传入引擎，最终状态为 `END`。

## 5. 回调参数和调用总览

### 5.1 公共参数

`context` 是所有回调共享的可变字典。插件维护的主要键：

| 键 | 含义 |
| --- | --- |
| `context.engine` | 当前引擎句柄 |
| `context.tradeDate` | 当前交易日 |
| `context.tradeTime` | 当前行情时间 |
| `context.barTime` | 快照合成 Bar 时的 Bar 时间 |

策略可以向 `context` 添加自己的状态。函数签名中的 `mutable` 表示允许回调修改
这个共享字典。

本次回调参数实测类型：

```text
onBar.msg        IN-MEMORY TABLE
onBar.indicator  VOID
onOrder.orders   ANY VECTOR
onTrade.trades   ANY VECTOR
```

`indicator` 为 `VOID`，因为本次没有调用 `subscribeIndicator`。

### 5.2 实测调用次数

```text
initialize:     1
beforeTrading:  7
onBar:          6
onSnapshot:     0
onOrder:        2
onTrade:        1
afterTrading:   7
finalize:       1
```

## 6. `initialize`

签名：

```dos
def initialize(mutable context)
```

用途：创建引擎时初始化策略共享状态或订阅指标。此时没有处理任何行情。

### 实测代码

```dos
def docInitialize(mutable context) {
    context["initializeCount"] = 1
    context["beforeTradingCount"] = 0
    context["onBarCount"] = 0
    context["onSnapshotCount"] = 0
    context["onOrderCount"] = 0
    context["onTradeCount"] = 0
    context["afterTradingCount"] = 0
    context["finalizeCount"] = 0
    context["submitted"] = false
    context["beforeDates"] = array(DATE, 0)
    context["barTimes"] = array(TIMESTAMP, 0)
    context["afterDates"] = array(DATE, 0)
    context["trace"] = array(STRING, 0)
    context["trace"].append!("initialize")
}
```

### 实测结果

```text
initializeCount = 1
tradeDate        = 2025-01-02
tradeTime        = 1970-01-01 00:00:00.000
```

`tradeTime` 是初始值，因为行情尚未送入引擎。

## 7. `beforeTrading`

签名：

```dos
def beforeTrading(mutable context)
```

用途：每个交易日开始时执行盘前准备。该回调不接收行情 `msg`。

### 实测代码

```dos
def docBeforeTrading(mutable context) {
    context["beforeTradingCount"] += 1
    context["beforeDates"].append!(take(context.tradeDate, 1))
    context["trace"].append!("beforeTrading:" + string(context.tradeDate))
}
```

### 实测结果

```text
beforeTradingCount = 7
beforeDates =
2025-01-02, 2025-01-03, 2025-01-06, 2025-01-07,
2025-01-08, 2025-01-09, 2025-01-10
```

## 8. `onBar`

签名：

```dos
def onBar(mutable context, msg, indicator)
```

用途：处理分钟或日频 Bar。本文设置了 `msgAsTable=true`，因此 `msg` 是表。

### 8.1 实测代码

```dos
def docOnBar(mutable context, msg, indicator) {
    context["onBarCount"] += 1
    context["barTimes"].append!(take(context.tradeTime, 1))
    context["trace"].append!("onBar:" + string(context.tradeTime))

    if (context["onBarCount"] == 1) {
        context["msgType"] = typestr(msg)
        context["indicatorType"] = typestr(indicator)
        context["firstSymbol"] = string(msg.symbol[0])
        context["firstTradeTime"] = msg.tradeTime[0]
        context["firstOpen"] = msg.open[0]
        context["firstClose"] = msg.close[0]
        context["firstPositionTarget"] = msg.positionTarget[0]
        context["firstFactorScore"] = msg.factorScore[0]
        context["firstMarketRegime"] = msg.marketRegime[0]
        context["firstSignal"] = msg.signal.row(0)
        context["signalType"] = typestr(msg.signal)
    }

    if (!context["submitted"] && msg.positionTarget[0] == 1) {
        context["submitted"] = true
        Backtest::submitOrder(
            context.engine,
            (
                msg.symbol[0],
                context.tradeTime,
                0,
                msg.close[0],
                long(100),
                1
            ),
            "doc-buy"
        )
    }
}
```

### 8.2 首次回调实测值

```text
typestr(msg)                = IN-MEMORY TABLE
typestr(indicator)          = VOID
msg.symbol[0]               = 000001.XSHE
msg.tradeTime[0]            = 2025-01-02 15:00:00
msg.open[0]                 = 11.73
msg.close[0]                = 11.43
msg.positionTarget[0]       = 1
msg.factorScore[0]          = 0.82
msg.marketRegime[0]         = bull
msg.signal.row(0)           = [0.10, 0.20]
typestr(msg.signal)         = FAST DOUBLE[] VECTOR
```

标准字段以及 `INT`、`DOUBLE`、`STRING`、`DOUBLE[]` 四种扩展字段均成功进入
`onBar`。

### 8.3 调用时间实测

7 行输入只触发 6 次 `onBar`：

```text
2025-01-02 15:00:00
2025-01-03 15:00:00
2025-01-06 15:00:00
2025-01-07 15:00:00
2025-01-08 15:00:00
2025-01-09 15:00:00
```

2025-01-10 触发了 `beforeTrading` 和 `afterTrading`，但没有触发 `onBar`。这是
Backtest 2.00.18.11 对本次整表追加的实际表现。若最后一个策略日也必须执行
`onBar`，输入中还需要包含下一个有效时间点，再发送结束标记。

## 9. `onSnapshot`

签名：

```dos
def onSnapshot(mutable context, msg, indicator)
```

用途：处理快照行情。本文是 `dataType=4` 日频回测，因此不触发该回调。

### 实测代码

```dos
def docOnSnapshot(mutable context, msg, indicator) {
    context["onSnapshotCount"] += 1
    context["trace"].append!("onSnapshot")
}
```

### 实测结果

```text
onSnapshotCount = 0
```

旧版位置参数接口仍然保留该位置，所以本次传入了一个可观测但不会触发的函数。

## 10. `onOrder`

签名：

```dos
def onOrder(mutable context, orders)
```

用途：每次委托状态发生变化时接收订单回报。同一订单可能调用多次。

### 10.1 实测代码

```dos
def docOnOrder(mutable context, orders) {
    context["onOrderCount"] += 1
    context["orderType"] = typestr(orders)
    context["lastOrder"] = orders
    context["trace"].append!("onOrder")
}
```

### 10.2 字段说明

| 字段 | 含义 |
| --- | --- |
| `orderId` | 委托 ID |
| `symbol` | 标的代码 |
| `timestamp` | 下单时间 |
| `qty` | 委托数量 |
| `price` | 委托价格 |
| `status` | 委托状态 |
| `direction` | 买卖方向 |
| `tradeQty` | 累计成交数量 |
| `tradeValue` | 累计成交金额 |
| `label` | 订单标签 |
| `updateTime` | 状态更新时间 |

状态值：

| `status` | 含义 |
| ---: | --- |
| `4` | 已报 |
| `0` | 部分成交 |
| `1` | 全部成交 |
| `2` | 撤单成功 |
| `-1` | 审批拒绝 |
| `-2` | 撤单拒绝 |

方向值：

| `direction` | 含义 |
| ---: | --- |
| `1` | 买开 |
| `2` | 卖开 |
| `3` | 卖平 |
| `4` | 买平 |

### 10.3 实测结果

```text
typestr(orders) = ANY VECTOR
onOrderCount    = 2
状态序列         = 4（已报） -> 1（全部成交）
```

最后一次回调内容：

```python
[{
    "orderId": 1,
    "symbol": "000001.XSHE",
    "timestamp": "2025-01-02 15:00:00",
    "direction": 1,
    "price": 11.43,
    "qty": 100,
    "status": 1,
    "tradeQty": 100,
    "tradeValue": 1173.0,
    "updateTime": "2025-01-02 15:00:00",
    "label": "doc-buy",
}]
```

## 11. `onTrade`

签名：

```dos
def onTrade(mutable context, trades)
```

用途：实际发生成交时接收成交回报。

### 11.1 实测代码

```dos
def docOnTrade(mutable context, trades) {
    context["onTradeCount"] += 1
    context["tradeType"] = typestr(trades)
    context["lastTrade"] = trades
    context["trace"].append!("onTrade")
}
```

### 11.2 字段说明

| 字段 | 含义 |
| --- | --- |
| `orderId` | 对应的委托 ID |
| `symbol` | 标的代码 |
| `tradeTime` | 成交时间 |
| `direction` | 买卖方向 |
| `orderPrice` | 原委托价格 |
| `tradePrice` | 本次成交价格 |
| `tradeQty` | 本次成交数量 |
| `tradeValue` | 本次成交金额 |
| `totalVolume` | 累计成交数量 |
| `totalValue` | 累计成交金额 |
| `totalFee` | 累计费用 |
| `label` | 订单标签 |

### 11.3 实测结果

```text
typestr(trades) = ANY VECTOR
onTradeCount    = 1
```

成交回调内容：

```python
[{
    "orderId": 1,
    "symbol": "000001.XSHE",
    "tradeTime": "2025-01-02 15:00:00",
    "direction": 1,
    "orderPrice": 11.43,
    "tradePrice": 11.73,
    "tradeQty": 100,
    "tradeValue": 1173.0,
    "totalVolume": 100,
    "totalValue": 1173.0,
    "totalFee": 0.3519,
    "label": "doc-buy",
}]
```

## 12. `afterTrading`

签名：

```dos
def afterTrading(mutable context)
```

用途：每个交易日结束后汇总成交、持仓或资金。该回调不接收行情 `msg`。

### 实测代码

```dos
def docAfterTrading(mutable context) {
    context["afterTradingCount"] += 1
    context["afterDates"].append!(take(context.tradeDate, 1))
    context["trace"].append!("afterTrading:" + string(context.tradeDate))
}
```

### 实测结果

```text
afterTradingCount = 7
afterDates =
2025-01-02, 2025-01-03, 2025-01-06, 2025-01-07,
2025-01-08, 2025-01-09, 2025-01-10
```

## 13. `finalize`

签名：

```dos
def finalize(mutable context)
```

用途：收到结束标记后，在回测结束前进行一次最终汇总。

### 实测代码

```dos
def docFinalize(mutable context) {
    context["finalizeCount"] += 1
    context["trace"].append!("finalize")
}
```

### 实测结果

```text
finalizeCount = 1
事件追踪最后一项 = finalize
```

## 14. 下单、撮合和实际回调顺序

### 14.1 `submitOrder`

股票普通订单元组：

```text
(股票代码, 下单时间, 订单类型, 订单价格, 订单数量, 买卖方向)
```

本次实测代码：

```dos
Backtest::submitOrder(
    context.engine,
    (
        msg.symbol[0],
        context.tradeTime,
        0,
        msg.close[0],
        long(100),
        1
    ),
    "doc-buy"
)
```

本次值：

| 元素 | 值 | 含义 |
| --- | ---: | --- |
| 股票代码 | `000001.XSHE` | 平安银行 |
| 下单时间 | `2025-01-02 15:00:00` | 当前 Bar 时间 |
| 订单类型 | `0` | 市价单 |
| 订单价格 | `11.43` | 订单携带的价格字段 |
| 订单数量 | `100` | 100 股 |
| 买卖方向 | `1` | 买开 |

### 14.2 实际撮合

```text
当日 open       = 11.73
当日 close      = 11.43
订单价格字段     = 11.43
matchingMode    = 2
实际成交价       = 11.73
实际成交数量     = 100
手续费           = 0.3519
```

这验证了日频 `matchingMode=2` 使用开盘价撮合。

插件没有自动把日频 `onBar` 下单推迟到下一交易日：回调已经能读取当日
`close=11.43`，订单却在同日按 `open=11.73` 成交。如果业务规定“日终数据只能
用于下一交易日”，必须在送入插件前或策略执行层明确处理时序，不能假设插件自动
延迟。

### 14.3 实际回调顺序

第一个交易日：

```text
initialize
beforeTrading:2025-01-02
onBar:2025-01-02 15:00:00
onOrder
onOrder
onTrade
afterTrading:2025-01-02
```

最后一个交易日：

```text
beforeTrading:2025-01-10
afterTrading:2025-01-10
finalize
```

## 15. 完整可运行脚本

以下脚本就是本页所有实测结果对应的 DolphinDB 代码。运行前应确保两个插件已经
加载。

```dos
engineName = "backtest_doc_daily"

config = dict(STRING, ANY)
config["startDate"] = 2025.01.02
config["endDate"] = 2025.01.10
config["strategyGroup"] = "stock"
config["cash"] = double(2000000)
config["commission"] = double(0.0003)
config["tax"] = double(0.001)
config["dataType"] = int(4)
config["msgAsTable"] = true
config["matchingMode"] = int(2)

def docInitialize(mutable context) {
    context["initializeCount"] = 1
    context["beforeTradingCount"] = 0
    context["onBarCount"] = 0
    context["onSnapshotCount"] = 0
    context["onOrderCount"] = 0
    context["onTradeCount"] = 0
    context["afterTradingCount"] = 0
    context["finalizeCount"] = 0
    context["submitted"] = false
    context["beforeDates"] = array(DATE, 0)
    context["barTimes"] = array(TIMESTAMP, 0)
    context["afterDates"] = array(DATE, 0)
    context["trace"] = array(STRING, 0)
    context["trace"].append!("initialize")
}

def docBeforeTrading(mutable context) {
    context["beforeTradingCount"] += 1
    context["beforeDates"].append!(take(context.tradeDate, 1))
    context["trace"].append!("beforeTrading:" + string(context.tradeDate))
}

def docOnBar(mutable context, msg, indicator) {
    context["onBarCount"] += 1
    context["barTimes"].append!(take(context.tradeTime, 1))
    context["trace"].append!("onBar:" + string(context.tradeTime))

    if (context["onBarCount"] == 1) {
        context["msgType"] = typestr(msg)
        context["indicatorType"] = typestr(indicator)
        context["firstSymbol"] = string(msg.symbol[0])
        context["firstTradeTime"] = msg.tradeTime[0]
        context["firstOpen"] = msg.open[0]
        context["firstClose"] = msg.close[0]
        context["firstPositionTarget"] = msg.positionTarget[0]
        context["firstFactorScore"] = msg.factorScore[0]
        context["firstMarketRegime"] = msg.marketRegime[0]
        context["firstSignal"] = msg.signal.row(0)
        context["signalType"] = typestr(msg.signal)
    }

    if (!context["submitted"] && msg.positionTarget[0] == 1) {
        context["submitted"] = true
        Backtest::submitOrder(
            context.engine,
            (
                msg.symbol[0],
                context.tradeTime,
                0,
                msg.close[0],
                long(100),
                1
            ),
            "doc-buy"
        )
    }
}

def docOnSnapshot(mutable context, msg, indicator) {
    context["onSnapshotCount"] += 1
    context["trace"].append!("onSnapshot")
}

def docOnOrder(mutable context, orders) {
    context["onOrderCount"] += 1
    context["orderType"] = typestr(orders)
    context["lastOrder"] = orders
    context["trace"].append!("onOrder")
}

def docOnTrade(mutable context, trades) {
    context["onTradeCount"] += 1
    context["tradeType"] = typestr(trades)
    context["lastTrade"] = trades
    context["trace"].append!("onTrade")
}

def docAfterTrading(mutable context) {
    context["afterTradingCount"] += 1
    context["afterDates"].append!(take(context.tradeDate, 1))
    context["trace"].append!("afterTrading:" + string(context.tradeDate))
}

def docFinalize(mutable context) {
    context["finalizeCount"] += 1
    context["trace"].append!("finalize")
}

signalColumn = array(DOUBLE[], 0, 7).append!([
    0.10 0.20,
    0.20 0.30,
    0.30 0.40,
    0.40 0.50,
    0.50 0.60,
    0.60 0.70,
    0.70 0.80
])

tradeDates = timestamp([
    2025.01.02,
    2025.01.03,
    2025.01.06,
    2025.01.07,
    2025.01.08,
    2025.01.09,
    2025.01.10
])

quotation = table(
    symbol(take("000001.XSHE", 7)) as symbol,
    temporalAdd(tradeDates, 15, "h") as tradeTime,
    double([11.73, 11.44, 11.38, 11.42, 11.50, 11.50, 11.40]) as open,
    double([11.39, 11.36, 11.22, 11.37, 11.40, 11.35, 11.28]) as low,
    double([11.77, 11.54, 11.48, 11.53, 11.63, 11.50, 11.46]) as high,
    double([11.43, 11.38, 11.44, 11.51, 11.50, 11.40, 11.30]) as close,
    long([
        181959699, 115468044, 108553630, 74786288,
        106238601, 75148330, 79813351
    ]) as volume,
    double([
        2102923.078, 1320520.978, 1234305.778, 858329.049,
        1223598.997, 857836.086, 905005.041
    ]) as amount,
    double([12.87, 12.57, 12.52, 12.58, 12.66, 12.65, 12.54]) as upLimitPrice,
    double([10.53, 10.29, 10.24, 10.30, 10.36, 10.35, 10.26]) as downLimitPrice,
    double([11.70, 11.43, 11.38, 11.44, 11.51, 11.50, 11.40]) as prevClosePrice,
    int([1, 1, 0, 0, 1, 1, 0]) as positionTarget,
    double([0.82, 0.76, -0.15, -0.23, 0.61, 0.55, -0.31]) as factorScore,
    ["bull", "bull", "neutral", "bear", "bull", "neutral", "bear"] as marketRegime,
    signalColumn as signal
)

engine = Backtest::createBacktestEngine(
    engineName,
    config,
    ,
    docInitialize,
    docBeforeTrading,
    docOnBar,
    docOnSnapshot,
    docOnOrder,
    docOnTrade,
    docAfterTrading,
    docFinalize
)

Backtest::appendQuotationMsg(engine, quotation)
Backtest::appendEndMarker(engine)

contextResult = Backtest::getContextDict(engine)
tradeDetails = Backtest::getTradeDetails(engine)
dailyPositions = Backtest::getDailyPosition(engine)
dailyPortfolios = Backtest::getDailyTotalPortfolios(engine)
returnSummary = Backtest::getReturnSummary(engine)
dailyTradingStatistics = Backtest::getDailyTradingStatistics(engine)
engineStat = Backtest::getBacktestEngineStat(engine)

Backtest::dropBacktestEngine(engine)
```

本次完整脚本的结果摘要：

```text
引擎状态:                 END
委托状态行数:              2
成交次数:                  1
每日持仓行数:              7
每日权益行数:              7
每日交易统计行数:           1
最终持仓:                  100
最终总权益:                1999956.6481
累计收益率:                -0.00002167595
```

## 16. 结果接口

本次完整脚本实际调用并成功返回：

| 接口 | 本次结果 |
| --- | --- |
| `getContextDict` | 包含所有回调计数、实测参数和策略状态 |
| `getTradeDetails` | 2 行：已报、全部成交 |
| `getDailyPosition` | 7 行每日持仓 |
| `getDailyTotalPortfolios` | 7 行每日权益 |
| `getReturnSummary` | 1 行收益汇总 |
| `getDailyTradingStatistics` | 1 行 2025-01-02 买开统计 |
| `getBacktestEngineStat` | 状态 `END`，错误为空 |

成交明细实测：

```text
orderId  orderStatus  orderPrice  tradePrice  tradeQty
1        4            11.43       0.00        0
1        1            11.43       11.73       100
```

每日持仓最后一行：

```text
symbol       tradeDate   longPosition  longPositionAvgPrice  closePrice
000001.XSHE  2025-01-10  100           11.73                 11.30
```

每日权益最后一行：

```text
tradeDate   cash          totalMarketValue  totalEquity   totalFee
2025-01-10  1998826.6481  1130.0            1999956.6481  0.3519
```

## 17. 官方参考

- [Backtest 插件总览与回调说明](https://docs.dolphindb.cn/zh/plugins/backtest.html)
- [Backtest 接口说明](https://docs.dolphindb.cn/zh/plugins/backtest/interface_description.html)
- [股票回测配置与行情结构](https://docs.dolphindb.cn/zh/plugins/backtest/stock.html)
