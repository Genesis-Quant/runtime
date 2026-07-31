# Core

Core 提供统一因子数据写入、DolphinDB 原生因子 DSL 查询和日频策略回测能力。

## 安装

```powershell
uv add arena-core
```

项目要求 Python 3.12，并需要可访问的 DolphinDB 服务。使用数据更新 Worker 或
查询全市场代码时，还需要在环境变量或 `.env` 中配置 `TUSHARE_TOKEN`。

## Python API

查询、因子分析和回测函数从顶层包直接导出：

```python
from core import analyze_factors, execute_query, run_backtest

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
    close_ic = factor_result.information_coefficient("close")
    close_group_returns = factor_result.group_returns("close")

with run_backtest(
    dataset_query,
    callbacks,
    adj="qfq",
) as backtest_result:
    summary = backtest_result.return_summary
    portfolios = backtest_result.daily_portfolios
```

也可以从对应应用包显式导入：

```python
from core.apps.query import FactorQuery, QueryResult, execute_query
from core.apps.factor import FactorAnalysisResult, analyze_factors
from core.apps.backtest import BacktestResult, run_backtest
```

`execute_query` 返回 `core.QueryResult`，`analyze_factors` 返回
`core.FactorAnalysisResult`，`run_backtest` 返回 `core.BacktestResult`。
结果保存在各自的 DolphinDB session 中；访问数据成员时才会执行对应 DOS
代码并下载结果。三种结果都提供 `session` 属性、`download()`
和 `close()`，退出
`with` 时会自动关闭 session。API 成功返回后，即使 session 是调用方传入的，
也由结果对象接管其关闭操作。

`run_backtest` 的 `adj` 默认为 `None`；传入 `"qfq"` 或 `"hfq"` 时会查询
`adj_factor`，并对回测消息中的价格字段执行前复权或后复权。
`source_ref` 和 `message_ref` 是当前 DolphinDB session 中的查询结果变量名：
变量已存在时直接复用，不存在时查询并把结果保存到该变量。回测默认使用
`coreBacktestSource` 和 `coreBacktestMessage`。

## 命令行

安装后使用 `core-manage`：

```powershell
core-manage --help
core-manage apps query --input-file query.json
core-manage apps factor --input-file factor.json
core-manage apps backtest --input-file backtest.json
core-manage apps backtest --input-file backtest.json --output-cloud
core-manage workers --list-workers
core-manage workers daily adj-factor --start-date 2025-01-01
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
    close_ic = factor_result.information_coefficient("close_processed")
```

`apps query`、`apps factor` 和 `apps backtest` 都使用必填的
`--input-file`，并支持可选的 `--output-cloud` 开关（默认 `False`）。
输入文件必须是 UTF-8 JSON 对象，包含应用的全部非敏感参数。

查询输入文件示例：

```json
{
  "dataset_query": {
    "start_date": "2025-01-01",
    "end_date": "2025-01-31",
    "codes": ["000001.SZ"],
    "factors": ["close"]
  },
  "output_dir": "output/query"
}
```

本地模式下，相对 `output_dir` 以输入文件所在目录为基准，查询结果固定写入
`<output_dir>/query.parquet`，目标目录不存在时会自动创建。

因子分析输入参考 [factor.json](examples/factor.json)，固定输出：

- `factor_processed.parquet`
- `factor_information_coefficients.parquet`
- `factor_group_returns.parquet`

后两张表使用 `factor` 列区分不同分析因子。

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
    "initialize": "def initialize(mutable context) {}"
  },
  "config": {
    "cash": 100000
  },
  "output_dir": "output/backtest",
  "output": [
    "trade_details",
    "daily_portfolios"
  ]
}
```

`output` 可省略，默认输出 `trade_details.parquet`、
`daily_positions.parquet`、`daily_portfolios.parquet` 和
`daily_trading_statistics.parquet`。回测输入还支持 `utils`、
`codes_query`、`adj`、`name`、`annual_trading_days`、`risk_free_rate`、
`source_ref` 和 `message_ref`。命令执行结束后自动关闭 DolphinDB session。

指定 `--output-cloud` 后不会在 `output_dir` 落本地文件。此时
`output_dir` 表示 bucket 内的相对对象路径，例如 `jobs/backtest-1`，
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

`database compile` 命令会重新生成 `common.dos`、`query.dos`、
`factor.dos` 和 `backtest.dos`。

## 构建与发布

```powershell
uv build
uv publish
```
