"""采用父代加子代精英保留的滚动进化策略选池方法。"""

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
from research.rolling_search import best_pool, one_swap

METHOD = "rolling_evolution_strategy"
OUTPUT_DIRECTORY = Path(__file__).with_name("output")
PARENT_COUNT = 10
OFFSPRING_COUNT = 20


def select_pool(
    evaluator: PoolEvaluator,
    universe_codes: tuple[str, ...],
    eligible_codes: tuple[str, ...],
    generator: np.random.Generator,
) -> SelectionResult:
    """从高分父代无性变异，按 (μ+λ) 规则保留下一代。"""
    del universe_codes
    parents: list[tuple[str, ...]] = []
    initial_size = min(PARENT_COUNT, evaluator.evaluation_limit)
    for _ in range(initial_size):
        codes = sample_unseen_pool(
            evaluator,
            generator,
            eligible_codes,
            set(evaluator.scores),
        )
        evaluator.evaluate(codes, phase="initial_parents")
        parents.append(codes)

    generation = 0
    while evaluator.evaluation_count < evaluator.evaluation_limit:
        children: list[tuple[str, ...]] = []
        child_count = min(
            OFFSPRING_COUNT,
            evaluator.evaluation_limit - evaluator.evaluation_count,
        )
        for _ in range(child_count):
            child: tuple[str, ...] | None = None
            for _ in range(1_000):
                parent = parents[int(generator.integers(len(parents)))]
                proposal, _, _ = one_swap(
                    evaluator,
                    parent,
                    eligible_codes,
                    generator,
                )
                if generator.random() < 0.25:
                    proposal, _, _ = one_swap(
                        evaluator,
                        proposal,
                        eligible_codes,
                        generator,
                    )
                if proposal not in evaluator.scores:
                    child = proposal
                    break
            if child is None:
                child = sample_unseen_pool(
                    evaluator,
                    generator,
                    eligible_codes,
                    set(evaluator.scores),
                )
            evaluator.evaluate(
                child,
                phase="offspring",
                generation=generation,
            )
            children.append(child)
        parents = sorted(
            set(parents + children),
            key=lambda codes: evaluator.scores[codes],
            reverse=True,
        )[:PARENT_COUNT]
        generation += 1

    selected = best_pool(evaluator)
    diagnostics = pd.DataFrame.from_records(
        [
            {
                "parent_count": PARENT_COUNT,
                "offspring_count": OFFSPRING_COUNT,
                "generations": generation,
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
    """运行滚动进化策略。"""
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
