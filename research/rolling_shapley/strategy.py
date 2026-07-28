"""按固定规模联盟的相对 Shapley 分数滚动选择 ETF 池。"""

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from core.database import create_session
from research.rolling_common import (
    CODE_GROUP,
    EVALUATION_COUNT,
    GROUP_QUOTAS,
    RANDOM_SEED,
    UNIVERSE_CODES,
    PoolEvaluator,
    RollingResult,
    SelectionResult,
    run_rolling_method,
    save_result as save_rolling_result,
)
from research.rolling_search import (
    code_statistics,
    evaluate_random_pools,
    ranked_code_selection,
)

METHOD = "rolling_shapley"
OUTPUT_DIRECTORY = Path(__file__).with_name("output")


def select_pool(
    evaluator: PoolEvaluator,
    universe_codes: tuple[str, ...],
    eligible_codes: tuple[str, ...],
    generator: np.random.Generator,
) -> SelectionResult:
    """按入选与未入选组合的平均 Sharpe 差分组选择 ETF。"""
    evaluate_random_pools(
        evaluator,
        eligible_codes,
        generator,
    )
    diagnostics = code_statistics(
        evaluator,
        universe_codes,
        eligible_codes,
    )
    eligible_group_counts = (
        pd.Series(
            [CODE_GROUP[code] for code in eligible_codes]
        )
        .value_counts()
        .to_dict()
    )
    mandatory_codes = {
        code
        for code in eligible_codes
        if eligible_group_counts[CODE_GROUP[code]]
        == GROUP_QUOTAS[CODE_GROUP[code]]
    }
    included_variance: dict[str, float] = {}
    excluded_variance: dict[str, float] = {}
    for code in eligible_codes:
        included_scores = np.asarray(
            [
                score
                for codes, score in evaluator.scores.items()
                if code in codes
            ]
        )
        excluded_scores = np.asarray(
            [
                score
                for codes, score in evaluator.scores.items()
                if code not in codes
            ]
        )
        included_variance[code] = (
            float(included_scores.var(ddof=1))
            if included_scores.size > 1
            else 0.0
        )
        excluded_variance[code] = (
            float(excluded_scores.var(ddof=1))
            if excluded_scores.size > 1
            else 0.0
        )

    diagnostics["shapley_score"] = diagnostics["contribution"]
    diagnostics.loc[
        diagnostics["code"].isin(mandatory_codes),
        "shapley_score",
    ] = 0.0

    def calculate_standard_error(row: pd.Series) -> float:
        """计算单只 ETF 相对贡献估计的标准误。"""
        code = str(row["code"])
        if code in mandatory_codes:
            return 0.0
        if (
            not bool(row["eligible"])
            or row["included_count"] == 0
            or row["excluded_count"] == 0
        ):
            return np.nan
        return math.sqrt(
            included_variance[code] / row["included_count"]
            + excluded_variance[code] / row["excluded_count"]
        )

    diagnostics["standard_error"] = diagnostics.apply(
        calculate_standard_error,
        axis=1,
    )
    indexed = diagnostics.set_index("code")
    extras = indexed[
        [
            "included_count",
            "excluded_count",
            "included_mean_sharpe",
            "excluded_mean_sharpe",
            "contribution",
            "standard_error",
        ]
    ].to_dict("index")
    return ranked_code_selection(
        evaluator,
        indexed["shapley_score"].to_dict(),
        universe_codes,
        eligible_codes,
        score_name="shapley_score",
        extra_columns=extras,
    )


def run_rolling_shapley(
    session: Any,
    *,
    start_date: str = "2022-01-01",
    end_date: str = "2026-07-26",
    evaluation_count: int = EVALUATION_COUNT,
    random_seed: int = RANDOM_SEED,
) -> RollingResult:
    """运行滚动相对 Shapley 选池及下一自然半年样本外回测。"""
    return run_rolling_method(
        session,
        METHOD,
        select_pool,
        start_date=start_date,
        end_date=end_date,
        evaluation_count=evaluation_count,
        random_seed=random_seed,
        universe_codes=UNIVERSE_CODES,
    )


def save_result(
    result: RollingResult,
    output_directory: Path = OUTPUT_DIRECTORY,
) -> None:
    """保存滚动相对 Shapley 方法结果及兼容旧名称的明细。"""
    save_rolling_result(result, output_directory)
    result.diagnostics.to_csv(
        output_directory / "shapley_scores.csv",
        index=False,
    )
    result.evaluations.to_csv(
        output_directory / "trial_scores.csv",
        index=False,
    )


def main() -> None:
    """以默认参数运行并保存滚动相对 Shapley 研究。"""
    session = create_session()
    try:
        result = run_rolling_shapley(session)
    finally:
        session.close()
    save_result(result)
    print("overall_performance:", result.performance)


if __name__ == "__main__":
    main()
