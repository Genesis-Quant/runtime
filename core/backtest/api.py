"""使用因子 DSL 构造日频消息并运行 DolphinDB Backtest 策略。"""

from collections.abc import Mapping
import time
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd

from core.database import (
    collect_functions,
    create_session,
    render_functions,
)
from core.query import FactorQuery, build_query_table
from core.utils import CODE_COLUMN, logger, normalize_date_range

from .schema import (
    CALLBACK_NAMES,
    BacktestParameters,
    BacktestResult,
    Callback,
    CallbackName,
    Utility,
)


def as_frame(value: Any) -> pd.DataFrame:
    """把 Backtest 插件的空表返回值统一为 DataFrame。"""
    if isinstance(value, pd.DataFrame):
        return value.reset_index(drop=True)
    if value is None or (isinstance(value, (list, tuple, dict)) and not value):
        return pd.DataFrame()
    raise TypeError(
        f"DolphinDB Backtest 输出必须是表，实际为 {type(value).__name__}"
    )


def run_backtest(
    request: FactorQuery | dict[str, Any],
    callbacks: Mapping[CallbackName, Callback],
    *,
    utils: Mapping[str, Utility] | None = None,
    codes_query: FactorQuery | dict[str, Any] | None = None,
    name: str | None = None,
    config: Mapping[str, Any] | None = None,
    session: Any | None = None,
) -> BacktestResult:
    """用未筛选行情构造消息，并以筛选结果提供策略数据和运行日频回测。"""
    started = time.perf_counter()
    parameters = BacktestParameters.model_validate(
        {
            "query": request,
            "callbacks": callbacks,
            "utils": utils,
            "codes_query": codes_query,
            "name": name,
            "config": config,
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
            }
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

            coreBacktestMsg = backtest::build_backtest_message(
                project_factor_output(
                    {unfiltered_data_ref},
                    coreDslOutputColumns,
                    coreOutputStart,
                    coreOutputEndExclusive
                )
            )
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

        outputs = current_session.run(
            """
            coreBacktestOutputs = dict(STRING, ANY)
            coreBacktestEngineStat = Backtest::getBacktestEngineStat(coreBacktestEngine)
            coreBacktestContext = Backtest::getContextDict(coreBacktestEngine)
            erase!(
                coreBacktestContext,
                [
                    "coreBacktestUnfilteredFactorData",
                    "coreBacktestFilteredFactorData"
                ]
            )
            coreBacktestOutputs["messageRows"] = coreBacktestMsg.rows()
            coreBacktestOutputs["context"] = coreBacktestContext
            coreBacktestOutputs["tradeDetails"] = Backtest::getTradeDetails(coreBacktestEngine)
            coreBacktestOutputs["dailyPositions"] = Backtest::getDailyPosition(coreBacktestEngine)
            coreBacktestOutputs["dailyPortfolios"] = Backtest::getDailyTotalPortfolios(coreBacktestEngine)
            coreBacktestOutputs["returnSummary"] = Backtest::getReturnSummary(coreBacktestEngine)
            coreBacktestOutputs["dailyTradingStatistics"] = Backtest::getDailyTradingStatistics(coreBacktestEngine)
            coreBacktestOutputs["engineStat"] = coreBacktestEngineStat

            coreBacktestOutputs
            """
        )
        if not isinstance(outputs, dict):
            raise TypeError(
                "DolphinDB Backtest 汇总结果必须是字典，实际为 "
                f"{type(outputs).__name__}"
            )

        context = outputs["context"]
        if isinstance(context, dict):
            context.pop("engine", None)

        backtest_result = BacktestResult(
            name=engine_name,
            message_rows=int(outputs["messageRows"]),
            trade_details=as_frame(outputs["tradeDetails"]),
            daily_positions=as_frame(outputs["dailyPositions"]),
            daily_portfolios=as_frame(outputs["dailyPortfolios"]),
            return_summary=as_frame(outputs["returnSummary"]),
            daily_trading_statistics=as_frame(
                outputs["dailyTradingStatistics"]
            ),
            engine_stat=as_frame(outputs["engineStat"]),
            context=context,
        )
        logger.success(
            f"回测完成：name={engine_name}，"
            f"msg={backtest_result.message_rows:,} 行，"
            f"成交明细={len(backtest_result.trade_details):,} 行，"
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
        if owns_session:
            current_session.close()


__all__ = [
    "BacktestResult",
    "Callback",
    "Utility",
    "run_backtest",
]
