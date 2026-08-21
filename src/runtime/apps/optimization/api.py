"""在共享 DolphinDB 数据和消息表上执行滚动参数调优。"""

import json
import math
from calendar import monthrange
from datetime import date, timedelta
from itertools import product
from time import monotonic
from typing import Any

from runtime.database import create_session
from runtime.database.session import disable_session_output
from runtime.utils import logger

from ..backtest.api import (
    drop_prepared_backtest_engine,
    execute_prepared_backtest,
    prepare_backtest_session,
)
from ..backtest.schema import Adj, BacktestParameters, CallbackName
from .algorithms import normalize_parameter_candidates, select_parameter
from .result import OptimizationResult
from .schema import (
    OptimizationAlgorithm,
    OptimizationParameters,
    OptimizationSelection,
    WalkForwardWindow,
)

INVALID_SCORE = -1e12
OPTIMIZATION_SESSION_MAX_TIME = 6 * 60 * 60


def optimize_backtest(
        dataset_query: dict[str, Any],
        callbacks: dict[CallbackName, str],
        parameter_space: dict[str, list[int | float]],
        algorithms: list[OptimizationAlgorithm | str],
        start_date: str,
        end_date: str,
        lookback_period: str,
        holding_period: str,
        *,
        session: Any | None = None,
        codes_query: dict[str, Any] | None = None,
        utils: str = "",
        params: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        adj: Adj | None = None,
        risk_free_rate: float = 0.04,
        annual_trading_days: int = 250,
        repetitions: int = 1,
        evaluation_budget: int = 12,
        seed: int = 20260815,
) -> OptimizationResult:
    """滚动调优参数，并为每种算法生成全部重复样本外净值路径。"""
    parameters = OptimizationParameters.model_validate({
        "dataset_query": dataset_query,
        "callbacks": callbacks,
        "parameter_space": parameter_space,
        "algorithms": algorithms,
        "start_date": start_date,
        "end_date": end_date,
        "lookback_period": lookback_period,
        "holding_period": holding_period,
        "codes_query": codes_query,
        "utils": utils,
        "params": params if params is not None else {},
        "config": config,
        "adj": adj,
        "risk_free_rate": risk_free_rate,
        "annual_trading_days": annual_trading_days,
        "repetitions": repetitions,
        "evaluation_budget": evaluation_budget,
        "seed": seed,
    })
    windows = build_walk_forward_windows(parameters)
    candidates = build_parameter_candidates(parameters)
    evaluation_budget = min(parameters.evaluation_budget, len(candidates))
    parameter_names = tuple(sorted(parameters.parameter_space))
    points = normalize_parameter_candidates(candidates, parameter_names)
    prepared_parameters = full_interval_parameters(parameters, windows)
    algorithm_numbers = {
        algorithm: number
        for number, algorithm in enumerate(OptimizationAlgorithm)
    }
    owns_session = session is None
    current_session = (
        create_session(
            redirect_output=False,
            max_time=OPTIMIZATION_SESSION_MAX_TIME,
        )
        if owns_session
        else session
    )
    if not owns_session:
        disable_session_output(current_session)
    training_scores: dict[tuple[int, int], float] = {}
    training_evaluations = 0
    total_windows = len(parameters.algorithms) * parameters.repetitions * len(windows)

    try:
        logger.info(
            f"参数调优开始：{len(parameters.algorithms)} 种算法，"
            f"{parameters.repetitions} 次重复，{len(windows)} 个滚动窗口，"
            f"{len(candidates)} 个参数组合，每窗口最多评估 {evaluation_budget} 个组合"
        )
        logger.info(
            f"正在准备共享数据：{windows[0].training_start} 至 "
            f"{windows[-1].holding_end}，完整区间只查询一次"
        )
        prepared_parameters = prepare_backtest_session(
            prepared_parameters,
            current_session,
            log_progress=False,
        )
        logger.info("共享数据准备完成，开始滚动训练与样本外回测")

        def training_score(window: WalkForwardWindow, candidate_index: int) -> float:
            nonlocal training_evaluations
            key = (window.number, candidate_index)
            if key not in training_scores:
                score = run_training_window(
                    prepared_parameters,
                    current_session,
                    window.training_start,
                    window.training_end,
                    {**prepared_parameters.params, **candidates[candidate_index]},
                )
                training_scores[key] = INVALID_SCORE if score is None else score
                training_evaluations += 1
            return training_scores[key]

        table_refs: dict[OptimizationAlgorithm, str] = {}
        for algorithm_index, algorithm in enumerate(parameters.algorithms, start=1):
            method_start = monotonic()
            method_training_start = training_evaluations
            method_completed_windows = 0
            method_total_windows = parameters.repetitions * len(windows)
            method_next_progress = 10
            logger.info(
                f"调优方法 {algorithm_index}/{len(parameters.algorithms)} "
                f"{algorithm.value} 开始：{method_total_windows} 个样本外窗口"
            )
            output_ref = f"coreOptimizationResult{algorithm_numbers[algorithm]}"
            table_refs[algorithm] = output_ref
            output_exists = False
            for repetition in range(1, parameters.repetitions + 1):
                current_session.run("coreOptimizationPathBase = 1.0")
                for window in windows:
                    seed = (
                        parameters.seed
                        + algorithm_numbers[algorithm] * 10_000_000
                        + repetition * 100_000
                        + window.number
                    )
                    selection = select_parameter(
                        algorithm,
                        points,
                        lambda index, current=window: training_score(current, index),
                        seed=seed,
                        budget=evaluation_budget,
                    )
                    if selection.selected_score <= INVALID_SCORE:
                        raise RuntimeError(
                            f"{algorithm.value} 第 {repetition} 次重复、第 {window.number} 个窗口没有有效训练 Sharpe"
                        )
                    holding_ref = "coreOptimizationHolding"
                    run_holding_window(
                        prepared_parameters,
                        current_session,
                        window.holding_start,
                        window.holding_end,
                        {
                            **prepared_parameters.params,
                            **candidates[selection.selected_index],
                        },
                        holding_ref,
                    )
                    append_path_rows(
                        current_session,
                        holding_ref,
                        output_ref,
                        algorithm,
                        repetition,
                        window,
                        candidates[selection.initial_index],
                        candidates[selection.selected_index],
                        selection,
                        append=output_exists,
                    )
                    output_exists = True
                    method_completed_windows += 1
                    method_progress = (
                        method_completed_windows * 100 // method_total_windows
                    )
                    if (
                        method_progress >= method_next_progress
                        or method_completed_windows == method_total_windows
                    ):
                        logger.info(
                            f"调优方法 {algorithm_index}/{len(parameters.algorithms)} "
                            f"{algorithm.value} 进度 "
                            f"{method_completed_windows}/{method_total_windows} "
                            f"({method_progress}%)："
                            f"重复 {repetition}/{parameters.repetitions}，"
                            f"窗口 {window.number}/{len(windows)}，"
                            f"训练 Sharpe={selection.selected_score:.4f}，"
                            f"本方法新增训练回测 "
                            f"{training_evaluations - method_training_start} 次"
                        )
                        while method_next_progress <= method_progress:
                            method_next_progress += 10
            logger.success(
                f"调优方法 {algorithm_index}/{len(parameters.algorithms)} "
                f"{algorithm.value} 完成：{method_completed_windows} 个窗口，"
                f"新增训练回测 {training_evaluations - method_training_start} 次，"
                f"耗时 {monotonic() - method_start:.1f} 秒"
            )
        current_session.run("undef(`coreOptimizationHolding, VAR)")
        logger.success(
            f"参数调优完成：生成 {len(table_refs)} 份算法结果，"
            f"完成 {total_windows} 个样本外窗口，"
            f"实际执行 {training_evaluations} 次训练回测"
        )
        return OptimizationResult(session=current_session, table_refs=table_refs)
    except Exception:
        if owns_session:
            current_session.close()
        raise


def build_walk_forward_windows(parameters: OptimizationParameters) -> list[WalkForwardWindow]:
    """按持有周期平移，构造不重叠的样本外窗口。"""
    start = date.fromisoformat(parameters.start_date)
    end = date.fromisoformat(parameters.end_date)
    windows: list[WalkForwardWindow] = []
    holding_start = start
    while holding_start <= end:
        next_start = shift_period(
            start,
            parameters.holding_period,
            len(windows) + 1,
        )
        holding_end = min(end, next_start - timedelta(days=1))
        windows.append(
            WalkForwardWindow(
                number=len(windows) + 1,
                training_start=shift_period(holding_start, parameters.lookback_period, -1),
                training_end=holding_start - timedelta(days=1),
                holding_start=holding_start,
                holding_end=holding_end,
            )
        )
        holding_start = next_start
    return windows


def shift_period(value: date, period: str, direction: int = 1) -> date:
    """按已校验的 D/W/M/Y 周期平移日期。"""
    amount = int(period[:-1]) * direction
    unit = period[-1]
    if unit == "D":
        return value + timedelta(days=amount)
    if unit == "W":
        return value + timedelta(weeks=amount)
    if unit == "M":
        month_index = value.year * 12 + value.month - 1 + amount
        year, month_offset = divmod(month_index, 12)
        month = month_offset + 1
        return date(year, month, min(value.day, monthrange(year, month)[1]))
    if unit == "Y":
        year = value.year + amount
        return date(year, value.month, min(value.day, monthrange(year, value.month)[1]))
    raise ValueError(f"不支持的滚动周期：{period}")


def full_interval_parameters(
        parameters: OptimizationParameters,
        windows: list[WalkForwardWindow],
) -> BacktestParameters:
    """把版本请求扩展为覆盖全部训练与持有窗口的一次查询。"""
    start = windows[0].training_start.isoformat()
    end = windows[-1].holding_end.isoformat()
    backtest = BacktestParameters.model_validate({
        name: getattr(parameters, name)
        for name in BacktestParameters.model_fields
    })
    dataset_query = backtest.dataset_query.model_copy(
        update={"start_date": start, "end_date": end}
    )
    codes_query = backtest.codes_query
    if codes_query is not None:
        codes_query = codes_query.model_copy(update={"start_date": start, "end_date": end})
    return backtest.model_copy(
        update={"dataset_query": dataset_query, "codes_query": codes_query}
    )


def build_parameter_candidates(
        parameters: OptimizationParameters,
) -> list[dict[str, int | float]]:
    """生成调优参数列表的笛卡尔积。"""
    names = tuple(sorted(parameters.parameter_space))
    candidates = []
    for values in product(*(sorted(parameters.parameter_space[name]) for name in names)):
        candidates.append(dict(zip(names, values, strict=True)))
    return candidates


def run_training_window(
        parameters: BacktestParameters,
        session: Any,
        start: date,
        end: date,
        params: dict[str, Any],
) -> float | None:
    """在共享 ref 上执行训练窗口，只下载一个 Sharpe 标量。"""
    try:
        execute_prepared_backtest(
            parameters,
            session,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            params=params,
            log_progress=False,
        )
        score = session.run(
            """
            coreOptimizationReturnSummary = backtest::standardize_return_summary(
                Backtest::getReturnSummary(coreBacktestEngine),
                Backtest::getDailyTotalPortfolios(coreBacktestEngine),
                coreBacktestAnnualTradingDays,
                coreBacktestRiskFreeRate
            )
            coreOptimizationTrainingSharpe = first(coreOptimizationReturnSummary.sharpeRatio)
            coreOptimizationTrainingSharpe
            """
        )
        if score is None:
            return None
        number = float(score)
        return number if math.isfinite(number) else None
    finally:
        drop_prepared_backtest_engine(session)


def run_holding_window(
        parameters: BacktestParameters,
        session: Any,
        start: date,
        end: date,
        params: dict[str, Any],
        holding_ref: str,
) -> None:
    """执行样本外窗口，并把每日组合资产保留为 DolphinDB 表引用。"""
    try:
        execute_prepared_backtest(
            parameters,
            session,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            params=params,
            log_progress=False,
        )
        session.run(f"""
            {holding_ref} = Backtest::getDailyTotalPortfolios(coreBacktestEngine)
            {holding_ref} = select * from {holding_ref} order by tradeDate
            if (rows({holding_ref}) == 0) throw "样本外回测没有返回每日组合资产"
            if (any(isNull({holding_ref}.netValue)) || any({holding_ref}.netValue <= 0)) {{
                throw "每日组合资产包含无效 netValue"
            }}
        """)
    finally:
        drop_prepared_backtest_engine(session)


def append_path_rows(
        session: Any,
        holding_ref: str,
        output_ref: str,
        algorithm: OptimizationAlgorithm,
        repetition: int,
        window: WalkForwardWindow,
        initial_params: dict[str, Any],
        selected_params: dict[str, Any],
        selection: OptimizationSelection,
        *,
        append: bool,
) -> None:
    """在 DolphinDB 中拼接一个样本外窗口，不下载任何结果表。"""
    session.upload({
        "coreOptimizationAlgorithm": algorithm.value,
        "coreOptimizationRepetition": repetition,
        "coreOptimizationWindow": window.number,
        "coreOptimizationTrainingStart": window.training_start,
        "coreOptimizationTrainingEnd": window.training_end,
        "coreOptimizationHoldingStart": window.holding_start,
        "coreOptimizationHoldingEnd": window.holding_end,
        "coreOptimizationTrainingSharpe": selection.selected_score,
        "coreOptimizationEvaluationCount": len(selection.evaluated_indices),
        "coreOptimizationInitialParams": json.dumps(initial_params, ensure_ascii=False, separators=(",", ":")),
        "coreOptimizationSelectedParams": json.dumps(selected_params, ensure_ascii=False, separators=(",", ":")),
    })
    output_statement = (
        f"{output_ref}.append!(coreOptimizationWindowResult)"
        if append
        else f"{output_ref} = coreOptimizationWindowResult"
    )
    session.run(f"""
        coreOptimizationWindowResult = select * from {holding_ref} order by tradeDate
        coreOptimizationWindowResult.rename!(`tradeDate`netValue, `time`window_net_value)
        coreOptimizationWindowResult[`algorithm] = take(coreOptimizationAlgorithm, rows(coreOptimizationWindowResult))
        coreOptimizationWindowResult[`repetition] = take(coreOptimizationRepetition, rows(coreOptimizationWindowResult))
        coreOptimizationWindowResult[`window] = take(coreOptimizationWindow, rows(coreOptimizationWindowResult))
        coreOptimizationWindowResult[`training_start] = take(coreOptimizationTrainingStart, rows(coreOptimizationWindowResult))
        coreOptimizationWindowResult[`training_end] = take(coreOptimizationTrainingEnd, rows(coreOptimizationWindowResult))
        coreOptimizationWindowResult[`holding_start] = take(coreOptimizationHoldingStart, rows(coreOptimizationWindowResult))
        coreOptimizationWindowResult[`holding_end] = take(coreOptimizationHoldingEnd, rows(coreOptimizationWindowResult))
        coreOptimizationWindowResult[`training_sharpe] = take(coreOptimizationTrainingSharpe, rows(coreOptimizationWindowResult))
        coreOptimizationWindowResult[`evaluation_count] = take(coreOptimizationEvaluationCount, rows(coreOptimizationWindowResult))
        coreOptimizationWindowResult[`initial_params] = take(coreOptimizationInitialParams, rows(coreOptimizationWindowResult))
        coreOptimizationWindowResult[`selected_params] = take(coreOptimizationSelectedParams, rows(coreOptimizationWindowResult))
        coreOptimizationWindowResult[`path_net_value] = coreOptimizationWindowResult.window_net_value * coreOptimizationPathBase
        coreOptimizationPreviousValue = move(coreOptimizationWindowResult.path_net_value, 1)
        coreOptimizationPreviousValue[0] = coreOptimizationPathBase
        coreOptimizationWindowResult[`daily_return] = coreOptimizationWindowResult.path_net_value / coreOptimizationPreviousValue - 1.0
        coreOptimizationPathBase = last(coreOptimizationWindowResult.path_net_value)
        {output_statement}
    """)


__all__ = ["optimize_backtest"]
