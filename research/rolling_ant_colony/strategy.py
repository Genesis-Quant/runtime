"""用高分组合强化代码信息素的滚动蚁群选池方法。"""

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
    ranked_code_selection,
    unseen_weighted_pool,
)

METHOD = "rolling_ant_colony"
OUTPUT_DIRECTORY = Path(__file__).with_name("output")
BATCH_SIZE = 20
EVAPORATION_RATE = 0.2
ELITE_COUNT = 5


def select_pool(
    evaluator: PoolEvaluator,
    universe_codes: tuple[str, ...],
    eligible_codes: tuple[str, ...],
    generator: np.random.Generator,
) -> SelectionResult:
    """按信息素抽样，使用每批高分组合的名次强化成员代码。"""
    pheromones = np.ones(len(eligible_codes), dtype=float)
    generation = 0
    while evaluator.evaluation_count < evaluator.evaluation_limit:
        batch: list[tuple[str, ...]] = []
        batch_target = min(
            BATCH_SIZE,
            evaluator.evaluation_limit - evaluator.evaluation_count,
        )
        for _ in range(batch_target):
            proposal = unseen_weighted_pool(
                evaluator,
                eligible_codes,
                pheromones,
                generator,
                set(evaluator.scores),
            )
            evaluator.evaluate(
                proposal,
                phase="ant",
                generation=generation,
            )
            batch.append(proposal)

        elite = sorted(
            batch,
            key=lambda codes: evaluator.scores[codes],
            reverse=True,
        )[: min(ELITE_COUNT, len(batch))]
        pheromones *= 1.0 - EVAPORATION_RATE
        for rank, codes in enumerate(elite, start=1):
            deposit = (len(elite) - rank + 1) / len(elite)
            for code in codes:
                pheromones[eligible_codes.index(code)] += deposit
        pheromones = np.maximum(pheromones, 0.05)
        generation += 1

    scores = dict(
        zip(eligible_codes, pheromones.tolist(), strict=True)
    )
    return ranked_code_selection(
        evaluator,
        scores,
        universe_codes,
        eligible_codes,
        score_name="pheromone",
    )


def run(
    session: Any,
    *,
    start_date: str = "2022-01-01",
    end_date: str = "2026-07-26",
    evaluation_count: int = EVALUATION_COUNT,
    random_seed: int = RANDOM_SEED,
) -> RollingResult:
    """运行滚动蚁群方法。"""
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
