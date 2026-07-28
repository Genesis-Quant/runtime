"""滚动 ETF 池搜索方法共用的组合操作。"""

from collections.abc import Mapping, Sequence
from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd

from research.rolling_common import (
    CODE_GROUP,
    GROUP_QUOTAS,
    PoolEvaluator,
    SelectionResult,
    canonical_pool,
    group_codes,
    group_correlation_is_valid,
    sample_pool,
    sample_unseen_pool,
)


def evaluate_random_pools(
    evaluator: PoolEvaluator,
    eligible_codes: tuple[str, ...],
    generator: np.random.Generator,
    count: int | None = None,
    *,
    phase: str = "random",
) -> None:
    """评估指定数量的新随机组合。"""
    target = evaluator.evaluation_limit
    if count is not None:
        target = min(target, evaluator.evaluation_count + count)
    while evaluator.evaluation_count < target:
        coalition = sample_unseen_pool(
            evaluator,
            generator,
            eligible_codes,
            set(evaluator.scores),
        )
        evaluator.evaluate(coalition, phase=phase)


def best_pool(evaluator: PoolEvaluator) -> tuple[str, ...]:
    """返回目前 Sharpe 最高的已评估组合。"""
    if not evaluator.scores:
        raise RuntimeError("尚未评估任何 ETF 组合")
    return max(
        evaluator.scores,
        key=lambda codes: evaluator.scores[codes],
    )


def one_swap(
    evaluator: PoolEvaluator,
    codes: Sequence[str],
    eligible_codes: Sequence[str],
    generator: np.random.Generator,
) -> tuple[tuple[str, ...], str, str]:
    """在同一类别内随机替换一只 ETF。"""
    current = canonical_pool(codes)
    for _ in range(1_000):
        removed = str(generator.choice(current))
        required = tuple(
            code for code in current if code != removed
        )
        proposal = sample_pool(
            evaluator,
            generator,
            eligible_codes,
            required_codes=required,
        )
        added = next(
            (
                code
                for code in proposal
                if code not in current
            ),
            None,
        )
        if added is not None:
            return proposal, removed, added
    raise RuntimeError("无法生成满足约束的单次替换组合")


def unseen_one_swap(
    evaluator: PoolEvaluator,
    codes: Sequence[str],
    eligible_codes: Sequence[str],
    generator: np.random.Generator,
    seen: set[tuple[str, ...]],
    *,
    forbidden: set[tuple[str, str]] | None = None,
    maximum_attempts: int = 10_000,
) -> tuple[tuple[str, ...], str, str]:
    """生成尚未评估且不在禁忌表中的单次替换邻居。"""
    for _ in range(maximum_attempts):
        proposal, removed, added = one_swap(
            evaluator,
            codes,
            eligible_codes,
            generator,
        )
        if proposal in seen:
            continue
        if forbidden is not None and (removed, added) in forbidden:
            continue
        return proposal, removed, added
    raise RuntimeError("无法生成新的单次替换组合")


def weighted_pool(
    evaluator: PoolEvaluator,
    eligible_codes: Sequence[str],
    weights: Sequence[float],
    generator: np.random.Generator,
) -> tuple[str, ...]:
    """按类别分别使用非负权重无放回抽取 ETF。"""
    probabilities = np.asarray(weights, dtype=float)
    if probabilities.shape != (len(eligible_codes),):
        raise ValueError("weights 长度必须与 eligible_codes 一致")
    probabilities = np.maximum(probabilities, 1e-12)
    return sample_pool(
        evaluator,
        generator,
        eligible_codes,
        weights=dict(
            zip(
                eligible_codes,
                probabilities.tolist(),
                strict=True,
            )
        ),
    )


def unseen_weighted_pool(
    evaluator: PoolEvaluator,
    eligible_codes: Sequence[str],
    weights: Sequence[float],
    generator: np.random.Generator,
    seen: set[tuple[str, ...]],
    *,
    maximum_attempts: int = 10_000,
) -> tuple[str, ...]:
    """按权重生成一个尚未评估的组合。"""
    for _ in range(maximum_attempts):
        proposal = weighted_pool(
            evaluator,
            eligible_codes,
            weights,
            generator,
        )
        if proposal not in seen:
            return proposal
    return sample_unseen_pool(
        evaluator,
        generator,
        eligible_codes,
        seen,
    )


def crossover(
    evaluator: PoolEvaluator,
    left: Sequence[str],
    right: Sequence[str],
    eligible_codes: Sequence[str],
    generator: np.random.Generator,
) -> tuple[str, ...]:
    """按父代成员权重生成满足类别和相关性约束的子代。"""
    left_set = set(left)
    right_set = set(right)
    weights = [
        (
            4.0
            if code in left_set and code in right_set
            else 2.0
            if code in left_set or code in right_set
            else 1.0
        )
        for code in eligible_codes
    ]
    return weighted_pool(
        evaluator,
        eligible_codes,
        weights,
        generator,
    )


def code_statistics(
    evaluator: PoolEvaluator,
    universe_codes: Sequence[str],
    eligible_codes: Sequence[str],
) -> pd.DataFrame:
    """汇总代码入选/未入选时的组合表现及相对贡献。"""
    coalitions = list(evaluator.scores)
    scores = np.asarray(
        [evaluator.scores[codes] for codes in coalitions],
        dtype=float,
    )
    eligible_set = set(eligible_codes)
    records: list[dict[str, Any]] = []
    for code in universe_codes:
        included = np.fromiter(
            (code in codes for codes in coalitions),
            dtype=bool,
            count=len(coalitions),
        )
        included_scores = scores[included]
        excluded_scores = scores[~included]
        eligible = code in eligible_set
        included_mean = (
            float(included_scores.mean())
            if included_scores.size
            else np.nan
        )
        excluded_mean = (
            float(excluded_scores.mean())
            if excluded_scores.size
            else np.nan
        )
        contribution = (
            included_mean - excluded_mean
            if eligible
            and included_scores.size
            and excluded_scores.size
            else np.nan
        )
        records.append(
            {
                "code": code,
                "eligible": eligible,
                "included_count": int(included_scores.size),
                "excluded_count": int(excluded_scores.size),
                "included_mean_sharpe": included_mean,
                "excluded_mean_sharpe": excluded_mean,
                "contribution": contribution,
            }
        )
    return pd.DataFrame.from_records(records)


def ranked_code_selection(
    evaluator: PoolEvaluator,
    code_scores: Mapping[str, float],
    universe_codes: Sequence[str],
    eligible_codes: Sequence[str],
    *,
    score_name: str,
    extra_columns: Mapping[str, Mapping[str, Any]] | None = None,
) -> SelectionResult:
    """按类别选择总分最高且组内相关性合格的代码组合。"""
    eligible_set = set(eligible_codes)
    records: list[dict[str, Any]] = []
    for code in universe_codes:
        record = {
            "code": code,
            "eligible": code in eligible_set,
            score_name: (
                float(code_scores[code])
                if code in code_scores
                else np.nan
            ),
        }
        if extra_columns is not None and code in extra_columns:
            record.update(extra_columns[code])
        records.append(record)

    diagnostics = pd.DataFrame.from_records(records).sort_values(
        ["eligible", score_name, "code"],
        ascending=[False, False, True],
        ignore_index=True,
    )
    diagnostics["rank"] = pd.Series(
        pd.NA,
        index=diagnostics.index,
        dtype="Int64",
    )
    eligible_rows = diagnostics["eligible"]
    diagnostics.loc[eligible_rows, "rank"] = np.arange(
        1,
        int(eligible_rows.sum()) + 1,
    )
    eligible_by_group = group_codes(eligible_codes)
    selected_codes: list[str] = []
    for group, quota in GROUP_QUOTAS.items():
        candidates = eligible_by_group[group]
        valid_combinations = [
            coalition
            for coalition in combinations(candidates, quota)
            if group_correlation_is_valid(
                coalition,
                evaluator.correlations,
            )
        ]
        if not valid_combinations:
            raise RuntimeError(
                f"{group} 不存在满足相关性约束的候选组合"
            )

        def combination_score(
            coalition: tuple[str, ...],
        ) -> float:
            values = np.asarray(
                [code_scores.get(code, -np.inf) for code in coalition],
                dtype=float,
            )
            values = np.where(np.isnan(values), -np.inf, values)
            return float(values.sum())

        selected_codes.extend(
            sorted(
                valid_combinations,
                key=lambda coalition: (
                    -combination_score(coalition),
                    coalition,
                ),
            )[0]
        )

    selected = canonical_pool(selected_codes)
    diagnostics["group"] = diagnostics["code"].map(CODE_GROUP)
    diagnostics["selected"] = diagnostics["code"].isin(selected)
    return SelectionResult(
        codes=selected,
        diagnostics=diagnostics,
    )


def best_pool_selection(
    evaluator: PoolEvaluator,
    *,
    extra: Mapping[str, Any] | None = None,
) -> SelectionResult:
    """以当前最佳已评估组合构造选择结果。"""
    codes = best_pool(evaluator)
    record = {
        "best_evaluation": next(
            index
            for index, row in enumerate(evaluator.records, start=1)
            if row["codes"] == "|".join(codes)
        ),
        "training_sharpe": evaluator.scores[codes],
        "codes": "|".join(codes),
    }
    if extra is not None:
        record.update(extra)
    return SelectionResult(
        codes=codes,
        diagnostics=pd.DataFrame.from_records([record]),
    )


def score_array(
    evaluator: PoolEvaluator,
    pools: Sequence[tuple[str, ...]],
) -> np.ndarray:
    """按组合顺序返回已评估 Sharpe。"""
    return np.asarray(
        [evaluator.scores[codes] for codes in pools],
        dtype=float,
    )


__all__ = [
    "best_pool",
    "best_pool_selection",
    "code_statistics",
    "crossover",
    "evaluate_random_pools",
    "one_swap",
    "ranked_code_selection",
    "score_array",
    "unseen_one_swap",
    "unseen_weighted_pool",
    "weighted_pool",
]
