"""通过命令行运行一个或多个数据写入 Worker。"""

import argparse
import time
from collections.abc import Sequence
from typing import Any


WORKER_ORDER = (
    "daily",
    "limit",
    "daily-basic",
    "adj-factor",
    "hfq",
    "st",
    "balance-sheet",
    "income",
    "cashflow",
    "fina-indicator",
    "dividend",
    "index-weight",
)

WORKER_DESCRIPTIONS = {
    "daily": "全市场未复权日行情",
    "limit": "全市场每日涨跌停价格",
    "daily-basic": "全市场每日估值和市值指标",
    "adj-factor": "全市场复权因子",
    "hfq": "逐股票后复权日行情",
    "st": "全市场 ST 名单",
    "balance-sheet": "逐股票资产负债表",
    "income": "逐股票利润表及 TTM 因子",
    "cashflow": "逐股票现金流量表及 TTM 因子",
    "fina-indicator": "逐股票财务指标",
    "dividend": "逐股票分红送股宽表",
    "index-weight": "指数成分股权重；每个指数创建一个 Worker",
}

WORKER_ALIASES = {
    "stock-daily": "daily",
    "stockdailyworker": "daily",
    "stock-limit": "limit",
    "stocklimitworker": "limit",
    "stock-daily-basic": "daily-basic",
    "stockdailybasicworker": "daily-basic",
    "stock-adj-factor": "adj-factor",
    "stockadjfactorworker": "adj-factor",
    "stock-hfq": "hfq",
    "stockhfqworker": "hfq",
    "stock-st": "st",
    "stockstworker": "st",
    "balancesheet": "balance-sheet",
    "stock-balance-sheet": "balance-sheet",
    "stockbalancesheetworker": "balance-sheet",
    "stock-income": "income",
    "stockincomeworker": "income",
    "stock-cashflow": "cashflow",
    "stockcashflowworker": "cashflow",
    "stock-fina-indicator": "fina-indicator",
    "stockfinaindicatorworker": "fina-indicator",
    "stock-dividend": "dividend",
    "stockdividendworker": "dividend",
    "indexweight": "index-weight",
    "indexweightworker": "index-weight",
}

DATE_WORKERS = frozenset({
    "daily",
    "limit",
    "daily-basic",
    "adj-factor",
    "st",
    "index-weight",
})
STOCK_WORKERS = frozenset({
    "hfq",
    "balance-sheet",
    "income",
    "cashflow",
    "fina-indicator",
    "dividend",
})


def positive_int(value: str) -> int:
    """解析大于零的整数命令行参数。"""
    result = int(value)
    if result <= 0:
        raise argparse.ArgumentTypeError("必须大于 0")
    return result


def nonnegative_int(value: str) -> int:
    """解析不小于零的整数命令行参数。"""
    result = int(value)
    if result < 0:
        raise argparse.ArgumentTypeError("不能小于 0")
    return result


def nonnegative_float(value: str) -> float:
    """解析不小于零的浮点命令行参数。"""
    result = float(value)
    if result < 0:
        raise argparse.ArgumentTypeError("不能小于 0")
    return result


def build_parser() -> argparse.ArgumentParser:
    """创建 Worker 命令行解析器。"""
    parser = argparse.ArgumentParser(
        description="运行指定 Worker 或依次运行全部 Worker。",
        epilog=(
            "示例：\n"
            "  python manage.py daily adj-factor\n"
            "  python manage.py income --codes 000001.SZ,600000.SH\n"
            "  python manage.py index-weight --index-code 000300.SH --dry-run\n"
            "  python manage.py all --start-date 2025-01-01 --overwrite"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "workers",
        nargs="*",
        metavar="WORKER",
        help="Worker 名称；使用 all 运行全部，使用 --list-workers 查看列表",
    )
    parser.add_argument(
        "--list-workers",
        action="store_true",
        help="列出可用 Worker 后退出",
    )
    parser.add_argument("--start-date", help="更新起始日期")
    parser.add_argument("--end-date", help="更新结束日期，默认今天")
    parser.add_argument(
        "--codes",
        action="append",
        metavar="CODE[,CODE...]",
        help="限制逐股票 Worker 的股票代码，可重复传入",
    )
    parser.add_argument(
        "--index-code",
        action="append",
        metavar="CODE[,CODE...]",
        help="index-weight 的指数代码，默认使用配置文件中的 INDEX_CODES",
    )
    parser.add_argument("--threads", type=positive_int, help="并发线程数")
    parser.add_argument(
        "--throttle",
        type=nonnegative_int,
        help="每秒最大 API 请求数，0 表示不限速",
    )
    parser.add_argument(
        "--max-retries",
        type=positive_int,
        help="单次请求最大重试次数",
    )
    parser.add_argument(
        "--retry-interval",
        type=nonnegative_float,
        help="重试间隔秒数",
    )
    parser.add_argument(
        "--batch-size",
        type=positive_int,
        help="单次写入的最大行数",
    )
    parser.add_argument(
        "--chunk-size",
        type=positive_int,
        help="DateWorker 每个完整提交块包含的自然日数",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "忽略增量水位并重新抓取指定区间；同键数据由 TSDB 保留最新值，"
            "不会预先删除旧记录"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="抓取并校验数据但不创建 writer、不写入数据库",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="任一 Worker 失败后立即停止；默认继续运行其余 Worker",
    )
    return parser


def split_values(
        values: Sequence[str] | None,
        location: str,
) -> tuple[str, ...] | None:
    """拆分可重复的逗号列表，在保持顺序的同时去重。"""
    if values is None:
        return None
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        parts = [part.strip() for part in value.split(",")]
        if any(not part for part in parts):
            raise ValueError(f"{location} 不能包含空值")
        for part in parts:
            if part not in seen:
                result.append(part)
                seen.add(part)
    return tuple(result)


def normalize_worker_names(values: Sequence[str]) -> tuple[str, ...]:
    """规范 Worker 名称、展开 all，并保持用户给定的执行顺序。"""
    if not values:
        raise ValueError("至少指定一个 Worker，或使用 all")

    normalized: list[str] = []
    for value in values:
        key = value.strip().lower().replace("_", "-")
        key = WORKER_ALIASES.get(key, key)
        if key == "all":
            if len(values) != 1:
                raise ValueError("all 不能与其他 Worker 同时使用")
            return WORKER_ORDER
        if key not in WORKER_DESCRIPTIONS:
            available = "、".join(WORKER_ORDER)
            raise ValueError(
                f"未知 Worker：{value!r}；可用值：{available}、all"
            )
        if key not in normalized:
            normalized.append(key)
    return tuple(normalized)


def worker_kwargs(arguments: argparse.Namespace) -> dict[str, Any]:
    """返回仅包含用户显式配置值的公共 Worker 构造参数。"""
    result: dict[str, Any] = {"overwrite": arguments.overwrite}
    mappings = {
        "start_date": arguments.start_date,
        "end_date": arguments.end_date,
        "threads": arguments.threads,
        "throttle": arguments.throttle,
        "max_retries": arguments.max_retries,
        "retry_interval": arguments.retry_interval,
        "batch_size": arguments.batch_size,
    }
    result.update({
        name: value
        for name, value in mappings.items()
        if value is not None
    })
    return result


def create_workers(
        names: Sequence[str],
        arguments: argparse.Namespace,
) -> list[Any]:
    """根据规范名称创建按执行顺序排列的 Worker 实例。"""
    from config import INDEX_CODES
    from core.workers import (
        IndexWeightWorker,
        StockAdjFactorWorker,
        StockBalanceSheetWorker,
        StockCashflowWorker,
        StockDailyBasicWorker,
        StockDailyWorker,
        StockDividendWorker,
        StockFinaIndicatorWorker,
        StockHfqWorker,
        StockIncomeWorker,
        StockLimitWorker,
        StockSTWorker,
    )

    date_types = {
        "daily": StockDailyWorker,
        "limit": StockLimitWorker,
        "daily-basic": StockDailyBasicWorker,
        "adj-factor": StockAdjFactorWorker,
        "st": StockSTWorker,
    }
    stock_types = {
        "hfq": StockHfqWorker,
        "balance-sheet": StockBalanceSheetWorker,
        "income": StockIncomeWorker,
        "cashflow": StockCashflowWorker,
        "fina-indicator": StockFinaIndicatorWorker,
        "dividend": StockDividendWorker,
    }

    common = worker_kwargs(arguments)
    date_arguments = dict(common)
    if arguments.chunk_size is not None:
        date_arguments["chunk_size"] = arguments.chunk_size
    stock_arguments = dict(common)
    codes = split_values(arguments.codes, "--codes")
    if codes is not None:
        stock_arguments["codes"] = codes

    index_codes = split_values(arguments.index_code, "--index-code")
    if index_codes is None:
        index_codes = tuple(INDEX_CODES)

    workers: list[Any] = []
    for name in names:
        if name in date_types:
            workers.append(date_types[name](**date_arguments))
        elif name in stock_types:
            workers.append(stock_types[name](**stock_arguments))
        elif name == "index-weight":
            if not index_codes:
                raise ValueError(
                    "没有可用指数代码，请配置 INDEX_CODES 或传入 --index-code"
                )
            workers.extend(
                IndexWeightWorker(index_code, **date_arguments)
                for index_code in index_codes
            )
        else:
            raise AssertionError(f"未注册 Worker：{name}")
    return workers


def dry_run_worker(worker: Any) -> int:
    """抓取并校验一个 Worker 的全部计划结果，但不执行任何写入。"""
    from core.utils.logging import logger

    started = time.perf_counter()
    rows = 0
    frames = 0
    logger.info(f"{worker} 开始 dry-run：不会写入数据库")
    for data in worker.fetch_all():
        frame = worker.check(data)
        rows += len(frame)
        frames += 1
    elapsed = time.perf_counter() - started
    logger.success(
        f"{worker} dry-run 完成：结果={rows:,}行，"
        f"批次={frames:,}，耗时={elapsed:.2f}秒"
    )
    return rows


def validate_arguments(
        parser: argparse.ArgumentParser,
        names: Sequence[str],
        arguments: argparse.Namespace,
) -> None:
    """拒绝对所选 Worker 没有意义的专用参数。"""
    selected = set(names)
    if arguments.codes and not selected.intersection(STOCK_WORKERS):
        parser.error("--codes 仅适用于逐股票 Worker")
    if arguments.index_code and "index-weight" not in selected:
        parser.error("--index-code 仅适用于 index-weight")
    if (
            arguments.chunk_size is not None
            and not selected.intersection(DATE_WORKERS)
    ):
        parser.error("--chunk-size 仅适用于 DateWorker")


def print_workers() -> None:
    """打印规范 Worker 名称和用途。"""
    width = max(map(len, WORKER_ORDER))
    for name in WORKER_ORDER:
        print(f"{name:<{width}}  {WORKER_DESCRIPTIONS[name]}")


def main(argv: Sequence[str] | None = None) -> int:
    """解析命令行、依次运行 Worker，并返回进程退出码。"""
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.list_workers:
        print_workers()
        return 0

    try:
        names = normalize_worker_names(arguments.workers)
        split_values(arguments.codes, "--codes")
        split_values(arguments.index_code, "--index-code")
    except ValueError as error:
        parser.error(str(error))
    validate_arguments(parser, names, arguments)

    try:
        workers = create_workers(names, arguments)
    except (TypeError, ValueError) as error:
        parser.error(str(error))

    from core.utils.logging import logger

    mode = "dry-run" if arguments.dry_run else "写入"
    if arguments.overwrite:
        logger.warning(
            "已启用覆盖模式：将忽略增量水位并重新抓取指定日期区间；"
            "不会预先删除数据库记录"
        )
    logger.info(
        f"Worker 任务开始：模式={mode}，"
        f"任务={len(workers):,}，选择={list(names)}"
    )

    started = time.perf_counter()
    total = 0
    failures: list[str] = []
    for number, worker in enumerate(workers, start=1):
        logger.info(f"运行 Worker {number:,}/{len(workers):,}：{worker}")
        try:
            rows = (
                dry_run_worker(worker)
                if arguments.dry_run
                else worker.run()
            )
        except KeyboardInterrupt:
            logger.warning(f"Worker 任务被用户中断：{worker}")
            return 130
        except Exception as error:
            failures.append(
                f"{worker}: {type(error).__name__}: {error}"
            )
            logger.exception(f"Worker 运行失败：{worker}")
            if arguments.fail_fast:
                break
        else:
            total += rows

    elapsed = time.perf_counter() - started
    if failures:
        logger.error(
            f"Worker 任务完成但存在失败：成功结果={total:,}行，"
            f"失败={len(failures):,}，耗时={elapsed:.2f}秒；"
            + "；".join(failures)
        )
        return 1

    result_name = "校验" if arguments.dry_run else "写入"
    logger.success(
        f"Worker 任务全部完成：{result_name}={total:,}行，"
        f"任务={len(workers):,}，耗时={elapsed:.2f}秒"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
