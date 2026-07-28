"""通过交叉、变异和精英保留搜索 ETF 池的滚动遗传算法。"""

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
from research.rolling_search import (
    best_pool,
    crossover,
    one_swap,
)

METHOD = "rolling_genetic"
OUTPUT_DIRECTORY = Path(__file__).with_name("output")
POPULATION_SIZE = 20
MUTATION_PROBABILITY = 0.35


def tournament(
    population: list[tuple[str, ...]],
    evaluator: PoolEvaluator,
    generator: np.random.Generator,
) -> tuple[str, ...]:
    """从三个随机个体中返回训练分数最高者。"""
    size = min(3, len(population))
    indices = generator.choice(
        len(population),
        size=size,
        replace=False,
    )
    candidates = [population[int(index)] for index in indices]
    return max(candidates, key=lambda codes: evaluator.scores[codes])


def select_pool(
    evaluator: PoolEvaluator,
    universe_codes: tuple[str, ...],
    eligible_codes: tuple[str, ...],
    generator: np.random.Generator,
) -> SelectionResult:
    """以锦标赛选择父代，执行集合交叉和单点变异。"""
    del universe_codes
    population: list[tuple[str, ...]] = []
    initial_size = min(POPULATION_SIZE, evaluator.evaluation_limit)
    for _ in range(initial_size):
        codes = sample_unseen_pool(
            evaluator,
            generator,
            eligible_codes,
            set(evaluator.scores),
        )
        evaluator.evaluate(codes, phase="initial_population")
        population.append(codes)

    generation = 0
    while evaluator.evaluation_count < evaluator.evaluation_limit:
        children: list[tuple[str, ...]] = []
        child_count = min(
            POPULATION_SIZE,
            evaluator.evaluation_limit - evaluator.evaluation_count,
        )
        for _ in range(child_count):
            child: tuple[str, ...] | None = None
            for _ in range(1_000):
                left = tournament(population, evaluator, generator)
                right = tournament(population, evaluator, generator)
                proposal = crossover(
                    evaluator,
                    left,
                    right,
                    eligible_codes,
                    generator,
                )
                if generator.random() < MUTATION_PROBABILITY:
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

        population = sorted(
            set(population + children),
            key=lambda codes: evaluator.scores[codes],
            reverse=True,
        )[:POPULATION_SIZE]
        generation += 1

    selected = best_pool(evaluator)
    diagnostics = pd.DataFrame.from_records(
        [
            {
                "population_size": POPULATION_SIZE,
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
    """运行滚动遗传算法。"""
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
