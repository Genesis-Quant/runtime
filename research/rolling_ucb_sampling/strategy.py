"""用 UCB 平衡代码探索与训练期高分利用的滚动选池方法。"""

import math
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
    evaluate_random_pools,
    ranked_code_selection,
    unseen_weighted_pool,
)

METHOD = "rolling_ucb_sampling"
OUTPUT_DIRECTORY = Path(__file__).with_name("output")
EXPLORATION_STRENGTH = 0.75


def code_moments(
    evaluator: PoolEvaluator,
    eligible_codes: tuple[str, ...],
) -> tuple[np.ndarray, np.ndarray]:
    """计算每只 ETF 所在组合的样本数与平均 Sharpe。"""
    counts = np.asarray(
        [
            sum(code in codes for codes in evaluator.scores)
            for code in eligible_codes
        ],
        dtype=float,
    )
    means = np.asarray(
        [
            np.mean(
                [
                    score
                    for codes, score in evaluator.scores.items()
                    if code in codes
                ]
            )
            if counts[index] > 0
            else 0.0
            for index, code in enumerate(eligible_codes)
        ]
    )
    return counts, means


def select_pool(
    evaluator: PoolEvaluator,
    universe_codes: tuple[str, ...],
    eligible_codes: tuple[str, ...],
    generator: np.random.Generator,
) -> SelectionResult:
    """用代码级 UCB 引导后续组合采样，最后按后验均值选池。"""
    warmup = min(evaluator.evaluation_limit, 20)
    evaluate_random_pools(
        evaluator,
        eligible_codes,
        generator,
        warmup,
        phase="warmup",
    )
    while evaluator.evaluation_count < evaluator.evaluation_limit:
        counts, means = code_moments(evaluator, eligible_codes)
        bonus = EXPLORATION_STRENGTH * np.sqrt(
            math.log(evaluator.evaluation_count + 1)
            / np.maximum(counts, 1.0)
        )
        upper_bounds = means + bonus
        centered = upper_bounds - upper_bounds.max()
        weights = np.exp(centered / 0.35)
        proposal = unseen_weighted_pool(
            evaluator,
            eligible_codes,
            weights,
            generator,
            set(evaluator.scores),
        )
        evaluator.evaluate(proposal, phase="ucb")

    counts, means = code_moments(evaluator, eligible_codes)
    scores = dict(zip(eligible_codes, means.tolist(), strict=True))
    extras = {
        code: {"observations": int(count)}
        for code, count in zip(eligible_codes, counts, strict=True)
    }
    return ranked_code_selection(
        evaluator,
        scores,
        universe_codes,
        eligible_codes,
        score_name="posterior_mean_sharpe",
        extra_columns=extras,
    )


def run(
    session: Any,
    *,
    start_date: str = "2022-01-01",
    end_date: str = "2026-07-26",
    evaluation_count: int = EVALUATION_COUNT,
    random_seed: int = RANDOM_SEED,
) -> RollingResult:
    """运行滚动 UCB 采样方法。"""
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
