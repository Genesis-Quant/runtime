"""同时保留多个高分搜索分支的滚动束搜索选池方法。"""

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

METHOD = "rolling_beam_search"
OUTPUT_DIRECTORY = Path(__file__).with_name("output")
BEAM_WIDTH = 5


def select_pool(
    evaluator: PoolEvaluator,
    universe_codes: tuple[str, ...],
    eligible_codes: tuple[str, ...],
    generator: np.random.Generator,
) -> SelectionResult:
    """每轮扩展当前最好的多个单次替换邻居。"""
    del universe_codes
    beam: list[tuple[str, ...]] = []
    initial_count = min(BEAM_WIDTH, evaluator.evaluation_limit)
    for _ in range(initial_count):
        codes = sample_unseen_pool(
            evaluator,
            generator,
            eligible_codes,
            set(evaluator.scores),
        )
        evaluator.evaluate(codes, phase="initial_beam")
        beam.append(codes)

    generations = 0
    while evaluator.evaluation_count < evaluator.evaluation_limit:
        children: list[tuple[str, ...]] = []
        for parent in beam:
            if evaluator.evaluation_count >= evaluator.evaluation_limit:
                break
            proposal, removed, added = unseen_one_swap(
                evaluator,
                parent,
                eligible_codes,
                generator,
                set(evaluator.scores),
            )
            evaluator.evaluate(
                proposal,
                phase="beam_neighbor",
                generation=generations,
                removed=removed,
                added=added,
            )
            children.append(proposal)
        beam = sorted(
            set(beam + children),
            key=lambda codes: evaluator.scores[codes],
            reverse=True,
        )[:BEAM_WIDTH]
        generations += 1

    selected = best_pool(evaluator)
    diagnostics = pd.DataFrame.from_records(
        [
            {
                "beam_width": BEAM_WIDTH,
                "generations": generations,
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
    """运行滚动束搜索方法。"""
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
