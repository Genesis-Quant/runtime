"""按代码收益后验抽样引导组合搜索的滚动选池方法。"""

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

METHOD = "rolling_thompson_sampling"
OUTPUT_DIRECTORY = Path(__file__).with_name("output")


def posterior_parameters(
    evaluator: PoolEvaluator,
    eligible_codes: tuple[str, ...],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """从代码所在组合的 Sharpe 样本构造正态后验近似。"""
    all_scores = np.asarray(list(evaluator.scores.values()))
    prior_scale = max(float(all_scores.std(ddof=0)), 0.1)
    counts: list[int] = []
    means: list[float] = []
    standard_errors: list[float] = []
    for code in eligible_codes:
        samples = np.asarray(
            [
                score
                for codes, score in evaluator.scores.items()
                if code in codes
            ]
        )
        counts.append(int(samples.size))
        means.append(
            float(samples.mean())
            if samples.size
            else float(all_scores.mean())
        )
        standard_errors.append(
            prior_scale / np.sqrt(max(samples.size, 1))
        )
    return (
        np.asarray(counts),
        np.asarray(means),
        np.asarray(standard_errors),
    )


def select_pool(
    evaluator: PoolEvaluator,
    universe_codes: tuple[str, ...],
    eligible_codes: tuple[str, ...],
    generator: np.random.Generator,
) -> SelectionResult:
    """用 Thompson 抽样产生组合，按最终后验均值选池。"""
    warmup = min(evaluator.evaluation_limit, 20)
    evaluate_random_pools(
        evaluator,
        eligible_codes,
        generator,
        warmup,
        phase="warmup",
    )
    while evaluator.evaluation_count < evaluator.evaluation_limit:
        _, means, standard_errors = posterior_parameters(
            evaluator,
            eligible_codes,
        )
        sampled_values = generator.normal(means, standard_errors)
        centered = sampled_values - sampled_values.max()
        weights = np.exp(centered / 0.35)
        proposal = unseen_weighted_pool(
            evaluator,
            eligible_codes,
            weights,
            generator,
            set(evaluator.scores),
        )
        evaluator.evaluate(proposal, phase="thompson")

    counts, means, standard_errors = posterior_parameters(
        evaluator,
        eligible_codes,
    )
    scores = dict(zip(eligible_codes, means.tolist(), strict=True))
    extras = {
        code: {
            "observations": int(count),
            "posterior_standard_error": float(error),
        }
        for code, count, error in zip(
            eligible_codes,
            counts,
            standard_errors,
            strict=True,
        )
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
    """运行滚动 Thompson 采样方法。"""
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
