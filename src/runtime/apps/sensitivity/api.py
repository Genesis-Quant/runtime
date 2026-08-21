"""在共享 DolphinDB 数据和消息表上执行敏感性分析。"""

import json
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
from ..backtest.schema import Adj, CallbackName
from .result import SensitivityResult
from .schema import (
    SensitivityAnalysisType,
    SensitivityCase,
    SensitivityParameters,
)

RESULT_REF = "coreSensitivityResult"


def analyze_backtest_sensitivity(
        dataset_query: dict[str, Any],
        callbacks: dict[CallbackName, str],
        analysis_type: SensitivityAnalysisType | str,
        cases: list[SensitivityCase | dict[str, Any]],
        *,
        session: Any | None = None,
        codes_query: dict[str, Any] | None = None,
        utils: str = "",
        params: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        adj: Adj | None = None,
        risk_free_rate: float = 0.04,
        annual_trading_days: int = 250,
) -> SensitivityResult:
    """只准备一次完整区间数据，并依次执行全部敏感性组合。"""
    parameters = SensitivityParameters.model_validate({
        "dataset_query": dataset_query,
        "callbacks": callbacks,
        "analysis_type": analysis_type,
        "cases": cases,
        "codes_query": codes_query,
        "utils": utils,
        "params": params if params is not None else {},
        "config": config,
        "adj": adj,
        "risk_free_rate": risk_free_rate,
        "annual_trading_days": annual_trading_days,
    })
    owns_session = session is None
    current_session = (
        create_session(redirect_output=False)
        if owns_session
        else session
    )
    if not owns_session:
        disable_session_output(current_session)
    started_at = monotonic()
    succeeded = 0
    failed = 0

    try:
        logger.info(
            f"敏感性分析开始：类型={parameters.analysis_type.value}，"
            f"共 {len(parameters.cases)} 个组合，完整区间数据只查询一次"
        )
        prepared = prepare_backtest_session(
            parameters,
            current_session,
            log_progress=False,
        )
        current_session.run(f"undef(`{RESULT_REF}, VAR)")
        logger.info("共享数据和消息表准备完成，开始执行参数组合")

        for case_index, case in enumerate(parameters.cases, start=1):
            case_started_at = monotonic()
            case_parameters = prepared.model_copy(update={
                "params": case.params,
                "config": {**prepared.config, "commission": case.commission},
            })
            try:
                execute_prepared_backtest(
                    case_parameters,
                    current_session,
                    params=case.params,
                    log_progress=False,
                )
                append_success_result(
                    current_session,
                    parameters.analysis_type,
                    case_index,
                    case,
                    append=succeeded + failed > 0,
                )
                succeeded += 1
                logger.info(
                    f"敏感性组合 {case_index}/{len(parameters.cases)} 完成，"
                    f"耗时 {monotonic() - case_started_at:.1f} 秒"
                )
            except Exception as error:
                failed += 1
                append_error_result(
                    current_session,
                    parameters.analysis_type,
                    case_index,
                    case,
                    str(error),
                    append=succeeded + failed > 1,
                )
                logger.warning(
                    f"敏感性组合 {case_index}/{len(parameters.cases)} 失败：{error}"
                )
            finally:
                drop_prepared_backtest_engine(current_session)

        message = (
            f"敏感性分析完成：成功 {succeeded}，失败 {failed}，"
            f"耗时 {monotonic() - started_at:.1f} 秒"
        )
        if succeeded:
            logger.success(message)
        else:
            logger.warning(f"{message}；失败原因已保存在结果文件中")
        return SensitivityResult(session=current_session, table_ref=RESULT_REF)
    except Exception:
        if owns_session:
            current_session.close()
        raise


def append_success_result(
        session: Any,
        analysis_type: SensitivityAnalysisType,
        case_index: int,
        case: SensitivityCase,
        *,
        append: bool,
) -> None:
    """在 DolphinDB 内生成一个组合的结果行并追加到结果表。"""
    upload_case(session, analysis_type, case_index, case, "", "SUCCESS")
    output_statement = (
        f"{RESULT_REF}.append!(coreSensitivityRow)"
        if append
        else f"{RESULT_REF} = coreSensitivityRow"
    )
    session.run(f"""
        coreSensitivityPortfolios = Backtest::getDailyTotalPortfolios(coreBacktestEngine)
        if (rows(coreSensitivityPortfolios) == 0) {{
            throw "回测没有返回每日组合资产"
        }}
        if (any(isNull(coreSensitivityPortfolios.netValue)) ||
            any(coreSensitivityPortfolios.netValue <= 0)) {{
            throw "每日组合资产包含无效 netValue"
        }}
        coreSensitivitySummary = backtest::standardize_return_summary(
            Backtest::getReturnSummary(coreBacktestEngine),
            coreSensitivityPortfolios,
            coreBacktestAnnualTradingDays,
            coreBacktestRiskFreeRate
        )
        coreSensitivityReturns = double(coreSensitivityPortfolios.ratio)
        coreSensitivityReturns[isNull(coreSensitivityReturns)] = 0.0
        coreSensitivityPeriodRate = pow(
            1.0 + coreBacktestRiskFreeRate,
            1.0 / coreBacktestAnnualTradingDays
        ) - 1.0
        coreSensitivityExcessReturns =
            coreSensitivityReturns - coreSensitivityPeriodRate
        coreSensitivityDownsideReturns =
            coreSensitivityExcessReturns[coreSensitivityExcessReturns < 0]
        coreSensitivityDownside = sqrt(
            sum(square(coreSensitivityDownsideReturns)) /
            size(coreSensitivityExcessReturns)
        )
        coreSensitivitySortino = double(NULL)
        if (!isNull(coreSensitivityDownside) && coreSensitivityDownside != 0) {{
            coreSensitivitySortino =
                avg(coreSensitivityExcessReturns) /
                coreSensitivityDownside *
                sqrt(coreBacktestAnnualTradingDays)
        }}
        coreSensitivityTotalFee = double(NULL)
        if ("totalFee" in coreSensitivityPortfolios.colNames()) {{
            coreSensitivityFees = double(coreSensitivityPortfolios.totalFee)
            coreSensitivityPreviousFees = move(coreSensitivityFees, 1)
            coreSensitivityPreviousFees[0] = 0.0
            coreSensitivityDailyFees =
                coreSensitivityFees - coreSensitivityPreviousFees
            coreSensitivityValidFees = coreSensitivityDailyFees[
                !isNull(coreSensitivityDailyFees) &&
                coreSensitivityDailyFees >= 0
            ]
            if (size(coreSensitivityValidFees) > 0) {{
                coreSensitivityTotalFee = sum(coreSensitivityValidFees)
            }}
        }}
        coreSensitivityRow = table(
            [long(coreSensitivityCaseIndex)] as case_index,
            [string(coreSensitivityAnalysisType)] as analysis_type,
            [string(coreSensitivityParams)] as params,
            [double(coreSensitivityCommission)] as commission,
            [string(coreSensitivityStatus)] as status,
            [string(coreSensitivityError)] as error,
            [double(first(coreSensitivitySummary.totalReturn))] as total_return,
            [double(first(coreSensitivitySummary.annualReturn))] as cagr,
            [double(first(coreSensitivitySummary.sharpeRatio))] as sharpe,
            [double(coreSensitivitySortino)] as sortino,
            [double(first(coreSensitivitySummary.annualVolatility))] as volatility,
            [-abs(double(first(coreSensitivitySummary.maxDrawdown)))] as max_drawdown,
            [double(first(coreSensitivitySummary.dailyWinningRate))] as win_rate,
            [double(first(coreSensitivitySummary.drawdownRatio))] as calmar,
            [double(coreSensitivityTotalFee)] as total_fee
        )
        {output_statement}
    """)


def append_error_result(
        session: Any,
        analysis_type: SensitivityAnalysisType,
        case_index: int,
        case: SensitivityCase,
        error: str,
        *,
        append: bool,
) -> None:
    """把单个组合错误保存为同构结果行。"""
    upload_case(session, analysis_type, case_index, case, error, "FAILURE")
    output_statement = (
        f"{RESULT_REF}.append!(coreSensitivityRow)"
        if append
        else f"{RESULT_REF} = coreSensitivityRow"
    )
    session.run(f"""
        coreSensitivityRow = table(
            [long(coreSensitivityCaseIndex)] as case_index,
            [string(coreSensitivityAnalysisType)] as analysis_type,
            [string(coreSensitivityParams)] as params,
            [double(coreSensitivityCommission)] as commission,
            [string(coreSensitivityStatus)] as status,
            [string(coreSensitivityError)] as error,
            [double(NULL)] as total_return,
            [double(NULL)] as cagr,
            [double(NULL)] as sharpe,
            [double(NULL)] as sortino,
            [double(NULL)] as volatility,
            [double(NULL)] as max_drawdown,
            [double(NULL)] as win_rate,
            [double(NULL)] as calmar,
            [double(NULL)] as total_fee
        )
        {output_statement}
    """)


def upload_case(
        session: Any,
        analysis_type: SensitivityAnalysisType,
        case_index: int,
        case: SensitivityCase,
        error: str,
        status: str,
) -> None:
    session.upload({
        "coreSensitivityCaseIndex": case_index,
        "coreSensitivityAnalysisType": analysis_type.value,
        "coreSensitivityParams": json.dumps(
            case.params,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        "coreSensitivityCommission": case.commission,
        "coreSensitivityStatus": status,
        "coreSensitivityError": error,
    })


__all__ = ["analyze_backtest_sensitivity"]
