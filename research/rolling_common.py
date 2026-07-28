"""滚动 ETF 池研究的公共回测、指标和输出逻辑。"""

import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from core.workers.fund_daily import FUND_CODES
from research import get_data, run_strategy

FACTOR_NAMES = [
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "adj_factor",
    "vol",
]

START_DATE = "2022-01-01"
END_DATE = "2026-07-26"
HISTORY_BUFFER_DAYS = 120

INITIAL_CASH = 100_000.0
MOMENTUM_WINDOW = 21
SELECT_COUNT = 4
RISK_WINDOW = 20
MAX_HISTORY_ROWS = 90
TARGET_VOLATILITY = 0.09
MAX_INVESTED_RATIO = 0.99

EVALUATION_COUNT = 100
RANDOM_SEED = 20260728
MINIMUM_SHARPE = -10.0
MINIMUM_TRAINING_ROWS = 60
MINIMUM_CORRELATION_ROWS = 60
MAXIMUM_WITHIN_GROUP_CORRELATION = 0.92

# FUND_CODES 中 159941.SZ 与 513100.SH 都跟踪纳斯达克 100。保留原策略
# 使用的 513100.SH，排除重复暴露，使研究范围固定为 72 只 ETF。
UNIVERSE_CODES = tuple(
    code for code in FUND_CODES if code != "159941.SZ"
)

# FUND_CODES 按 A 股、商品、港股、全球经济体分段定义。
ETF_GROUPS = {
    "commodity": tuple(FUND_CODES[44:50]),
    "global": tuple(
        code for code in FUND_CODES[55:] if code != "159941.SZ"
    ),
    "hong_kong": tuple(FUND_CODES[50:55]),
    "a_share": tuple(FUND_CODES[:44]),
}
GROUP_QUOTAS = {
    "commodity": 4,
    "global": 4,
    "hong_kong": 2,
    "a_share": 3,
}
POOL_SIZE = sum(GROUP_QUOTAS.values())
CODE_GROUP = {
    code: group
    for group, group_codes in ETF_GROUPS.items()
    for code in group_codes
}

if set(CODE_GROUP) != set(UNIVERSE_CODES):
    raise RuntimeError("ETF 分类必须完整且不重复地覆盖研究范围")


@dataclass
class SelectionResult:
    """一次训练区间选池的结果和方法特有诊断数据。"""

    codes: tuple[str, ...]
    diagnostics: pd.DataFrame


@dataclass
class RollingResult:
    """一种滚动选池方法产生的完整结果。"""

    method: str
    net_value: pd.Series
    period_pools: pd.DataFrame
    period_performance: pd.DataFrame
    evaluations: pd.DataFrame
    diagnostics: pd.DataFrame
    performance: dict[str, Any]
    configuration: dict[str, Any]


@dataclass(frozen=True)
class RollingPeriod:
    """一组连续的半年训练区间和半年持有区间。"""

    training_start: pd.Timestamp
    training_end: pd.Timestamp
    holding_start: pd.Timestamp
    holding_end: pd.Timestamp

    @property
    def training_period(self) -> str:
        """返回训练区间标识。"""
        return (
            f"{self.training_start:%Y-%m-%d}/"
            f"{self.training_end:%Y-%m-%d}"
        )

    @property
    def holding_period(self) -> str:
        """返回持有区间标识。"""
        return (
            f"{self.holding_start:%Y-%m-%d}/"
            f"{self.holding_end:%Y-%m-%d}"
        )


@dataclass
class PoolEvaluator:
    """在一个训练区间内按统一策略评估 ETF 组合。"""

    session: Any
    method: str
    period: RollingPeriod
    evaluation_limit: int
    correlations: pd.DataFrame
    records: list[dict[str, Any]] = field(default_factory=list)
    scores: dict[tuple[str, ...], float] = field(default_factory=dict)

    @property
    def evaluation_count(self) -> int:
        """返回实际执行回测的不同组合数。"""
        return len(self.scores)

    def evaluate(
        self,
        codes: Sequence[str],
        **metadata: Any,
    ) -> float:
        """评估一个新组合；重复组合直接复用分数且不消耗预算。"""
        coalition = canonical_pool(codes)
        validate_pool(coalition, self.correlations)
        if coalition in self.scores:
            return self.scores[coalition]
        if self.evaluation_count >= self.evaluation_limit:
            raise RuntimeError("组合评估次数已达到训练区间上限")

        net_value = run_strategy(
            self.session,
            coalition,
            self.period.training_start,
            self.period.training_end,
            INITIAL_CASH,
            MOMENTUM_WINDOW,
            SELECT_COUNT,
            RISK_WINDOW,
            MAX_HISTORY_ROWS,
            TARGET_VOLATILITY,
            MAX_INVESTED_RATIO,
        )
        score = calculate_sharpe(net_value)
        self.scores[coalition] = score
        self.records.append(
            {
                "method": self.method,
                "training_period": self.period.training_period,
                "holding_period": self.period.holding_period,
                "evaluation": self.evaluation_count,
                "codes": "|".join(coalition),
                "sharpe": score,
                "maximum_within_group_correlation":
                    maximum_within_group_correlation(
                        coalition,
                        self.correlations,
                    ),
                **metadata,
            }
        )
        if (
            self.evaluation_count % 10 == 0
            or self.evaluation_count == self.evaluation_limit
        ):
            print(
                f"method={self.method}, "
                f"training_period={self.period.training_period}, "
                f"completed={self.evaluation_count}/"
                f"{self.evaluation_limit}"
            )
        return score


Selector = Callable[
    [
        PoolEvaluator,
        tuple[str, ...],
        tuple[str, ...],
        np.random.Generator,
    ],
    SelectionResult,
]


def canonical_pool(codes: Sequence[str]) -> tuple[str, ...]:
    """把组合转成可比较、可缓存的唯一有序形式。"""
    return tuple(sorted(set(codes)))


def group_codes(
    codes: Sequence[str],
) -> dict[str, tuple[str, ...]]:
    """按资产类别拆分代码。"""
    grouped = {group: [] for group in GROUP_QUOTAS}
    for code in codes:
        try:
            grouped[CODE_GROUP[code]].append(code)
        except KeyError as error:
            raise ValueError(f"ETF 未配置资产类别：{code}") from error
    return {
        group: tuple(values)
        for group, values in grouped.items()
    }


def group_correlation_is_valid(
    codes: Sequence[str],
    correlations: pd.DataFrame,
) -> bool:
    """检查同类 ETF 是否都有足够数据且相关性低于阈值。"""
    selected = tuple(codes)
    if len(selected) < 2:
        return True
    values = correlations.loc[
        list(selected),
        list(selected),
    ].to_numpy(dtype=float)
    pairwise = values[np.triu_indices(len(selected), 1)]
    return bool(
        np.isfinite(pairwise).all()
        and (pairwise < MAXIMUM_WITHIN_GROUP_CORRELATION).all()
    )


def pool_is_valid(
    codes: Sequence[str],
    correlations: pd.DataFrame,
) -> bool:
    """检查组合规模、类别配额和组内相关性约束。"""
    coalition = canonical_pool(codes)
    if len(coalition) != POOL_SIZE:
        return False
    grouped = group_codes(coalition)
    return all(
        len(grouped[group]) == quota
        and group_correlation_is_valid(
            grouped[group],
            correlations,
        )
        for group, quota in GROUP_QUOTAS.items()
    )


def validate_pool(
    codes: Sequence[str],
    correlations: pd.DataFrame,
) -> None:
    """校验一个待评估或最终输出的 ETF 池。"""
    coalition = canonical_pool(codes)
    if len(coalition) != POOL_SIZE:
        raise ValueError(
            f"ETF 池必须恰好包含 {POOL_SIZE} 只不同 ETF"
        )
    grouped = group_codes(coalition)
    counts = {
        group: len(values)
        for group, values in grouped.items()
    }
    if counts != GROUP_QUOTAS:
        raise ValueError(
            f"ETF 池类别数量不符合 {GROUP_QUOTAS}：{counts}"
        )
    invalid_groups = [
        group
        for group, values in grouped.items()
        if not group_correlation_is_valid(values, correlations)
    ]
    if invalid_groups:
        raise ValueError(
            "ETF 池存在组内相关性缺失或相关性达到 "
            f"{MAXIMUM_WITHIN_GROUP_CORRELATION:.2f} 的类别："
            f"{invalid_groups}"
        )


def _sample_group(
    generator: np.random.Generator,
    eligible_codes: Sequence[str],
    required_codes: Sequence[str],
    quota: int,
    correlations: pd.DataFrame,
    weights: dict[str, float] | None,
    *,
    maximum_attempts: int = 1_000,
) -> tuple[str, ...]:
    """抽取一个满足配额与相关性约束的类别子组合。"""
    required = canonical_pool(required_codes)
    if len(required) > quota:
        raise ValueError("必选 ETF 数量超过类别配额")
    if not group_correlation_is_valid(required, correlations):
        raise ValueError("必选 ETF 的组内相关性过高")

    available = tuple(
        code for code in eligible_codes if code not in required
    )
    remaining = quota - len(required)
    if remaining == 0:
        return required
    if len(available) < remaining:
        raise RuntimeError("可交易 ETF 数量不足以满足类别配额")

    probabilities: np.ndarray | None = None
    if weights is not None:
        probabilities = np.asarray(
            [
                max(float(weights.get(code, 0.0)), 1e-12)
                for code in available
            ],
            dtype=float,
        )
        probabilities /= probabilities.sum()

    for _ in range(maximum_attempts):
        selected = generator.choice(
            available,
            size=remaining,
            replace=False,
            p=probabilities,
        ).tolist()
        proposal = canonical_pool((*required, *selected))
        if group_correlation_is_valid(proposal, correlations):
            return proposal

    for selected in combinations(available, remaining):
        proposal = canonical_pool((*required, *selected))
        if group_correlation_is_valid(proposal, correlations):
            return proposal
    raise RuntimeError("不存在满足组内相关性约束的类别子组合")


def sample_pool(
    evaluator: PoolEvaluator,
    generator: np.random.Generator,
    eligible_codes: Sequence[str],
    *,
    weights: dict[str, float] | None = None,
    required_codes: Sequence[str] = (),
) -> tuple[str, ...]:
    """按类别配额抽取 ETF，并拒绝组内高相关组合。"""
    eligible_by_group = group_codes(eligible_codes)
    required_by_group = group_codes(required_codes)
    selected: list[str] = []
    for group, quota in GROUP_QUOTAS.items():
        selected.extend(
            _sample_group(
                generator,
                eligible_by_group[group],
                required_by_group[group],
                quota,
                evaluator.correlations,
                weights,
            )
        )
    coalition = canonical_pool(selected)
    validate_pool(coalition, evaluator.correlations)
    return coalition


def sampling_universe_is_valid(
    eligible_codes: Sequence[str],
    correlations: pd.DataFrame,
) -> bool:
    """检查可交易范围能否构造至少一个满足约束的组合。"""
    eligible_by_group = group_codes(eligible_codes)
    for group, quota in GROUP_QUOTAS.items():
        candidates = eligible_by_group[group]
        if len(candidates) < quota:
            return False
        if not any(
            group_correlation_is_valid(selected, correlations)
            for selected in combinations(candidates, quota)
        ):
            return False
    return True


def count_pool_completions(
    required_codes: Sequence[str],
    eligible_codes: Sequence[str],
    correlations: pd.DataFrame,
) -> int:
    """计算包含必选代码的合法组合总数。"""
    required_by_group = group_codes(required_codes)
    eligible_by_group = group_codes(eligible_codes)
    total = 1
    for group, quota in GROUP_QUOTAS.items():
        required = required_by_group[group]
        if (
            len(required) > quota
            or not group_correlation_is_valid(
                required,
                correlations,
            )
        ):
            return 0
        available = tuple(
            code
            for code in eligible_by_group[group]
            if code not in required
        )
        remaining = quota - len(required)
        valid_count = sum(
            group_correlation_is_valid(
                (*required, *selected),
                correlations,
            )
            for selected in combinations(available, remaining)
        )
        if valid_count == 0:
            return 0
        total *= valid_count
    return total


def validate_sampling_universe(
    eligible_codes: Sequence[str],
    correlations: pd.DataFrame,
) -> None:
    """校验训练区间是否能满足全部类别和相关性约束。"""
    eligible_by_group = group_codes(eligible_codes)
    errors: list[str] = []
    for group, quota in GROUP_QUOTAS.items():
        candidates = eligible_by_group[group]
        if len(candidates) < quota:
            errors.append(
                f"{group} 只有 {len(candidates)} 只，至少需要 {quota} 只"
            )
            continue
        if not any(
            group_correlation_is_valid(selected, correlations)
            for selected in combinations(candidates, quota)
        ):
            errors.append(
                f"{group} 不存在相关性均低于 "
                f"{MAXIMUM_WITHIN_GROUP_CORRELATION:.2f} 的 "
                f"{quota} 只组合"
            )
    if errors:
        raise RuntimeError("；".join(errors))


def maximum_within_group_correlation(
    codes: Sequence[str],
    correlations: pd.DataFrame,
) -> float:
    """返回组合中各类别内最大的相关系数。"""
    maximum = 0.0
    for selected in group_codes(codes).values():
        if len(selected) < 2:
            continue
        values = correlations.loc[
            list(selected),
            list(selected),
        ].to_numpy(dtype=float)
        pairwise = values[np.triu_indices(len(selected), 1)]
        if pairwise.size:
            maximum = max(maximum, float(pairwise.max()))
    return maximum


def get_training_correlations(
    session: Any,
    training_start: pd.Timestamp,
    training_end: pd.Timestamp,
    eligible_codes: Sequence[str],
) -> pd.DataFrame:
    """计算训练区间复权日收益相关矩阵。"""
    session.upload(
        {
            "rollingCorrelationCodeNames": np.asarray(
                eligible_codes,
                dtype=str,
            ),
            "rollingCorrelationStart":
                training_start.to_datetime64().astype("datetime64[D]"),
            "rollingCorrelationEnd":
                training_end.to_datetime64().astype("datetime64[D]"),
        }
    )
    prices = session.run(
        """
        select time, code, close
        from strategyMarketData
        where
            date(time) >= rollingCorrelationStart,
            date(time) <= rollingCorrelationEnd,
            code in symbol(rollingCorrelationCodeNames)
        order by time, code
        """
    )
    close = prices.pivot(
        index="time",
        columns="code",
        values="close",
    )
    return close.pct_change(fill_method=None).corr(
        min_periods=MINIMUM_CORRELATION_ROWS,
    ).reindex(
        index=eligible_codes,
        columns=eligible_codes,
    )


def sample_unseen_pool(
    evaluator: PoolEvaluator,
    generator: np.random.Generator,
    eligible_codes: Sequence[str],
    seen: set[tuple[str, ...]],
    *,
    weights: dict[str, float] | None = None,
    required_codes: Sequence[str] = (),
    maximum_attempts: int = 10_000,
) -> tuple[str, ...]:
    """抽取一个尚未评估的组合。"""
    for _ in range(maximum_attempts):
        codes = sample_pool(
            evaluator,
            generator,
            eligible_codes,
            weights=weights,
            required_codes=required_codes,
        )
        if codes not in seen:
            return codes
    raise RuntimeError("无法在限定次数内生成新的 ETF 组合")


def calculate_sharpe(net_value: pd.Series) -> float:
    """按 250 个交易日和 4% 无风险利率计算年化 Sharpe。"""
    daily_returns = net_value.pct_change().dropna()
    if daily_returns.empty:
        return MINIMUM_SHARPE

    daily_volatility = float(daily_returns.std(ddof=0))
    if daily_volatility <= 1e-12:
        return MINIMUM_SHARPE

    sharpe = (
        float(daily_returns.mean()) - 0.04 / 250
    ) / daily_volatility * math.sqrt(250)
    return sharpe if math.isfinite(sharpe) else MINIMUM_SHARPE


def calculate_performance(net_value: pd.Series) -> dict[str, Any]:
    """计算净值曲线的收益与风险指标。"""
    if net_value.empty:
        raise ValueError("净值曲线不能为空")

    daily_returns = net_value.pct_change().dropna()
    elapsed_days = (net_value.index[-1] - net_value.index[0]).days
    years = elapsed_days / 365.2425
    annual_return = (
        float(net_value.iloc[-1] / net_value.iloc[0]) ** (1 / years)
        - 1
        if years > 0
        else 0.0
    )
    max_drawdown = float(
        -(net_value / net_value.cummax() - 1).min()
    )
    annual_volatility = (
        float(daily_returns.std(ddof=0)) * math.sqrt(250)
        if not daily_returns.empty
        else 0.0
    )
    sharpe = calculate_sharpe(net_value)
    calmar = (
        annual_return / max_drawdown
        if max_drawdown > 0
        else math.inf
    )
    return {
        "start_date": net_value.index[0],
        "end_date": net_value.index[-1],
        "trading_days": len(net_value),
        "final_net_value": float(net_value.iloc[-1]),
        "annual_return": annual_return,
        "max_drawdown": max_drawdown,
        "annual_volatility": annual_volatility,
        "sharpe": sharpe,
        "calmar": calmar,
    }


def get_eligible_codes(
    session: Any,
    training_start: pd.Timestamp,
    training_end: pd.Timestamp,
    universe_codes: tuple[str, ...],
) -> tuple[str, ...]:
    """返回训练区间至少具有 60 个有效行情日的 ETF。"""
    session.upload(
        {
            "rollingUniverseCodeNames": np.asarray(
                universe_codes,
                dtype=str,
            ),
            "rollingTrainingStart":
                training_start.to_datetime64().astype("datetime64[D]"),
            "rollingTrainingEnd":
                training_end.to_datetime64().astype("datetime64[D]"),
        }
    )
    counts = session.run(
        """
        select
            code,
            count(*) as rows
        from strategyMarketData
        where
            date(time) >= rollingTrainingStart,
            date(time) <= rollingTrainingEnd,
            code in symbol(rollingUniverseCodeNames)
        group by code
        """
    )
    rows_by_code = dict(
        zip(
            counts["code"].astype(str),
            counts["rows"].astype(int),
            strict=True,
        )
    )
    eligible = tuple(
        code
        for code in universe_codes
        if rows_by_code.get(code, 0) >= MINIMUM_TRAINING_ROWS
    )
    return eligible


def build_rolling_periods(
    output_start: pd.Timestamp,
    output_end: pd.Timestamp,
) -> tuple[RollingPeriod, ...]:
    """构造以前一自然半年训练、后一自然半年持有的连续区间。"""
    holding_start = pd.Timestamp(
        year=output_start.year,
        month=1 if output_start.month <= 6 else 7,
        day=1,
    )
    periods: list[RollingPeriod] = []
    while holding_start <= output_end:
        holding_end = (
            holding_start
            + pd.DateOffset(months=6)
            - pd.Timedelta(days=1)
        )
        periods.append(
            RollingPeriod(
                training_start=(
                    holding_start - pd.DateOffset(months=6)
                ),
                training_end=holding_start - pd.Timedelta(days=1),
                holding_start=max(output_start, holding_start),
                holding_end=min(output_end, holding_end),
            )
        )
        holding_start += pd.DateOffset(months=6)
    return tuple(periods)


def compound_period_curves(
    period_curves: list[pd.Series],
) -> pd.Series:
    """把每个持有区间从 1 开始的净值连续复合。"""
    compounded: list[pd.Series] = []
    current_value = 1.0
    for curve in period_curves:
        if curve.empty:
            raise RuntimeError("持有区间净值曲线为空")
        segment = curve / float(curve.iloc[0]) * current_value
        segment.name = "netValue"
        compounded.append(segment)
        current_value = float(segment.iloc[-1])

    result = pd.concat(compounded)
    if result.index.has_duplicates:
        raise RuntimeError("持有区间净值拼接后出现重复交易日")
    return result.sort_index()


def run_rolling_method(
    session: Any,
    method: str,
    selector: Selector,
    *,
    start_date: str = START_DATE,
    end_date: str = END_DATE,
    evaluation_count: int = EVALUATION_COUNT,
    random_seed: int = RANDOM_SEED,
    universe_codes: tuple[str, ...] = UNIVERSE_CODES,
    load_data: bool = True,
) -> RollingResult:
    """按上一自然半年训练、下一自然半年持有的流程运行方法。"""
    if len(universe_codes) != 72:
        raise ValueError(
            f"研究范围必须为 72 只 ETF，实际为 {len(universe_codes)} 只"
        )
    if evaluation_count <= 0:
        raise ValueError("evaluation_count 必须大于 0")

    output_start = pd.Timestamp(start_date).normalize()
    output_end = pd.Timestamp(end_date).normalize()
    if output_start > output_end:
        raise ValueError("start_date 不能晚于 end_date")

    periods = build_rolling_periods(output_start, output_end)
    first_training_start = periods[0].training_start
    if load_data:
        get_data(
            session,
            FACTOR_NAMES,
            first_training_start,
            output_end,
            HISTORY_BUFFER_DAYS,
        )

    generator = np.random.default_rng(random_seed)
    period_curves: list[pd.Series] = []
    pool_records: list[dict[str, Any]] = []
    performance_records: list[dict[str, Any]] = []
    evaluation_frames: list[pd.DataFrame] = []
    diagnostic_frames: list[pd.DataFrame] = []

    for period in periods:
        eligible_codes = get_eligible_codes(
            session,
            period.training_start,
            period.training_end,
            universe_codes,
        )
        correlations = get_training_correlations(
            session,
            period.training_start,
            period.training_end,
            eligible_codes,
        )
        try:
            validate_sampling_universe(
                eligible_codes,
                correlations,
            )
        except RuntimeError as error:
            raise RuntimeError(
                f"{period.training_period} 无法构造满足选池约束的组合："
                f"{error}"
            ) from error
        evaluator = PoolEvaluator(
            session=session,
            method=method,
            period=period,
            evaluation_limit=evaluation_count,
            correlations=correlations,
        )
        selection = selector(
            evaluator,
            universe_codes,
            eligible_codes,
            generator,
        )
        selected_codes = canonical_pool(selection.codes)
        validate_pool(selected_codes, correlations)
        if not set(selected_codes).issubset(eligible_codes):
            raise RuntimeError(f"{method} 选择了训练区间不可交易的 ETF")
        if evaluator.evaluation_count != evaluation_count:
            raise RuntimeError(
                f"{method} 在 {period.training_period} 只执行了 "
                f"{evaluator.evaluation_count}/{evaluation_count} 次评估"
            )

        period_curve = run_strategy(
            session,
            selected_codes,
            period.holding_start,
            period.holding_end,
            INITIAL_CASH,
            MOMENTUM_WINDOW,
            SELECT_COUNT,
            RISK_WINDOW,
            MAX_HISTORY_ROWS,
            TARGET_VOLATILITY,
            MAX_INVESTED_RATIO,
        )
        period_metrics = calculate_performance(period_curve)
        period_metrics.update(
            {
                "method": method,
                "training_period": period.training_period,
                "holding_period": period.holding_period,
                "eligible_count": len(eligible_codes),
                "codes": "|".join(selected_codes),
                "maximum_within_group_correlation":
                    maximum_within_group_correlation(
                        selected_codes,
                        correlations,
                ),
            }
        )
        performance_records.append(period_metrics)
        period_curves.append(period_curve)

        for rank, code in enumerate(selected_codes, start=1):
            pool_records.append(
                {
                    "method": method,
                    "training_period": period.training_period,
                    "holding_period": period.holding_period,
                    "rank": rank,
                    "code": code,
                    "group": CODE_GROUP[code],
                }
            )

        evaluation_frames.append(
            pd.DataFrame.from_records(evaluator.records)
        )
        diagnostics = selection.diagnostics.copy()
        diagnostics.insert(0, "method", method)
        diagnostics.insert(
            1,
            "training_period",
            period.training_period,
        )
        diagnostics.insert(
            2,
            "holding_period",
            period.holding_period,
        )
        diagnostic_frames.append(diagnostics)

        print(
            f"method={method}, holding_period={period.holding_period}, "
            f"eligible={len(eligible_codes)}, "
            f"selected={list(selected_codes)}, "
            f"out_of_sample_sharpe={period_metrics['sharpe']:.4f}"
        )

    net_value = compound_period_curves(period_curves)
    configuration = {
        "method": method,
        "start_date": start_date,
        "end_date": end_date,
        "adjustment_months": 6,
        "training_months": 6,
        "evaluation_count_per_period": evaluation_count,
        "pool_size": POOL_SIZE,
        "group_quotas": GROUP_QUOTAS,
        "maximum_within_group_correlation":
            MAXIMUM_WITHIN_GROUP_CORRELATION,
        "minimum_correlation_rows": MINIMUM_CORRELATION_ROWS,
        "random_seed": random_seed,
        "minimum_training_rows": MINIMUM_TRAINING_ROWS,
        "universe_codes": list(universe_codes),
    }
    return RollingResult(
        method=method,
        net_value=net_value,
        period_pools=pd.DataFrame.from_records(pool_records),
        period_performance=pd.DataFrame.from_records(
            performance_records
        ),
        evaluations=pd.concat(
            evaluation_frames,
            ignore_index=True,
        ),
        diagnostics=pd.concat(
            diagnostic_frames,
            ignore_index=True,
        ),
        performance=calculate_performance(net_value),
        configuration=configuration,
    )


def save_result(
    result: RollingResult,
    output_directory: Path,
) -> None:
    """保存一种方法的净值、滚动池、评估过程、诊断数据和摘要。"""
    output_directory.mkdir(parents=True, exist_ok=True)
    result.net_value.to_csv(
        output_directory / "net_value.csv",
        header=True,
        index_label="tradeDate",
    )
    result.period_pools.to_csv(
        output_directory / "period_pools.csv",
        index=False,
    )
    result.period_performance.to_csv(
        output_directory / "period_performance.csv",
        index=False,
    )
    result.evaluations.to_csv(
        output_directory / "evaluations.csv",
        index=False,
    )
    result.diagnostics.to_csv(
        output_directory / "diagnostics.csv",
        index=False,
    )

    summary = {
        **result.configuration,
        "performance": {
            key: (
                value.isoformat()
                if isinstance(value, pd.Timestamp)
                else value
            )
            for key, value in result.performance.items()
        },
    }
    with (output_directory / "summary.json").open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)

    figure, axis = plt.subplots(figsize=(12, 5))
    axis.plot(
        result.net_value.index,
        result.net_value.to_numpy(),
    )
    axis.set(
        title=f"{result.method} ETF Pool Strategy",
        xlabel="Date",
        ylabel="Net Value",
    )
    axis.grid(alpha=0.3)
    figure.tight_layout()
    figure.savefig(
        output_directory / "net_value.png",
        dpi=160,
    )
    plt.close(figure)


__all__ = [
    "EVALUATION_COUNT",
    "ETF_GROUPS",
    "GROUP_QUOTAS",
    "MAXIMUM_WITHIN_GROUP_CORRELATION",
    "POOL_SIZE",
    "RANDOM_SEED",
    "PoolEvaluator",
    "RollingPeriod",
    "RollingResult",
    "SelectionResult",
    "UNIVERSE_CODES",
    "calculate_performance",
    "calculate_sharpe",
    "build_rolling_periods",
    "canonical_pool",
    "count_pool_completions",
    "group_codes",
    "group_correlation_is_valid",
    "pool_is_valid",
    "run_rolling_method",
    "sample_pool",
    "sample_unseen_pool",
    "sampling_universe_is_valid",
    "save_result",
    "validate_pool",
]
