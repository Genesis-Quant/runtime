"""实现查询与回测应用命令。"""

import argparse
from collections.abc import Sequence
import json
from typing import Any


def json_object(value: str) -> dict[str, Any]:
    """解析 JSON 对象参数。"""
    try:
        result = json.loads(value)
    except json.JSONDecodeError as error:
        raise argparse.ArgumentTypeError(
            f"不是有效的 JSON：{error.msg}"
        ) from error
    if not isinstance(result, dict):
        raise argparse.ArgumentTypeError("必须是 JSON 对象")
    return result


def json_array(value: str) -> list[Any]:
    """解析 JSON 数组参数。"""
    try:
        result = json.loads(value)
    except json.JSONDecodeError as error:
        raise argparse.ArgumentTypeError(
            f"不是有效的 JSON：{error.msg}"
        ) from error
    if not isinstance(result, list):
        raise argparse.ArgumentTypeError("必须是 JSON 数组")
    return result


def positive_int(value: str) -> int:
    """解析大于零的整数。"""
    result = int(value)
    if result <= 0:
        raise argparse.ArgumentTypeError("必须大于 0")
    return result


def add_query_arguments(parser: argparse.ArgumentParser) -> None:
    """添加 FactorQuery 字段对应的命令行参数。"""
    parser.add_argument(
        "--start-date",
        required=True,
        help="查询闭区间开始日期",
    )
    parser.add_argument(
        "--end-date",
        required=True,
        help="查询闭区间结束日期",
    )
    parser.add_argument(
        "--lookback",
        help="计算前额外加载的历史时长",
    )
    parser.add_argument(
        "--codes",
        type=json_array,
        required=True,
        metavar="JSON",
        help="股票代码 JSON 数组；空数组表示全市场",
    )
    parser.add_argument(
        "--factors",
        type=json_array,
        metavar="JSON",
        help="数据库因子 JSON 数组",
    )
    parser.add_argument(
        "--derivatives",
        type=json_object,
        metavar="JSON",
        help="命名派生因子 JSON 对象",
    )
    parser.add_argument(
        "--filters",
        type=json_array,
        metavar="JSON",
        help="过滤因子名称 JSON 数组",
    )


def build_parser(*, prog: str | None = None) -> argparse.ArgumentParser:
    """创建应用命令解析器。"""
    parser = argparse.ArgumentParser(
        prog=prog,
        description="运行查询或回测应用。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  core-manage apps query "
            "--start-date 2025-01-01 --end-date 2025-01-31 "
            "--codes '[\\\"000001.SZ\\\"]' "
            "--factors '[\\\"close\\\"]'\n"
            "  core-manage apps backtest "
            "--start-date 2025-01-01 --end-date 2025-01-31 "
            "--codes '[\\\"000001.SZ\\\"]' "
            "--factors '[\\\"open\\\",\\\"low\\\",\\\"high\\\","
            "\\\"close\\\",\\\"volume\\\",\\\"upLimitPrice\\\","
            "\\\"downLimitPrice\\\",\\\"prevClosePrice\\\"]' "
            "--callbacks CALLBACKS_JSON "
            "--config '{\\\"cash\\\":1000000}'"
        ),
    )
    commands = parser.add_subparsers(
        dest="app",
        metavar="APP",
        required=True,
    )

    query_parser = commands.add_parser(
        "query",
        help="执行因子查询",
        description="执行因子查询。",
        allow_abbrev=False,
    )
    add_query_arguments(query_parser)

    backtest_parser = commands.add_parser(
        "backtest",
        help="执行日频回测",
        description="执行日频回测。",
        allow_abbrev=False,
    )
    add_query_arguments(backtest_parser)
    backtest_parser.add_argument(
        "--callbacks",
        type=json_object,
        required=True,
        metavar="CALLBACKS_JSON",
        help="回调名称到 DolphinDB 函数定义的 JSON 对象",
    )
    backtest_parser.add_argument(
        "--utils",
        type=json_object,
        metavar="JSON",
        help="工具函数名称到 DolphinDB 函数定义的 JSON 对象",
    )
    backtest_parser.add_argument(
        "--codes-query",
        type=json_object,
        metavar="JSON",
        help="选股 FactorQuery JSON 对象",
    )
    backtest_parser.add_argument(
        "--adj",
        choices=("hfq", "qfq"),
        help="价格复权方式：hfq 后复权，qfq 前复权；默认不复权",
    )
    backtest_parser.add_argument("--name", help="回测引擎名称")
    backtest_parser.add_argument(
        "--config",
        type=json_object,
        metavar="JSON",
        help="Backtest 配置 JSON 对象",
    )
    backtest_parser.add_argument(
        "--annual-trading-days",
        type=positive_int,
        default=250,
        metavar="DAYS",
        help="年化交易日数，默认 250",
    )
    backtest_parser.add_argument(
        "--risk-free-rate",
        type=float,
        default=0.04,
        metavar="RATE",
        help="年化无风险利率，默认 0.04",
    )
    backtest_parser.add_argument(
        "--source-ref",
        default="coreBacktestSource",
        help="基础因子查询结果变量名，默认 coreBacktestSource",
    )
    backtest_parser.add_argument(
        "--message-ref",
        default="coreBacktestMessage",
        help="日频消息查询结果变量名，默认 coreBacktestMessage",
    )
    return parser


def main(
        argv: Sequence[str] | None = None,
        *,
        prog: str | None = None,
) -> int:
    """解析参数并运行指定应用。"""
    parser = build_parser(prog=prog)
    arguments = parser.parse_args(argv)
    request: dict[str, Any] = {
        "start_date": arguments.start_date,
        "end_date": arguments.end_date,
        "codes": arguments.codes,
    }
    for name in ("lookback", "factors", "derivatives", "filters"):
        value = getattr(arguments, name)
        if value is not None:
            request[name] = value

    if arguments.app == "query":
        from core.apps.query import execute_query

        with execute_query(request):
            pass
        return 0

    from core.apps.backtest import run_backtest

    with run_backtest(
        dataset_query=request,
        callbacks=arguments.callbacks,
        utils=arguments.utils,
        codes_query=arguments.codes_query,
        adj=arguments.adj,
        name=arguments.name,
        config=arguments.config,
        annual_trading_days=arguments.annual_trading_days,
        risk_free_rate=arguments.risk_free_rate,
        source_ref=arguments.source_ref,
        message_ref=arguments.message_ref,
    ):
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
