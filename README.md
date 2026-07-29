# Core

Core 提供统一因子数据写入、DolphinDB 原生因子 DSL 查询和日频策略回测能力。

## 安装

```powershell
uv add arena-core
```

项目要求 Python 3.12，并需要可访问的 DolphinDB 服务。使用数据更新 Worker 或
查询全市场代码时，还需要在环境变量或 `.env` 中配置 `TUSHARE_TOKEN`。

## Python API

查询和回测函数从顶层包直接导出：

```python
from core import execute_query, run_backtest

with execute_query(query_request) as query_result:
    factor_data = query_result.data
    session = query_result.session

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
from core.apps.backtest import BacktestResult, run_backtest
```

`execute_query` 返回 `core.QueryResult`，`run_backtest` 返回
`core.BacktestResult`。结果保存在各自的 DolphinDB session 中；访问数据成员时
才会执行对应 DOS 代码并下载结果。两种结果都提供 `session` 属性、`download()`
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
core-manage apps query --start-date 2025-01-01 --end-date 2025-01-31 --codes '[\"000001.SZ\"]' --factors '[\"close\"]'
core-manage apps backtest --start-date 2025-01-01 --end-date 2025-01-31 --codes CODES_JSON --factors FACTORS_JSON --callbacks CALLBACKS_JSON
core-manage workers --list-workers
core-manage workers daily adj-factor --start-date 2025-01-01
core-manage database compile --output-dir output
```

在源码仓库中也可以调用同一套命令：

```powershell
uv run python manage.py workers --list-workers
uv run python manage.py database compile
```

`apps query` 和 `apps backtest` 的日期、回看周期、复权方式、名称和数值使用
普通命令行参数；股票代码、因子、派生因子、过滤器、回调、工具函数、
选股查询和回测配置等数组或对象使用 JSON 字符串。命令当前只负责执行，
不会下载或打印结果；执行结束后自动关闭 DolphinDB session。

`database compile` 命令会重新生成 `common.dos`、`query.dos` 和
`backtest.dos`。

## 构建与发布

```powershell
uv build
uv publish
```
