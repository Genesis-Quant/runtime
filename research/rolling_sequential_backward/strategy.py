"""逐步排除低贡献代码的滚动后向选池方法。"""

from pathlib import Path
from typing import Any

import numpy as np

from research.rolling_common import (
    EVALUATION_COUNT,
    RANDOM_SEED,
    PoolEvaluator,
    RollingResult,
    SelectionResult,
    sampling_universe_is_valid,
)
from research.rolling_entry import run_and_save, run_method
from research.rolling_search import (
    code_statistics,
    evaluate_random_pools,
    ranked_code_selection,
    sample_unseen_pool,
)

METHOD = "rolling_sequential_backward"
OUTPUT_DIRECTORY = Path(__file__).with_name("output")
ELIMINATION_INTERVAL = 5


def select_pool(
    evaluator: PoolEvaluator,
    universe_codes: tuple[str, ...],
    eligible_codes: tuple[str, ...],
    generator: np.random.Generator,
) -> SelectionResult:
    """每 5 次评估淘汰当前贡献最低的一只 ETF。"""
    warmup = min(evaluator.evaluation_limit, 20)
    evaluate_random_pools(
        evaluator,
        eligible_codes,
        generator,
        warmup,
        phase="warmup",
    )
    eliminated: list[str] = []
    elimination_finished = False
    steps_since_elimination = ELIMINATION_INTERVAL
    # 至少保留 18 只候选，确保后续仍有足够多的不重复组合完成
    # 默认的 100 次不重复评估。
    maximum_eliminations = max(0, len(eligible_codes) - 18)
    while evaluator.evaluation_count < evaluator.evaluation_limit:
        if (
            not elimination_finished
            and steps_since_elimination >= ELIMINATION_INTERVAL
            and len(eliminated) < maximum_eliminations
        ):
            statistics = code_statistics(
                evaluator,
                universe_codes,
                eligible_codes,
            )
            candidates = statistics.loc[
                ~statistics["code"].isin(eliminated)
                & statistics["contribution"].notna()
            ].sort_values(
                ["contribution", "code"],
                ascending=[True, True],
            )
            for code in candidates["code"].astype(str):
                allowed = tuple(
                    candidate
                    for candidate in eligible_codes
                    if candidate not in (*eliminated, code)
                )
                if sampling_universe_is_valid(
                    allowed,
                    evaluator.correlations,
                ):
                    eliminated.append(code)
                    steps_since_elimination = 0
                    break
            else:
                elimination_finished = True

        allowed = tuple(
            code
            for code in eligible_codes
            if code not in eliminated
        )
        proposal = sample_unseen_pool(
            evaluator,
            generator,
            allowed,
            set(evaluator.scores),
        )
        evaluator.evaluate(
            proposal,
            phase="backward",
            eliminated_count=len(eliminated),
        )
        steps_since_elimination += 1

    statistics = code_statistics(
        evaluator,
        universe_codes,
        eligible_codes,
    ).set_index("code")
    scores = statistics["contribution"].to_dict()
    for code in eliminated:
        scores[code] = -np.inf
    extras = {
        code: {
            "eliminated": code in eliminated,
            "elimination_order": (
                eliminated.index(code) + 1
                if code in eliminated
                else np.nan
            ),
        }
        for code in universe_codes
    }
    return ranked_code_selection(
        evaluator,
        scores,
        universe_codes,
        eligible_codes,
        score_name="retained_contribution",
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
    """运行滚动顺序后向方法。"""
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
