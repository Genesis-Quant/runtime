# Core

Core 提供统一因子数据写入、DolphinDB 原生因子 DSL 查询和日频策略回测能力。

## 安装

```powershell
uv add arena-runtime
```

项目要求 Python 3.12，并需要可访问的 DolphinDB 服务。使用数据更新 Worker 或
查询全市场代码时，还需要在环境变量或 `.env` 中配置 `TUSHARE_TOKEN`。

DolphinDB 单节点使用 `DOLPHIN_HOST` 和 `DOLPHIN_PORT`。集群连接额外设置逗号
分隔的 `DOLPHIN_HIGH_AVAILABILITY_SITES`。内网模式下 Runtime 使用 Python API 的 Session
高可用；通过公网地址访问集群时，服务端需为数据/计算节点配置 `publicName`，并设置
`DOLPHIN_USE_PUBLIC_NAME=true`。由于 Python API 的 Session 不支持 `usePublicName`，普通
Session 会按配置的公网入口依次尝试建立初始连接，写入连接池则通过 `publicName` 使用
集群高可用，避免把服务端内网 site 与公网入口错误比较。候选节点只应包含数据节点和
计算节点，不包含 controller 或 agent。

业务执行与增量更新必须使用不同账号。`DOLPHIN_RUNTIME_USERNAME` 和
`DOLPHIN_RUNTIME_PASSWORD` 用于查询、因子分析、回测、参数调优及 MCP，只需数据库读取和
脚本执行权限；`DOLPHIN_WORKER_USERNAME` 和 `DOLPHIN_WORKER_PASSWORD` 仅用于 Worker
读取增量水位、初始化库表、补充分区及写入数据。

## Python API

查询、因子分析、回测、回测参数调优和敏感性分析函数从顶层包直接导出：

```python
from runtime import (
    analyze_backtest_sensitivity,
    analyze_factors,
    execute_query,
    optimize_backtest,
    run_backtest,
)

with execute_query(query_request) as query_result:
    factor_data = query_result.data
    session = query_result.session

with analyze_factors(
    query_request,
    factor_columns=["close"],
    return_columns=["pct_chg"],
    n_groups=5,
) as factor_result:
    processed = factor_result.processed_data
    information_coefficient = factor_result.information_coefficient
    group_returns = factor_result.group_returns

with run_backtest(
    dataset_query,
    callbacks,
    adj="qfq",
) as backtest_result:
    summary = backtest_result.return_summary
    portfolios = backtest_result.daily_portfolios

with optimize_backtest(**optimization_request) as optimization_result:
    random_search_paths = optimization_result.table("random_search")

with analyze_backtest_sensitivity(**sensitivity_request) as sensitivity_result:
    case_metrics = sensitivity_result.results
```

也可以从对应应用包显式导入：

```python
from runtime.apps.query import FactorQuery, execute_query
from runtime.apps.factor import FactorAnalysisParameters, analyze_factors
from runtime.apps.backtest import BacktestParameters, run_backtest
from runtime.apps.optimization import OptimizationParameters, optimize_backtest
from runtime.apps.sensitivity import SensitivityParameters, analyze_backtest_sensitivity
```

`execute_query`、`analyze_factors`、`run_backtest`、`optimize_backtest` 和
`analyze_backtest_sensitivity` 分别返回查询、因子分析、回测、参数调优和敏感性分析结果对象。
结果保存在各自的 DolphinDB session 中；访问数据成员时才会执行对应 DOS
代码并下载结果。五种结果都提供 `session` 属性、`download()`
和 `close()`，退出
`with` 时会自动关闭 session。API 成功返回后，即使 session 是调用方传入的，
也由结果对象接管其关闭操作。

Runtime 自行创建 Session 时，Query 的总使用时间上限为 5 分钟，Backtest（含提交前回调编译）
为 1 小时，参数调优为 6 小时；MCP DolphinScript 测试由 Backend 限制为 10 分钟。
截止时间从连接成功开始计算，到期会主动关闭底层连接。调用方显式传入 Session 时，其生命周期和
超时仍由调用方负责。

`run_backtest` 的 `adj` 默认为 `None`；传入 `"qfq"` 或 `"hfq"` 时会查询
`adj_factor`，并对回测消息中的价格字段执行前复权或后复权。
`source_ref` 和 `message_ref` 是当前 DolphinDB session 中的查询结果变量名：
变量已存在时直接复用，不存在时查询并把结果保存到该变量。回测默认使用
`coreBacktestSourceData` 和 `coreBacktestMessage`。

## 命令行

安装后使用 `core-manage`：

```powershell
core-manage --help
core-manage database compile --upload --output-dir output
core-manage apps query --input-file query.json --output-dir output/query --output data --cloud false
core-manage apps factor --input-file factor.json --output-dir output/factor --output processed_data information_coefficient group_returns --cloud false
core-manage apps backtest --input-file backtest.json --output-dir output/backtest --output daily_portfolios return_summary --cloud false
core-manage apps optimization --input-file optimization.json --output-dir output/optimization --cloud false
core-manage apps sensitivity --input-file sensitivity.json --output-dir output/sensitivity --cloud false
core-manage apps backtest --input-file backtest.json --output-dir jobs/backtest-1 --output daily_portfolios --cloud true
core-manage workers --list-workers
core-manage workers daily adj-factor --start-date 2025-01-01
core-manage workers daily --job-id incremental:1 --output-dir output/incremental --selected-workers daily,limit
core-manage messages send --input-file output/incremental/message.json --channel console
core-manage database compile --output-dir output
```

在源码仓库中也可以调用同一套命令：

```powershell
uv run python manage.py workers --list-workers
uv run python manage.py database compile
```

默认由 `analyze_factors` 完成 MAD 去极值、标准化、市值与行业中性化及
等数量分组。设置 `preprocess=False` 时直接分析 DSL 输出，不加载行业元数据；
此时 DSL 必须为每个分析因子同时输出 `<factor>_group` 列，例如可以使用
`unary.robust_zscore` 和 `unary.qcut` 手动完成标准化及分组。

```python
with analyze_factors(
    manually_preprocessed_query,
    factor_columns=["close_processed"],
    return_columns=["pct_chg"],
    n_groups=5,
    preprocess=False,
) as factor_result:
    information_coefficient = factor_result.information_coefficient
```

`apps query`、`apps factor` 和 `apps backtest` 都使用必填的
`--input-file`、`--output-dir` 和 `--output` 为必填项。直接运行时
`--cloud true|false` 默认读取 `ARENA_SHARED_CLOUD`；工作流执行时由调用方显式传入，
不会使用该默认值。
`--output` 后可以指定一个或多个结果属性；未指定会报错，未选中的结果属性不会
被访问、下载或计算。
输入文件必须是 UTF-8 JSON 对象，只包含应用的非敏感运行参数。输出目录、
输出项和存储方式均由命令行参数指定。

`database compile --upload` 会先重新生成 `common`、`query`、`factor` 和 `backtest`
四个 DOS 模块，再使用增量更新账号逐一连接 `DOLPHIN_HOST:DOLPHIN_PORT` 及
`DOLPHIN_HIGH_AVAILABILITY_SITES` 中的全部节点，写入各节点的 `moduleDir`，回读校验完整
内容并执行 `use` 验证模块可以导入。任一节点失败时命令失败，Backend 启动也会停止，避免集群
同时运行不同版本的模块。

`apps optimization` 不接收 `--output`：它会为请求中每个 `algorithms`
条目保存同名 Parquet，例如 `random_search.parquet`。输入是独立、扁平的
`OptimizationParameters`：直接包含回测使用的 `dataset_query`、`callbacks`、`params`
等字段，并增加调优字段。`parameter_space` 只能选择 `params` 中已经定义的数值参数；
每个值都是有限候选列表。`start_date` 是第一段样本外区间的起点，
`end_date` 是最后一段样本外区间的终点，`lookback_period` 和 `holding_period`
支持 `D/W/M/Y`，例如 `6M` 和 `2W`。`repetitions` 控制每种算法的随机初始点次数，
`evaluation_budget` 控制每个训练窗口最多评价多少个候选组合。

参数调优只创建一个 DolphinDB session。Runtime 先把最早训练日到最后持有日作为
完整区间执行一次 `codes_query` 和 `dataset_query`，随后只生成一次
`coreBacktestComputedData`、`coreBacktestFilteredData`、`coreBacktestData` 和
`coreBacktestMessage`。每次训练或样本外回测仅从同一个消息表截取当前窗口，替换
`coreBacktestParams` 并创建独立引擎，不会重新查询因子或重新合成快照。训练目标固定为
`sharpeRatio`；每个算法的 Parquet 包含全部重复、滚动窗口、随机初始参数、最终参数、
训练 Sharpe、窗口净值和拼接后的 `path_net_value`。每个样本外窗口由独立引擎运行，
窗口净值按收益率首尾拼接，不跨窗口继承持仓。

`apps sensitivity` 同样不接收 `--output`。它在一个 session 中只准备一次完整区间数据和消息表，
随后依次执行 `cases` 中的手续费或策略参数组合，并保存一份 `results.parquet`。每行记录一个组合的
参数、手续费、成功或失败状态、错误和指标；即使全部组合失败也会保留该文件，调用方必须按行检查
`status`，不能只依据工作流成功状态判断每个组合是否有效。

查询输入文件示例：

```json
{
  "dataset_query": {
    "start_date": "2025-01-01",
    "end_date": "2025-01-31",
    "codes": ["000001.SZ"],
    "factors": ["close"]
  }
}
```

查询可选输出为 `source_data`、`computed_data`、`filtered_data` 和 `data`；
其中 `data` 写入 `<output_dir>/query.parquet`。本地模式下，相对
`--output-dir` 以当前工作目录为基准，目标目录不存在时会自动创建。

因子分析输入参考 [factor.json](examples/factor.json)，可选输出：

- `factor_processed.parquet`
- `factor_information_coefficients.parquet`
- `factor_group_returns.parquet`

访问结果属性时才会计算 IC 或分组收益。后两张表按 `time` 横向拼接全部因子，
其余列以因子名为前缀，例如 `close_pct_chg_ic`。

回测输入文件示例：

```json
{
  "dataset_query": {
    "start_date": "2025-01-01",
    "end_date": "2025-01-31",
    "lookback": "60D",
    "codes": ["000001.SZ"],
    "factors": ["close"]
  },
  "callbacks": {
    "initialize": "def initialize(mutable context) { return NULL }",
    "beforeTrading": "def beforeTrading(mutable context) { return NULL }",
    "onBar": "def onBar(mutable context, message, indicator) { return NULL }",
    "onSnapshot": "def onSnapshot(mutable context, message, indicator) { return NULL }",
    "onOrder": "def onOrder(mutable context, event) { return NULL }",
    "onTrade": "def onTrade(mutable context, event) { return NULL }",
    "afterTrading": "def afterTrading(mutable context) { return NULL }",
    "finalize": "def finalize(mutable context) { return NULL }"
  },
  "config": {
    "cash": 100000
  }
}
```

回测可选输出为 `trade_details`、`daily_positions`、`daily_portfolios`、
`return_summary`、`daily_trading_statistics` 和 `engine_stat`。`utils` 是在生命周期回调
注册前原样执行的 DolphinDB 脚本，不限制脚本内容。`callbacks` 必须完整提供上述 8 个
固定生命周期回调且定义不能为空。`codes_query` 为空时，`dataset_query.codes` 必须提供
至少一个股票代码。日线会转换为每天 09:30 和 15:00 的单档合成快照，盘口数量使用
十亿股/份的安全盘口容量表示近似无限流动性，避免插件内部整数运算溢出；策略在
`onSnapshot` 中通过 `message.timestamp`、`message.lastPrice` 和单档盘口下单；框架固定
使用 `dataType=1`、`matchingMode=1`、`matchingRatio=0` 和
`orderBookMatchingRatio=1`。`config.syntheticSpread` 可设置单档合成盘口的完整相对
价差，买一和卖一各偏离 `lastPrice` 一半。回测输入还支持
`codes_query`、`adj`、`name`、`annual_trading_days`、`risk_free_rate`、
`source_ref` 和 `message_ref`。命令执行结束后自动关闭 DolphinDB session。

`dataset_query` 和 `codes_query` 的输入仍使用 `.SH/.SZ`；数据查询完成后，回测专用的
source、computed、filtered 和 data 表会统一转换为 `.XSHG/.XSHE`。因此生命周期回调
中的 `history.code`、`message.symbol`、持仓和订单使用完全相同的证券代码，不需要策略
自行转换。

`onSnapshot` 可调用 `backtest::order_target(context, message, stockCode,
targetAmount, orderLabel)` 将持仓调整到精确目标股数，或调用
`backtest::order_target_value(context, message, stockCode, targetValue,
orderLabel)` 调整到目标市值。后者使用当前快照 `lastPrice` 换算目标股数并按 100 股
整手调整；目标市值为 0 时会卖出不足一手的剩余持仓。两者分别以卖一价买入、
买一价卖出。

指定 `--cloud true` 后不会在 `--output-dir` 落本地文件。此时
`--output-dir` 表示 bucket 内的相对对象路径，例如 `jobs/backtest-1`，
结果将上传为
`s3://<OBJECT_STORAGE_BUCKET>/jobs/backtest-1/<文件名>.parquet`。
对象路径不能是绝对路径，不能包含 `.` 或 `..` 路径段。

对象存储使用 S3 兼容协议，连接参数通过环境变量或 `.env` 提供：

```dotenv
OBJECT_STORAGE_ENDPOINT_URL=http://127.0.0.1:9000
OBJECT_STORAGE_ACCESS_KEY_ID=your-access-key
OBJECT_STORAGE_SECRET_ACCESS_KEY=your-secret-key
OBJECT_STORAGE_BUCKET=arena
OBJECT_STORAGE_REGION=us-east-1
OBJECT_STORAGE_ADDRESSING_STYLE=auto
OBJECT_STORAGE_ROOT_FOLDER=arena-runtime
```

前四项为必填项；`OBJECT_STORAGE_ADDRESSING_STYLE` 可设置为 `auto`、`path`
或 `virtual`。`OBJECT_STORAGE_ROOT_FOLDER` 设置 bucket 内的统一根文件夹，
可使用 `team/arena-runtime` 形式的多级相对路径；设置为空表示直接使用
bucket 根目录。配置为 `arena-runtime` 时，云端结果路径为
`s3://<bucket>/arena-runtime/<output_dir>/<文件名>.parquet`。
对象存储参数统一在 `D:\Arena\.env` 中配置。
当前腾讯云南京区域配置使用 `https://cos.ap-nanjing.myqcloud.com` 和
`virtual` addressing style。
DolphinDB 凭据和 Tushare Token 等敏感信息同样不写入输入 JSON。

仓库中的 [query.json](examples/query.json)、[factor.json](examples/factor.json)
和 [backtest.json](examples/backtest.json) 可以直接作为输入文件示例。

增量更新 Worker 可通过 `--job-id`、`--output-dir` 和 `--selected-workers`
接收工作流上下文。未指定 `--output-dir` 时不生成结构化结果；指定后，每个 Task
原子写入固定的 `<worker>.json`，并在 DolphinScheduler 重试时保留 `attempts`
历史。未被 `--selected-workers` 选中的 Task 返回成功退出码，同时写入
`SKIPPED` 结果，便于工作流保持并行结构并统一汇总。

消息功能与具体工作流解耦。`runtime.messaging` 定义文本、图片和渠道专用消息块，
负责 JSON 读写与 Channel 分发；`runtime.workers.report` 只负责把 Worker 结果构造成
结构化消息。`console` 是默认 Channel，只打印可处理的普通消息块，并忽略其他
Channel 的专用格式。新增发送渠道时，在 `runtime.messaging.channels` 中实现
`MessageChannel` 并注册到 `CHANNEL_TYPES`，无需修改 Worker 或汇总逻辑。

`database compile` 命令会重新生成 `common.dos`、`query.dos`、
`factor.dos` 和 `backtest.dos`。

## 构建与发布

```powershell
uv build
uv publish
```
