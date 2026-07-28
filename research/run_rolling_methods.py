"""批量运行滚动 ETF 选池方法并生成横向比较。"""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from core.database import create_session
from research import get_data
from research.rolling_common import (
    EVALUATION_COUNT,
    END_DATE,
    FACTOR_NAMES,
    HISTORY_BUFFER_DAYS,
    RANDOM_SEED,
    START_DATE,
    build_rolling_periods,
    run_rolling_method,
    save_result,
)
from research.rolling_methods import METHODS

OUTPUT_FILE = Path(__file__).with_name(
    "rolling_method_comparison.csv"
)


def load_saved_comparison(
    method_names: Sequence[str] = tuple(METHODS),
) -> pd.DataFrame:
    """读取各方法已保存的摘要并重建完整比较表。"""
    records: list[dict[str, Any]] = []
    for method_name in method_names:
        method = METHODS[method_name]
        summary_file = method.output_directory / "summary.json"
        if not summary_file.exists():
            raise FileNotFoundError(
                f"{method_name} 尚未生成结果：{summary_file}"
            )
        with summary_file.open(encoding="utf-8") as file:
            summary = json.load(file)
        records.append(
            {
                "method": method_name,
                "description": method.description,
                **summary["performance"],
            }
        )
    return pd.DataFrame.from_records(records).sort_values(
        ["sharpe", "annual_return"],
        ascending=[False, False],
        ignore_index=True,
    )


def run_methods(
    session: Any,
    method_names: Sequence[str],
    *,
    start_date: str,
    end_date: str,
    evaluation_count: int,
    random_seed: int,
    save_outputs: bool = True,
) -> pd.DataFrame:
    """一次加载数据，依次运行指定方法并保存各自结果。"""
    unknown = sorted(set(method_names) - METHODS.keys())
    if unknown:
        raise ValueError(f"未知方法：{unknown}")
    if not method_names:
        raise ValueError("至少指定一种方法")

    output_start = pd.Timestamp(start_date).normalize()
    output_end = pd.Timestamp(end_date).normalize()
    periods = build_rolling_periods(output_start, output_end)
    get_data(
        session,
        FACTOR_NAMES,
        periods[0].training_start,
        output_end,
        HISTORY_BUFFER_DAYS,
    )

    records: list[dict[str, Any]] = []
    for method_name in method_names:
        method = METHODS[method_name]
        result = run_rolling_method(
            session,
            method_name,
            method.selector,
            start_date=start_date,
            end_date=end_date,
            evaluation_count=evaluation_count,
            random_seed=random_seed,
            load_data=False,
        )
        if save_outputs:
            save_result(result, method.output_directory)
        records.append(
            {
                "method": method_name,
                "description": method.description,
                **result.performance,
            }
        )
    comparison = pd.DataFrame.from_records(records).sort_values(
        ["sharpe", "annual_return"],
        ascending=[False, False],
        ignore_index=True,
    )
    if save_outputs:
        completed_methods = [
            name
            for name, method in METHODS.items()
            if (method.output_directory / "summary.json").exists()
        ]
        comparison = load_saved_comparison(completed_methods)
        comparison.to_csv(OUTPUT_FILE, index=False)
    return comparison


def parse_arguments() -> argparse.Namespace:
    """解析批量研究参数。"""
    parser = argparse.ArgumentParser(
        description="运行至少 20 种前一自然半年训练、后一自然半年持有的 ETF 选池方法"
    )
    parser.add_argument(
        "--methods",
        nargs="+",
        choices=tuple(METHODS),
        default=list(METHODS),
    )
    parser.add_argument("--start-date", default=START_DATE)
    parser.add_argument("--end-date", default=END_DATE)
    parser.add_argument(
        "--evaluation-count",
        type=int,
        default=EVALUATION_COUNT,
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=RANDOM_SEED,
    )
    parser.add_argument(
        "--no-save",
        action="store_false",
        dest="save_outputs",
        help="只验证运行，不覆盖各方法现有输出",
    )
    return parser.parse_args()


def main() -> None:
    """运行命令行指定的方法并打印比较结果。"""
    arguments = parse_arguments()
    session = create_session()
    try:
        comparison = run_methods(
            session,
            arguments.methods,
            start_date=arguments.start_date,
            end_date=arguments.end_date,
            evaluation_count=arguments.evaluation_count,
            random_seed=arguments.random_seed,
            save_outputs=arguments.save_outputs,
        )
    finally:
        session.close()
    print(comparison.to_string(index=False))


if __name__ == "__main__":
    main()
