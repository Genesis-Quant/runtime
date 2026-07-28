"""按代码入选组合的平均训练期 Sharpe 滚动选择 ETF 池。"""

from pathlib import Path
from typing import Any

import numpy as np

from research.rolling_common import (
    EVALUATION_COUNT,
    RANDOM_SEED,
    PoolEvaluator,
    RollingResult,
    SelectionResult,
)
from research.rolling_entry import run_and_save, run_method
from research.rolling_search import (
    code_statistics,
    evaluate_random_pools,
    ranked_code_selection,
)

METHOD = "rolling_mean_inclusion"
OUTPUT_DIRECTORY = Path(__file__).with_name("output")


def select_pool(
    evaluator: PoolEvaluator,
    universe_codes: tuple[str, ...],
    eligible_codes: tuple[str, ...],
    generator: np.random.Generator,
) -> SelectionResult:
    """按类别选择入选组合平均 Sharpe 最高的 ETF。"""
    evaluate_random_pools(evaluator, eligible_codes, generator)
    statistics = code_statistics(
        evaluator,
        universe_codes,
        eligible_codes,
    ).set_index("code")
    scores = statistics["included_mean_sharpe"].to_dict()
    extras = statistics[
        ["included_count", "excluded_count", "excluded_mean_sharpe"]
    ].to_dict("index")
    return ranked_code_selection(
        evaluator,
        scores,
        universe_codes,
        eligible_codes,
        score_name="mean_included_sharpe",
        extra_columns=extras,
    )


def run(
    session: Any,
    *,
    start_date: str = "2022-01-01",
    end_date: str = "2026-07-26",
    evaluation_count: int = EVALUATION_COUNT,
    random_seed: int = RANDOM_SEED,
) -> RollingResult:
    """运行滚动入选均值方法。"""
    return run_method(
        session,
        METHOD,
        select_pool,
        start_date=start_date,
        end_date=end_date,
        evaluation_count=evaluation_count,
        random_seed=random_seed,
    )


def main() -> None:
    """运行并保存默认研究。"""
    run_and_save(METHOD, select_pool, OUTPUT_DIRECTORY)


if __name__ == "__main__":
    main()
