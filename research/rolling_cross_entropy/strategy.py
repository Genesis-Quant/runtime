"""用交叉熵法逐批集中到高 Sharpe 代码的滚动选池方法。"""

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

METHOD = "rolling_cross_entropy"
OUTPUT_DIRECTORY = Path(__file__).with_name("output")
BATCH_SIZE = 20
ELITE_FRACTION = 0.25
SMOOTHING = 0.7


def select_pool(
    evaluator: PoolEvaluator,
    universe_codes: tuple[str, ...],
    eligible_codes: tuple[str, ...],
    generator: np.random.Generator,
) -> SelectionResult:
    """逐批用高分组合的成员频率更新下一批抽样概率。"""
    probabilities = np.full(
        len(eligible_codes),
        1.0 / len(eligible_codes),
    )
    generation = 0
    while evaluator.evaluation_count < evaluator.evaluation_limit:
        current_batch: list[tuple[str, ...]] = []
        batch_target = min(
            BATCH_SIZE,
            evaluator.evaluation_limit - evaluator.evaluation_count,
        )
        for _ in range(batch_target):
            proposal = unseen_weighted_pool(
                evaluator,
                eligible_codes,
                probabilities,
                generator,
                set(evaluator.scores),
            )
            evaluator.evaluate(
                proposal,
                phase="cross_entropy",
                generation=generation,
            )
            current_batch.append(proposal)

        elite_count = max(
            1,
            int(np.ceil(len(current_batch) * ELITE_FRACTION)),
        )
        elite = sorted(
            current_batch,
            key=lambda codes: evaluator.scores[codes],
            reverse=True,
        )[:elite_count]
        elite_frequencies = np.asarray(
            [
                sum(code in codes for codes in elite) / len(elite)
                for code in eligible_codes
            ]
        )
        elite_frequencies = np.maximum(elite_frequencies, 0.02)
        elite_frequencies /= elite_frequencies.sum()
        probabilities = (
            (1.0 - SMOOTHING) * probabilities
            + SMOOTHING * elite_frequencies
        )
        probabilities /= probabilities.sum()
        generation += 1

    scores = dict(
        zip(eligible_codes, probabilities.tolist(), strict=True)
    )
    return ranked_code_selection(
        evaluator,
        scores,
        universe_codes,
        eligible_codes,
        score_name="sampling_probability",
    )


def run(
    session: Any,
    *,
    start_date: str = "2022-01-01",
    end_date: str = "2026-07-26",
    evaluation_count: int = EVALUATION_COUNT,
    random_seed: int = RANDOM_SEED,
) -> RollingResult:
    """运行滚动交叉熵选池方法。"""
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
