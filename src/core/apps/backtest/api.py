"""使用因子 DSL 构造日频消息并运行 DolphinDB Backtest 策略。"""

from uuid import uuid4
from typing import Any

import numpy as np

from core.utils import CODE_COLUMN, logger, normalize_date_range
from core.database import create_session
from core.database.session import has_session_variable, redirect_session_output

from .result import BacktestResult
from .schema import CallbackName, Adj, BacktestParameters
from ..query import FactorQuery, api as query_api

CODES_SOURCE_REF = "coreBacktestCodesSourceData"
CODES_COMPUTED_REF = "coreBacktestCodesComputedData"
CODES_FILTERED_REF = "coreBacktestCodesFilteredData"


def execute_codes_query(codes_query: FactorQuery, session: Any) -> list[str]:
    """执行股票池查询并返回股票代码。"""
    query_api.build_query_table(codes_query, session=session, source_ref=CODES_SOURCE_REF,
                                computed_ref=CODES_COMPUTED_REF, filtered_ref=CODES_FILTERED_REF)
    logger.info(f"session.run: 从 {CODES_FILTERED_REF} 读取选股结果")
    selected_codes = session.run(
        f"""
        exec distinct {CODE_COLUMN}
        from {CODES_FILTERED_REF}
        where
            time >= coreOutputStart,
            time < coreOutputEndExclusive,
            not isNull({CODE_COLUMN})
        order by {CODE_COLUMN}
        """
    )
    if not isinstance(selected_codes, np.ndarray):
        raise TypeError(f"codes DSL 必须返回一维代码向量，实际为 {type(selected_codes).__name__}")
    if selected_codes.ndim != 1:
        raise ValueError(f"codes DSL 必须返回一维代码向量，实际维数为 {selected_codes.ndim}")
    codes = selected_codes.astype(str).tolist()
    if not codes:
        raise ValueError("codes DSL 没有选出任何股票")
    unsupported_codes = [code for code in codes if not code.endswith((".SH", ".SZ"))]
    if unsupported_codes:
        raise ValueError(f"codes DSL 只能返回 .SH 和 .SZ 股票代码：{unsupported_codes[:10]}")
    logger.info(f"codes DSL 选出 {len(codes):,} 只股票")
    return codes


SOURCE_REF = "coreBacktestSourceData"
COMPUTED_REF = "coreBacktestComputedData"
FILTERED_REF = "coreBacktestFilteredData"
MESSAGE_REF = "coreBacktestMessage"


def run_backtest(
        dataset_query: dict[str, Any],
        callbacks: dict[CallbackName, str],
        *,
        session: Any = None,
        codes_query: dict[str, Any] = None,
        utils: dict[str, str] = None,
        name: str = None,
        config: dict[str, Any] = None,
        adj: Adj = None,
        risk_free_rate: float = 0.04,
        annual_trading_days: int = 250,
        source_ref: str = SOURCE_REF,
        message_ref: str = MESSAGE_REF,
) -> BacktestResult:
    """运行日频回测，并把保存服务端输出的会话移交给惰性结果。"""
    parameters = BacktestParameters.model_validate({
        "dataset_query": dataset_query,
        "callbacks": callbacks,
        "utils": utils,
        "codes_query": codes_query,
        "adj": adj,
        "name": name,
        "config": config,
        "annual_trading_days": annual_trading_days,
        "risk_free_rate": risk_free_rate,
        "source_ref": source_ref,
        "message_ref": message_ref,
    })
    engine_name = parameters.name or f"coreBacktest_{uuid4().hex}"
    backtest_config = dict(parameters.config)
    owns_session = session is None
    current_session = create_session() if owns_session else session
    redirect_session_output(current_session)

    try:
        validated_dataset_query = parameters.dataset_query

        if parameters.codes_query is not None:
            codes = execute_codes_query(parameters.codes_query, current_session)
            validated_dataset_query = validated_dataset_query.model_copy(update={"codes": codes})

        query_api.build_query_table(
            validated_dataset_query,
            session=current_session,
            source_ref=parameters.source_ref,
            computed_ref=COMPUTED_REF,
            filtered_ref=FILTERED_REF
        )

        output_start, output_end = normalize_date_range(
            validated_dataset_query.start_date,
            validated_dataset_query.end_date
        )
        backtest_config.update(
            {
                "startDate": output_start.to_datetime64().astype("datetime64[D]"),
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
                "coreBacktestCodes": np.asarray(validated_dataset_query.codes, dtype=str),
                "coreBacktestStartDate": output_start,
                "coreBacktestEndDate": output_end,
                "coreBacktestAnnualTradingDays": parameters.annual_trading_days,
                "coreBacktestRiskFreeRate": parameters.risk_free_rate,
                "coreBacktestAdj": parameters.adj or "",
            }
        )

        # DolphinDB resolves plugin functions while compiling a module, before
        # executing that module's top-level statements. The plugins therefore
        # have to be loaded before `use backtest` compiles backtest.dos.
        logger.info("session.run: 加载 Backtest 和 MatchingEngineSimulator 插件")
        current_session.run(
            """
            coreLoadedPlugins = exec plugin from getLoadedPlugins()
            if (!("MatchingEngineSimulator" in coreLoadedPlugins)) {
                loadPlugin("MatchingEngineSimulator")
            }
            if (!("Backtest" in coreLoadedPlugins)) {
                loadPlugin("Backtest")
            }
            """
        )

        logger.info("session.run: 加载 backtest 模块")
        current_session.run("use backtest")

        logger.info(f"session.run: 定义工具函数 {list(parameters.utils)}")
        current_session.run("\n".join(parameters.utils.values()))

        logger.info(f"session.run: 定义回调函数 {list(parameters.callbacks)}")
        current_session.run("\n".join(parameters.callbacks.values()))

        if not has_session_variable(current_session, parameters.message_ref):
            logger.info(f"session.run: 生成回测消息表 {parameters.message_ref}")
            current_session.run(f"""
                {parameters.message_ref} = backtest::build_backtest_message(
                    project_factor_output(
                        {COMPUTED_REF},
                        coreDslOutputColumns,
                        coreOutputStart,
                        coreOutputEndExclusive
                    ),
                    coreBacktestAdj
                )
            """)
        else:
            logger.info(f"复用回测消息表 {parameters.message_ref}")

        logger.info(f"session.run: 创建并运行回测引擎 {engine_name}")
        current_session.run(f"""
            coreBacktestEngine = backtest::run_backtest(
                coreBacktestName,
                coreBacktestConfig,
                {parameters.message_ref},
                {COMPUTED_REF},
                {FILTERED_REF},
                {"initialize" if "initialize" in parameters.callbacks else "NULL"},
                {"beforeTrading" if "beforeTrading" in parameters.callbacks else "NULL"},
                {"onBar" if "onBar" in parameters.callbacks else "NULL"},
                {"onSnapshot" if "onSnapshot" in parameters.callbacks else "NULL"},
                {"onOrder" if "onOrder" in parameters.callbacks else "NULL"},
                {"onTrade" if "onTrade" in parameters.callbacks else "NULL"},
                {"afterTrading" if "afterTrading" in parameters.callbacks else "NULL"},
                {"finalize" if "finalize" in parameters.callbacks else "NULL"}
            )
            """
                            )
        backtest_result = BacktestResult(session=current_session)
        logger.success(f"回测完成：name={engine_name}")
        return backtest_result
    except Exception:
        logger.exception(f"回测失败：name={engine_name}")
        if owns_session:
            current_session.close()
        raise


__all__ = ["run_backtest"]
