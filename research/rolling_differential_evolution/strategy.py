"""把 ETF 池表示为定长二进制向量的滚动差分进化方法。"""

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
from research.rolling_search import best_pool, weighted_pool

METHOD = "rolling_differential_evolution"
OUTPUT_DIRECTORY = Path(__file__).with_name("output")
POPULATION_SIZE = 20
DIFFERENTIAL_WEIGHT = 0.7
CROSSOVER_RATE = 0.7


def as_mask(
    codes: tuple[str, ...],
    eligible_codes: tuple[str, ...],
) -> np.ndarray:
    """把代码集合转换为布尔成员向量。"""
    selected = set(codes)
    return np.asarray(
        [code in selected for code in eligible_codes],
        dtype=bool,
    )


def mask_to_pool(
    evaluator: PoolEvaluator,
    mask: np.ndarray,
    eligible_codes: tuple[str, ...],
    generator: np.random.Generator,
) -> tuple[str, ...]:
    """按试验向量权重构造满足全部选池约束的组合。"""
    return weighted_pool(
        evaluator,
        eligible_codes,
        np.where(mask, 4.0, 1.0),
        generator,
    )


def select_pool(
    evaluator: PoolEvaluator,
    universe_codes: tuple[str, ...],
    eligible_codes: tuple[str, ...],
    generator: np.random.Generator,
) -> SelectionResult:
    """用三个种群成员的差异构造试验向量并做贪心替换。"""
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
    target_index = 0
    while evaluator.evaluation_count < evaluator.evaluation_limit:
        if len(population) < 4:
            child = sample_unseen_pool(
                evaluator,
                generator,
                eligible_codes,
                set(evaluator.scores),
            )
            evaluator.evaluate(child, phase="random_fallback")
            population.append(child)
            continue

        target_index %= len(population)
        other_indices = [
            index
            for index in range(len(population))
            if index != target_index
        ]
        left_index, middle_index, right_index = generator.choice(
            other_indices,
            size=3,
            replace=False,
        )
        target_mask = as_mask(
            population[target_index],
            eligible_codes,
        )
        left_mask = as_mask(
            population[int(left_index)],
            eligible_codes,
        )
        middle_mask = as_mask(
            population[int(middle_index)],
            eligible_codes,
        )
        right_mask = as_mask(
            population[int(right_index)],
            eligible_codes,
        )

        child: tuple[str, ...] | None = None
        for _ in range(1_000):
            differential = (middle_mask != right_mask) & (
                generator.random(len(eligible_codes))
                < DIFFERENTIAL_WEIGHT
            )
            mutant = left_mask ^ differential
            crossover_points = (
                generator.random(len(eligible_codes)) < CROSSOVER_RATE
            )
            crossover_points[
                int(generator.integers(len(eligible_codes)))
            ] = True
            trial_mask = np.where(
                crossover_points,
                mutant,
                target_mask,
            )
            proposal = mask_to_pool(
                evaluator,
                trial_mask,
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

        child_score = evaluator.evaluate(
            child,
            phase="trial_vector",
            generation=generation,
        )
        target = population[target_index]
        if child_score > evaluator.scores[target]:
            population[target_index] = child
        target_index += 1
        if target_index % len(population) == 0:
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
    """运行滚动差分进化方法。"""
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
