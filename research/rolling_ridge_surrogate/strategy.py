"""用岭回归代理模型估计代码对训练期 Sharpe 的边际影响。"""

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
)

METHOD = "rolling_ridge_surrogate"
OUTPUT_DIRECTORY = Path(__file__).with_name("output")
RIDGE_PENALTY = 1.0


def select_pool(
    evaluator: PoolEvaluator,
    universe_codes: tuple[str, ...],
    eligible_codes: tuple[str, ...],
    generator: np.random.Generator,
) -> SelectionResult:
    """对组合成员矩阵拟合岭回归并选取正向系数最高代码。"""
    evaluate_random_pools(evaluator, eligible_codes, generator)
    coalitions = list(evaluator.scores)
    features = np.asarray(
        [
            [float(code in coalition) for code in eligible_codes]
            for coalition in coalitions
        ]
    )
    targets = np.asarray(
        [evaluator.scores[codes] for codes in coalitions]
    )
    centered_features = features - features.mean(axis=0)
    centered_targets = targets - targets.mean()
    gram = centered_features.T @ centered_features
    coefficients = np.linalg.solve(
        gram + RIDGE_PENALTY * np.eye(len(eligible_codes)),
        centered_features.T @ centered_targets,
    )
    scores = dict(
        zip(eligible_codes, coefficients.tolist(), strict=True)
    )
    return ranked_code_selection(
        evaluator,
        scores,
        universe_codes,
        eligible_codes,
        score_name="ridge_coefficient",
    )


def run(
    session: Any,
    *,
    start_date: str = "2022-01-01",
    end_date: str = "2026-07-26",
    evaluation_count: int = EVALUATION_COUNT,
    random_seed: int = RANDOM_SEED,
) -> RollingResult:
    """运行滚动岭回归代理方法。"""
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
