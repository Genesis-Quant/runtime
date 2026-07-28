"""逐步锁定高贡献代码的滚动前向选池方法。"""

from pathlib import Path
from typing import Any

import numpy as np

from research.rolling_common import (
    EVALUATION_COUNT,
    POOL_SIZE,
    RANDOM_SEED,
    PoolEvaluator,
    RollingResult,
    SelectionResult,
    count_pool_completions,
    sample_unseen_pool,
)
from research.rolling_entry import run_and_save, run_method
from research.rolling_search import (
    code_statistics,
    evaluate_random_pools,
    ranked_code_selection,
)

METHOD = "rolling_sequential_forward"
OUTPUT_DIRECTORY = Path(__file__).with_name("output")
LOCK_INTERVAL = 5


def constrained_pool(
    locked: list[str],
    eligible_codes: tuple[str, ...],
    evaluator: PoolEvaluator,
    generator: np.random.Generator,
) -> tuple[str, ...]:
    """生成包含全部已锁定代码的新组合。"""
    return sample_unseen_pool(
        evaluator,
        generator,
        eligible_codes,
        set(evaluator.scores),
        required_codes=locked,
    )


def select_pool(
    evaluator: PoolEvaluator,
    universe_codes: tuple[str, ...],
    eligible_codes: tuple[str, ...],
    generator: np.random.Generator,
) -> SelectionResult:
    """每 5 次评估锁定当前贡献最高且尚未锁定的一只 ETF。"""
    warmup = min(evaluator.evaluation_limit, 20)
    evaluate_random_pools(
        evaluator,
        eligible_codes,
        generator,
        warmup,
        phase="warmup",
    )
    locked: list[str] = []
    locking_finished = False
    steps_since_lock = LOCK_INTERVAL
    while evaluator.evaluation_count < evaluator.evaluation_limit:
        if (
            not locking_finished
            and steps_since_lock >= LOCK_INTERVAL
            and len(locked) < POOL_SIZE - 2
        ):
            statistics = code_statistics(
                evaluator,
                universe_codes,
                eligible_codes,
            )
            candidates = statistics.loc[
                ~statistics["code"].isin(locked)
                & statistics["contribution"].notna()
            ].sort_values(
                ["contribution", "code"],
                ascending=[False, True],
            )
            for code in candidates["code"].astype(str):
                required = (*locked, code)
                completion_count = count_pool_completions(
                    required,
                    eligible_codes,
                    evaluator.correlations,
                )
                seen_count = sum(
                    set(required).issubset(pool)
                    for pool in evaluator.scores
                )
                remaining_evaluations = (
                    evaluator.evaluation_limit
                    - evaluator.evaluation_count
                )
                if (
                    completion_count - seen_count
                    >= remaining_evaluations
                ):
                    locked.append(code)
                    steps_since_lock = 0
                    break
            else:
                locking_finished = True
        proposal = constrained_pool(
            locked,
            eligible_codes,
            evaluator,
            generator,
        )
        evaluator.evaluate(
            proposal,
            phase="forward",
            locked_count=len(locked),
        )
        steps_since_lock += 1

    statistics = code_statistics(
        evaluator,
        universe_codes,
        eligible_codes,
    ).set_index("code")
    scores = statistics["contribution"].to_dict()
    extras = {
        code: {
            "locked": code in locked,
            "lock_order": (
                locked.index(code) + 1 if code in locked else np.nan
            ),
        }
        for code in universe_codes
    }
    return ranked_code_selection(
        evaluator,
        scores,
        universe_codes,
        eligible_codes,
        score_name="estimated_contribution",
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
    """运行滚动顺序前向方法。"""
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
