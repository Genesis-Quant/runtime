"""用定长二进制粒子群搜索高 Sharpe ETF 池。"""

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

METHOD = "rolling_particle_swarm"
OUTPUT_DIRECTORY = Path(__file__).with_name("output")
SWARM_SIZE = 20
INERTIA = 0.65
COGNITIVE_WEIGHT = 1.4
SOCIAL_WEIGHT = 1.4


def as_vector(
    codes: tuple[str, ...],
    eligible_codes: tuple[str, ...],
) -> np.ndarray:
    """把 ETF 池转换为 0/1 向量。"""
    selected = set(codes)
    return np.asarray(
        [float(code in selected) for code in eligible_codes]
    )


def select_pool(
    evaluator: PoolEvaluator,
    universe_codes: tuple[str, ...],
    eligible_codes: tuple[str, ...],
    generator: np.random.Generator,
) -> SelectionResult:
    """根据个体最佳与全局最佳更新速度并分组抽取 ETF。"""
    del universe_codes
    particles: list[tuple[str, ...]] = []
    initial_size = min(SWARM_SIZE, evaluator.evaluation_limit)
    for _ in range(initial_size):
        codes = sample_unseen_pool(
            evaluator,
            generator,
            eligible_codes,
            set(evaluator.scores),
        )
        evaluator.evaluate(codes, phase="initial_swarm")
        particles.append(codes)

    velocities = np.zeros(
        (len(particles), len(eligible_codes)),
        dtype=float,
    )
    personal_best = particles.copy()
    generation = 0
    particle_index = 0
    while evaluator.evaluation_count < evaluator.evaluation_limit:
        particle_index %= len(particles)
        global_best = best_pool(evaluator)
        position = as_vector(
            particles[particle_index],
            eligible_codes,
        )
        personal = as_vector(
            personal_best[particle_index],
            eligible_codes,
        )
        global_vector = as_vector(global_best, eligible_codes)
        velocities[particle_index] = (
            INERTIA * velocities[particle_index]
            + COGNITIVE_WEIGHT
            * generator.random(len(eligible_codes))
            * (personal - position)
            + SOCIAL_WEIGHT
            * generator.random(len(eligible_codes))
            * (global_vector - position)
        )

        proposal: tuple[str, ...] | None = None
        for _ in range(1_000):
            noise = generator.gumbel(
                size=len(eligible_codes)
            )
            priorities = velocities[particle_index] + noise
            candidate = weighted_pool(
                evaluator,
                eligible_codes,
                np.exp(priorities - priorities.max()),
                generator,
            )
            if candidate not in evaluator.scores:
                proposal = candidate
                break
        if proposal is None:
            proposal = sample_unseen_pool(
                evaluator,
                generator,
                eligible_codes,
                set(evaluator.scores),
            )

        score = evaluator.evaluate(
            proposal,
            phase="particle",
            generation=generation,
            particle=particle_index,
        )
        particles[particle_index] = proposal
        if score > evaluator.scores[personal_best[particle_index]]:
            personal_best[particle_index] = proposal
        particle_index += 1
        if particle_index % len(particles) == 0:
            generation += 1

    selected = best_pool(evaluator)
    diagnostics = pd.DataFrame.from_records(
        [
            {
                "swarm_size": SWARM_SIZE,
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
    """运行滚动粒子群方法。"""
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
