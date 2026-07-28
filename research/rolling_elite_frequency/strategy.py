"""按高分随机组合中的超额出现频率滚动选择 ETF 池。"""

import math
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
    evaluate_random_pools,
    ranked_code_selection,
)

METHOD = "rolling_elite_frequency"
OUTPUT_DIRECTORY = Path(__file__).with_name("output")


def select_pool(
    evaluator: PoolEvaluator,
    universe_codes: tuple[str, ...],
    eligible_codes: tuple[str, ...],
    generator: np.random.Generator,
) -> SelectionResult:
    """按前 25% 组合相对全部组合的代码出现频率选择。"""
    evaluate_random_pools(evaluator, eligible_codes, generator)
    ranked = sorted(
        evaluator.scores,
        key=lambda codes: evaluator.scores[codes],
        reverse=True,
    )
    elite_count = max(1, math.ceil(len(ranked) * 0.25))
    elite = ranked[:elite_count]
    scores: dict[str, float] = {}
    extras: dict[str, dict[str, float]] = {}
    for code in eligible_codes:
        elite_rate = sum(code in codes for codes in elite) / len(elite)
        overall_rate = sum(
            code in codes for codes in ranked
        ) / len(ranked)
        scores[code] = elite_rate - overall_rate
        extras[code] = {
            "elite_inclusion_rate": elite_rate,
            "overall_inclusion_rate": overall_rate,
        }
    return ranked_code_selection(
        evaluator,
        scores,
        universe_codes,
        eligible_codes,
        score_name="excess_elite_frequency",
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
    """运行滚动精英频率方法。"""
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
