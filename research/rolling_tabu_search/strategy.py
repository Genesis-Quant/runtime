"""使用短期禁忌表避免立即反向替换的滚动选池方法。"""

from collections import deque
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

METHOD = "rolling_tabu_search"
OUTPUT_DIRECTORY = Path(__file__).with_name("output")
TABU_TENURE = 10
CANDIDATES_PER_STEP = 5


def select_pool(
    evaluator: PoolEvaluator,
    universe_codes: tuple[str, ...],
    eligible_codes: tuple[str, ...],
    generator: np.random.Generator,
) -> SelectionResult:
    """每轮选择最佳非禁忌邻居，并暂时禁止其反向替换。"""
    del universe_codes
    current = sample_unseen_pool(
        evaluator,
        generator,
        eligible_codes,
        set(),
    )
    evaluator.evaluate(current, phase="initial")
    tabu_queue: deque[tuple[str, str]] = deque(maxlen=TABU_TENURE)
    moves = 0
    while evaluator.evaluation_count < evaluator.evaluation_limit:
        candidates: list[
            tuple[float, tuple[str, ...], str, str]
        ] = []
        batch_size = min(
            CANDIDATES_PER_STEP,
            evaluator.evaluation_limit - evaluator.evaluation_count,
        )
        for _ in range(batch_size):
            proposal, removed, added = unseen_one_swap(
                evaluator,
                current,
                eligible_codes,
                generator,
                set(evaluator.scores),
                forbidden=set(tabu_queue),
            )
            score = evaluator.evaluate(
                proposal,
                phase="tabu_neighbor",
                removed=removed,
                added=added,
            )
            candidates.append((score, proposal, removed, added))
        _, current, removed, added = max(candidates, key=lambda row: row[0])
        tabu_queue.append((added, removed))
        moves += 1

    selected = best_pool(evaluator)
    diagnostics = pd.DataFrame.from_records(
        [
            {
                "tabu_tenure": TABU_TENURE,
                "moves": moves,
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
    """运行滚动禁忌搜索方法。"""
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
