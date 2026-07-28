"""使用因子 DSL 构造日频消息并运行 DolphinDB Backtest 策略。"""

from collections.abc import Mapping
import time
from typing import Any
from uuid import uuid4

import numpy as np

from core.database import (
    STOCK_DIVIDEND_TABLE,
    collect_functions,
    create_session,
    ensure_stock_dividend_table,
    render_functions,
)
from core.utils import CODE_COLUMN, logger, normalize_date_range

from ..query import FactorQuery, build_query_table
from .schema import (
    CALLBACK_NAMES,
    BacktestParameters,
    Callback,
    CallbackName,
    Utility,
)
from .result import BacktestResult


def run_backtest(
    request: FactorQuery | dict[str, Any],
    callbacks: Mapping[CallbackName, Callback],
    *,
    utils: Mapping[str, Utility] | None = None,
    codes_query: FactorQuery | dict[str, Any] | None = None,
    name: str | None = None,
    config: Mapping[str, Any] | None = None,
    annual_trading_days: int = 250,
    risk_free_rate: float = 0.04,
    source_ref: str | None = None,
    message_ref: str | None = None,
    compact: bool = False,
    session: Any | None = None,
) -> BacktestResult:
    """运行日频回测，并把保存服务端输出的会话移交给惰性结果。"""
    started = time.perf_counter()
    parameters = BacktestParameters.model_validate(
        {
            "query": request,
            "callbacks": callbacks,
            "utils": utils,
            "codes_query": codes_query,
            "name": name,
            "config": config,
            "annual_trading_days": annual_trading_days,
            "risk_free_rate": risk_free_rate,
            "source_ref": source_ref,
            "message_ref": message_ref,
            "compact": compact,
        }
    )
    engine_name = parameters.name or f"coreBacktest_{uuid4().hex}"
    backtest_config = dict(parameters.config)
    callback_script = render_functions(
        collect_functions(
            (
                *parameters.utils.values(),
                *parameters.callbacks.values(),
            )
        )
    )
    callback_names = {
        callback_name: (
            parameters.callbacks[callback_name].name
            if callback_name in parameters.callbacks
            else "NULL"
        )
        for callback_name in CALLBACK_NAMES
    }
    owns_session = session is None
    current_session = create_session() if owns_session else session
    engine_created = False
    backtest_result: BacktestResult | None = None
    try:
        query = parameters.query

        if parameters.codes_query is not None:
            codes_unfiltered_data_ref = "coreBacktestCodesUnfilteredFactorData"
            codes_filtered_data_ref = "coreBacktestCodesFilteredFactorData"
            build_query_table(
                parameters.codes_query,
                session=current_session,
                computed_ref=codes_unfiltered_data_ref,
                filtered_ref=codes_filtered_data_ref,
            )
            selected_codes = current_session.run(
                f"""
                exec distinct {CODE_COLUMN}
                from {codes_filtered_data_ref}
                where
                    time >= coreOutputStart,
                    time < coreOutputEndExclusive,
                    not isNull({CODE_COLUMN})
                order by {CODE_COLUMN}
                """
            )
            if not isinstance(selected_codes, np.ndarray):
                raise TypeError(
                    "codes DSL 必须返回一维代码向量，实际为 "
                    f"{type(selected_codes).__name__}"
                )
            if selected_codes.ndim != 1:
                raise ValueError(
                    "codes DSL 必须返回一维代码向量，实际维数为 "
                    f"{selected_codes.ndim}"
                )
            codes = selected_codes.astype(str).tolist()
            if not codes:
                raise ValueError("codes DSL 没有选出任何股票")
            unsupported_codes = [
                code
                for code in codes
                if not code.endswith((".SH", ".SZ"))
            ]
            if unsupported_codes:
                raise ValueError(
                    "codes DSL 只能返回 .SH 和 .SZ 股票代码："
                    f"{unsupported_codes[:10]}"
                )
            logger.info(f"codes DSL 选出 {len(codes):,} 只股票")
            query = query.model_copy(update={"codes": codes})

        unfiltered_data_ref = "coreBacktestUnfilteredFactorData"
        filtered_data_ref = "coreBacktestFilteredFactorData"
        query, _ = build_query_table(
            query,
            session=current_session,
            computed_ref=unfiltered_data_ref,
            filtered_ref=filtered_data_ref,
            source_ref=parameters.source_ref,
        )

        output_start, output_end = normalize_date_range(
            query.start_date,
            query.end_date,
        )
        backtest_config.update(
            {
                "startDate": output_start.to_datetime64().astype(
                    "datetime64[D]"
                ),
                "endDate": output_end.to_datetime64().astype("datetime64[D]"),
                "strategyGroup": "stock",
                "dataType": 4,
                "msgAsTable": True,
            }
        )
        current_session.upload(
            {
                "coreBacktestName": engine_name,
                "coreBacktestConfig": backtest_config,
                "coreBacktestCodes": np.asarray(query.codes, dtype=str),
                "coreBacktestStartDate": output_start,
                "coreBacktestEndDate": output_end,
                "coreBacktestAnnualTradingDays": parameters.annual_trading_days,
                "coreBacktestRiskFreeRate": parameters.risk_free_rate,
            }
        )
        ensure_stock_dividend_table(current_session)
        message_statement = (
            f"coreBacktestMsg = select * from {parameters.message_ref}"
            if parameters.message_ref is not None
            else f"""
            coreBacktestMsg = backtest::build_backtest_message(
                project_factor_output(
                    {unfiltered_data_ref},
                    coreDslOutputColumns,
                    coreOutputStart,
                    coreOutputEndExclusive
                )
            )
            """
        )

        current_session.run(
            f"""
            coreLoadedPlugins = exec plugin from getLoadedPlugins()
            if (!("MatchingEngineSimulator" in coreLoadedPlugins)) {{
                loadPlugin("MatchingEngineSimulator")
            }}
            if (!("Backtest" in coreLoadedPlugins)) {{
                loadPlugin("Backtest")
            }}

            use backtest

            {callback_script}

            coreBacktestStockDividend = select
                symbol(
                    strReplace(
                        strReplace(string(symbol), ".SZ", ".XSHE"),
                        ".SH",
                        ".XSHG"
                    )
                ) as symbol,
                endDate,
                iif(isNull(annDate), recordDate, annDate) as annDate,
                recordDate,
                exDate,
                iif(isNull(payDate), exDate, payDate) as payDate,
                iif(
                    isNull(divListDate),
                    exDate,
                    divListDate
                ) as divListDate,
                bonusRatio,
                capitalConversion,
                afterTaxCashDiv,
                allotPrice,
                allotRatio
            from {STOCK_DIVIDEND_TABLE}
            where
                symbol in symbol(coreBacktestCodes),
                recordDate >= date(coreBacktestStartDate),
                exDate <= date(coreBacktestEndDate),
                iif(isNull(payDate), exDate, payDate)
                    <= date(coreBacktestEndDate),
                iif(isNull(divListDate), exDate, divListDate)
                    <= date(coreBacktestEndDate)
            if (coreBacktestStockDividend.rows() > 0) {{
                coreBacktestConfig["stockDividend"] =
                    coreBacktestStockDividend
            }}

            {message_statement}
            coreBacktestEngine = backtest::run_backtest(
                coreBacktestName,
                coreBacktestConfig,
                coreBacktestMsg,
                {unfiltered_data_ref},
                {filtered_data_ref},
                {callback_names["initialize"]},
                {callback_names["beforeTrading"]},
                {callback_names["onBar"]},
                {callback_names["onSnapshot"]},
                {callback_names["onOrder"]},
                {callback_names["onTrade"]},
                {callback_names["afterTrading"]},
                {callback_names["finalize"]}
            )
            """
        )
        engine_created = True

        optional_outputs = ""
        if not parameters.compact:
            optional_outputs = """
            coreBacktestResultContext =
                Backtest::getContextDict(coreBacktestEngine)
            erase!(
                coreBacktestResultContext,
                [
                    "engine",
                    "coreBacktestUnfilteredFactorData",
                    "coreBacktestFilteredFactorData"
                ]
            )
            coreBacktestResultTradeDetails =
                Backtest::getTradeDetails(coreBacktestEngine)
            coreBacktestResultDailyPositions =
                Backtest::getDailyPosition(coreBacktestEngine)
            coreBacktestResultDailyTradingStatistics =
                Backtest::getDailyTradingStatistics(coreBacktestEngine)
            coreBacktestResultEngineStat =
                Backtest::getBacktestEngineStat(coreBacktestEngine)
            """
        current_session.run(
            f"""
            coreBacktestResultMessageRows =
                long(coreBacktestMsg.rows())
            coreBacktestResultDailyPortfolios =
                Backtest::getDailyTotalPortfolios(coreBacktestEngine)
            coreBacktestResultReturnSummary =
                backtest::standardize_return_summary(
                Backtest::getReturnSummary(coreBacktestEngine),
                coreBacktestResultDailyPortfolios,
                coreBacktestAnnualTradingDays,
                coreBacktestRiskFreeRate
            )
            {optional_outputs}
            """
        )
        backtest_result = BacktestResult(
            name=engine_name,
            session=current_session,
            compact=parameters.compact,
        )
        logger.success(
            f"回测完成：name={engine_name}，"
            "结果已保存在 DolphinDB 会话中，"
            f"耗时={time.perf_counter() - started:.2f} 秒"
        )
        return backtest_result
    except Exception:
        logger.exception(f"回测失败：name={engine_name}")
        raise
    finally:
        if engine_created:
            try:
                current_session.run(
                    "Backtest::dropBacktestEngine(coreBacktestEngine)"
                )
            except Exception:
                logger.exception(f"清理回测引擎失败：name={engine_name}")
        if owns_session and backtest_result is None:
            current_session.close()


__all__ = [
    "BacktestResult",
    "Callback",
    "Utility",
    "run_backtest",
]
