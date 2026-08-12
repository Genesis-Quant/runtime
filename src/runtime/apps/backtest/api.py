"""使用因子 DSL 构造日频消息并运行 DolphinDB Backtest 策略。"""

from typing import Any
from uuid import uuid4

import numpy as np

from runtime.database import create_session
from runtime.database.session import has_session_variable, redirect_session_output
from runtime.utils import (
    logger,
    normalize_date_range,
    normalize_str,
    validate_dolphindb_references,
)

from ..query import api as query_api
from ..query.schema import QUERY_RESERVED_REFERENCES
from .result import BacktestResult
from .schema import CALLBACK_PARAMETER_COUNTS, Adj, BacktestParameters, CallbackName

CODES_SOURCE_REF = "coreBacktestCodesSourceData"
CODES_COMPUTED_REF = "coreBacktestCodesComputedData"
CODES_FILTERED_REF = "coreBacktestCodesFilteredData"
CODES_DATA_REF = "coreBacktestCodesData"


SOURCE_REF = "coreBacktestSourceData"
COMPUTED_REF = "coreBacktestComputedData"
FILTERED_REF = "coreBacktestFilteredData"
DATA_REF = "coreBacktestData"
MESSAGE_REF = "coreBacktestMessage"
DAILY_MESSAGE_FACTORS = ("open", "low", "high", "close", "vol", "up_limit", "down_limit", "pre_close")
BACKTEST_RESERVED_REFERENCES = QUERY_RESERVED_REFERENCES | frozenset({
    "coreBacktestName",
    "coreBacktestConfig",
    "coreBacktestCodes",
    "coreBacktestStartDate",
    "coreBacktestEndDate",
    "coreBacktestAnnualTradingDays",
    "coreBacktestRiskFreeRate",
    "coreBacktestAdj",
    "coreBacktestParams",
    "getParams",
    "coreBacktestEngine",
    "coreLoadedPlugins",
    "coreBacktestComputedData",
    "coreBacktestFilteredData",
    "coreBacktestData",
    "coreBacktestCodesSourceData",
    "coreBacktestCodesComputedData",
    "coreBacktestCodesFilteredData",
    "coreBacktestCodesData",
})


def load_backtest_environment(session: Any) -> None:
    """加载回测脚本编译和执行依赖的插件及模块。"""
    logger.info("session.run: 加载 Backtest 和 MatchingEngineSimulator 插件")
    session.run(
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
    session.run("use backtest")


def compile_backtest_scripts(parameters: BacktestParameters, session: Any | None = None) -> None:
    """在独立 DolphinDB 会话中编译 utils 和全部回调，提交前暴露语法错误。"""
    owns_session = session is None
    current_session = create_session() if owns_session else session
    redirect_session_output(current_session)
    try:
        load_backtest_environment(current_session)
        if parameters.utils:
            logger.info("session.run: 编译 utils 脚本")
            current_session.run(parameters.utils)
        logger.info(f"session.run: 编译回调函数 {list(parameters.callbacks)}")
        current_session.run("\n".join(parameters.callbacks.values()))
    finally:
        if owns_session:
            current_session.close()


def run_backtest(
        dataset_query: dict[str, Any],
        callbacks: dict[CallbackName, str],
        *,
        session: Any | None = None,
        codes_query: dict[str, Any] | None = None,
        utils: str = "",
        params: dict[str, Any] | None = None,
        name: str | None = None,
        config: dict[str, Any] | None = None,
        adj: Adj | None = None,
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
        "params": params if params is not None else {},
        "codes_query": codes_query,
        "adj": adj,
        "config": config,
        "annual_trading_days": annual_trading_days,
        "risk_free_rate": risk_free_rate,
    })
    validate_dolphindb_references(
        {"source_ref": source_ref, "message_ref": message_ref},
        reserved=BACKTEST_RESERVED_REFERENCES | frozenset(CALLBACK_PARAMETER_COUNTS),
    )
    engine_name = normalize_str(name, "name") if name is not None else f"coreBacktest_{uuid4().hex}"
    backtest_config = dict(parameters.config)
    owns_session = session is None
    current_session = create_session() if owns_session else session
    redirect_session_output(current_session)

    try:
        execution_factors = list(parameters.dataset_query.factors)
        execution_factors.extend(factor for factor in DAILY_MESSAGE_FACTORS if factor not in execution_factors)
        if parameters.adj is not None and "adj_factor" not in execution_factors:
            execution_factors.append("adj_factor")
        validated_dataset_query = parameters.dataset_query.model_copy(update={"factors": execution_factors})

        if parameters.codes_query is not None:
            codes = query_api.execute_codes_query(
                parameters.codes_query,
                session=current_session,
                source_ref=CODES_SOURCE_REF,
                computed_ref=CODES_COMPUTED_REF,
                filtered_ref=CODES_FILTERED_REF,
                data_ref=CODES_DATA_REF,
            )
            validated_dataset_query = validated_dataset_query.model_copy(update={"codes": codes})

        query_api.build_query_table(
            validated_dataset_query,
            session=current_session,
            source_ref=source_ref,
            computed_ref=COMPUTED_REF,
            filtered_ref=FILTERED_REF,
            data_ref=DATA_REF
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
                "matchingMode": 2,
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
        current_session.run("coreBacktestParams = dict(STRING, ANY)")
        if parameters.params:
            current_session.upload({"coreBacktestParams": parameters.params})

        # DolphinDB resolves plugin functions while compiling a module, before
        # executing that module's top-level statements. Load the environment
        # before compiling user utilities and callbacks.
        load_backtest_environment(current_session)

        if parameters.utils:
            logger.info("session.run: 执行 utils 脚本")
            current_session.run(parameters.utils)

        logger.info(f"session.run: 定义回调函数 {list(parameters.callbacks)}")
        current_session.run("\n".join(parameters.callbacks.values()))

        if not has_session_variable(current_session, message_ref):
            logger.info(f"session.run: 生成回测消息表 {message_ref}")
            current_session.run(f"""
                {message_ref} = backtest::build_backtest_message(
                    {DATA_REF},
                    coreBacktestAdj
                )
            """)
        else:
            logger.info(f"复用回测消息表 {message_ref}")

        logger.info(f"session.run: 创建并运行回测引擎 {engine_name}")
        current_session.run(f"""
            coreBacktestEngine = backtest::run_backtest(
                coreBacktestName,
                coreBacktestConfig,
                {message_ref},
                {COMPUTED_REF},
                {FILTERED_REF},
                initialize,
                beforeTrading,
                onBar,
                onSnapshot,
                onOrder,
                onTrade,
                afterTrading,
                finalize
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
