"""通过多次重启降低局部最优依赖的滚动爬山选池方法。"""

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
)
from research.rolling_entry import run_and_save, run_method
from research.rolling_search import (
    best_pool,
    sample_unseen_pool,
    unseen_one_swap,
)

METHOD = "rolling_multi_start_hill"
OUTPUT_DIRECTORY = Path(__file__).with_name("output")
RESTART_INTERVAL = 20


def select_pool(
    evaluator: PoolEvaluator,
    universe_codes: tuple[str, ...],
    eligible_codes: tuple[str, ...],
    generator: np.random.Generator,
) -> SelectionResult:
    """每 20 次评估重新随机起点，并在各起点内执行爬山。"""
    del universe_codes
    restart = 0
    accepted = 0
    while evaluator.evaluation_count < evaluator.evaluation_limit:
        current = sample_unseen_pool(
            evaluator,
            generator,
            eligible_codes,
            set(evaluator.scores),
        )
        current_score = evaluator.evaluate(
            current,
            phase="restart",
            restart=restart,
        )
        local_target = min(
            evaluator.evaluation_limit,
            evaluator.evaluation_count + RESTART_INTERVAL - 1,
        )
        while evaluator.evaluation_count < local_target:
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
                restart=restart,
                removed=removed,
                added=added,
            )
            if score > current_score:
                current = proposal
                current_score = score
                accepted += 1
        restart += 1

    selected = best_pool(evaluator)
    diagnostics = pd.DataFrame.from_records(
        [
            {
                "restart_count": restart,
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
    """运行滚动多起点爬山方法。"""
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
