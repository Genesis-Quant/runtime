"""只接受单代码替换改进的滚动爬山选池方法。"""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.rolling_common import (
    EVALUATION_COUNT,
    RANDOM_SEED,
    PoolEvaluator,
    RollingResult,
    SelectionResult,
    sample_unseen_pool,
)
from research.rolling_entry import run_and_save, run_method
from research.rolling_search import best_pool, unseen_one_swap

METHOD = "rolling_hill_climb"
OUTPUT_DIRECTORY = Path(__file__).with_name("output")


def select_pool(
    evaluator: PoolEvaluator,
    universe_codes: tuple[str, ...],
    eligible_codes: tuple[str, ...],
    generator: np.random.Generator,
) -> SelectionResult:
    """从一个随机池出发，仅接受提升 Sharpe 的单次替换。"""
    del universe_codes
    current = sample_unseen_pool(
        evaluator,
        generator,
        eligible_codes,
        set(),
    )
    current_score = evaluator.evaluate(current, phase="initial")
    accepted = 0
    while evaluator.evaluation_count < evaluator.evaluation_limit:
        proposal, removed, added = unseen_one_swap(
            evaluator,
            current,
            eligible_codes,
            generator,
            set(evaluator.scores),
        )
        score = evaluator.evaluate(
            proposal,
            phase="neighbor",
            removed=removed,
            added=added,
        )
        if score > current_score:
            current = proposal
            current_score = score
            accepted += 1

    selected = best_pool(evaluator)
    diagnostics = pd.DataFrame.from_records(
        [
            {
                "accepted_moves": accepted,
                "training_sharpe": evaluator.scores[selected],
                "codes": "|".join(selected),
            }
        ]
    )
    return SelectionResult(selected, diagnostics)


def run(
    session: Any,
    *,
    start_date: str = "2022-01-01",
    end_date: str = "2026-07-26",
    evaluation_count: int = EVALUATION_COUNT,
    random_seed: int = RANDOM_SEED,
) -> RollingResult:
    """运行滚动爬山选池方法。"""
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
