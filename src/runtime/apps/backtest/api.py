"""使用因子 DSL 日线构造开收盘单档合成快照并运行 Backtest 策略。"""

from typing import Any
from uuid import uuid4

import numpy as np

from runtime.database import create_session
from runtime.database.session import has_session_variable, redirect_session_output
from runtime.utils import (
    get_stock_metadata,
    logger,
    normalize_date_range,
    normalize_str,
    validate_dolphindb_references,
)

from ..query import api as query_api
from ..query.schema import FactorQuery, QUERY_RESERVED_REFERENCES
from .result import BacktestResult
from .schema import (
    CALLBACK_PARAMETER_COUNTS,
    Adj,
    BacktestParameters,
    CallbackName,
    backtest_symbol,
)

CODES_SOURCE_REF = "coreBacktestCodesSourceData"
CODES_COMPUTED_REF = "coreBacktestCodesComputedData"
CODES_FILTERED_REF = "coreBacktestCodesFilteredData"
CODES_DATA_REF = "coreBacktestCodesData"


SOURCE_REF = "coreBacktestSourceData"
COMPUTED_REF = "coreBacktestComputedData"
FILTERED_REF = "coreBacktestFilteredData"
DATA_REF = "coreBacktestData"
MESSAGE_REF = "coreBacktestMessage"
BENCHMARK_SOURCE_REF = "coreBacktestBenchmarkSourceData"
BENCHMARK_COMPUTED_REF = "coreBacktestBenchmarkComputedData"
BENCHMARK_FILTERED_REF = "coreBacktestBenchmarkFilteredData"
BENCHMARK_DATA_REF = "coreBacktestBenchmarkData"
BENCHMARK_MESSAGE_REF = "coreBacktestBenchmarkMessage"
DAILY_MESSAGE_FACTORS = ("open", "low", "high", "close", "up_limit", "down_limit", "pre_close")
BACKTEST_RESERVED_REFERENCES = QUERY_RESERVED_REFERENCES | frozenset({
    "coreBacktestName",
    "coreBacktestConfig",
    "coreBacktestCodes",
    "coreBacktestStartDate",
    "coreBacktestEndDate",
    "coreBacktestAnnualTradingDays",
    "coreBacktestRiskFreeRate",
    "coreBacktestAdj",
    "coreBacktestSyntheticSpread",
    "coreBacktestBenchmark",
    "coreBacktestParams",
    "coreBacktestCodeToIndustry",
    "coreBacktestAvailableTradeDates",
    "coreBacktestTradeDates",
    "coreBacktestRunMessage",
    "getParams",
    "getParam",
    "getIndustry",
    "getTradeDates",
    "coreBacktestEngine",
    "coreLoadedPlugins",
    "coreBacktestComputedData",
    "coreBacktestFilteredData",
    "coreBacktestData",
    "coreBacktestBenchmarkSourceData",
    "coreBacktestBenchmarkComputedData",
    "coreBacktestBenchmarkFilteredData",
    "coreBacktestBenchmarkData",
    "coreBacktestBenchmarkMessage",
    "coreBacktestCodesSourceData",
    "coreBacktestCodesComputedData",
    "coreBacktestCodesFilteredData",
    "coreBacktestCodesData",
})
BACKTEST_SESSION_MAX_TIME = 60 * 60
STOCK_POOL_MEMBER = "stock_pool_member"
STATIC_STOCK_POOL_MEMBER = {
    "type": "DIRECT",
    "op": "nullary.true",
    "fields": {},
    "params": {},
}


def backtest_industry_mapping() -> dict[str, str]:
    """Return Factor research industries keyed by Backtest canonical symbols."""
    result: dict[str, str] = {}
    for code, industry in get_stock_metadata()[2].items():
        if code.endswith(".SZ"):
            result[f"{code[:-3]}.XSHE"] = industry
        elif code.endswith(".SH"):
            result[f"{code[:-3]}.XSHG"] = industry
    return result


def managed_backtest_dataset_query(
    parameters: BacktestParameters,
) -> FactorQuery:
    """Inject point-in-time membership without mutating either saved DSL source."""
    dataset = parameters.dataset_query.model_dump(mode="json")
    derivatives = dict(dataset["derivatives"])
    if parameters.codes_query is None:
        member: Any = STATIC_STOCK_POOL_MEMBER
    else:
        member = None
        if STOCK_POOL_MEMBER in parameters.codes_query.filters:
            codes_member = parameters.codes_query.derivatives.get(
                STOCK_POOL_MEMBER
            )
            if codes_member is not None:
                member = codes_member.model_dump(mode="json")
        if member is None:
            member = derivatives.get(STOCK_POOL_MEMBER)
        if member is None:
            member = STATIC_STOCK_POOL_MEMBER
    derivatives[STOCK_POOL_MEMBER] = member
    dataset["factors"] = [
        factor
        for factor in dataset["factors"]
        if factor != STOCK_POOL_MEMBER
    ]
    dataset["derivatives"] = derivatives
    return FactorQuery.model_validate(dataset)


def load_backtest_environment(session: Any, *, log_progress: bool = True) -> None:
    """加载回测脚本编译和执行依赖的插件及模块。"""
    if log_progress:
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
    if log_progress:
        logger.info("session.run: 加载 factor 和 backtest 模块")
    session.run("use factor")
    session.run("use backtest")


def compile_backtest_scripts(parameters: BacktestParameters, session: Any | None = None) -> None:
    """在独立 DolphinDB 会话中编译 utils 和全部回调，提交前暴露语法错误。"""
    owns_session = session is None
    current_session = (
        create_session(max_time=BACKTEST_SESSION_MAX_TIME)
        if owns_session
        else session
    )
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


def prepare_backtest_session(
        parameters: BacktestParameters,
        session: Any,
        *,
        source_ref: str = SOURCE_REF,
        message_ref: str = MESSAGE_REF,
        log_progress: bool = True,
) -> BacktestParameters:
    """在一个 session 中一次性生成完整区间数据、消息表和策略函数。"""
    validate_dolphindb_references(
        {"source_ref": source_ref, "message_ref": message_ref},
        reserved=BACKTEST_RESERVED_REFERENCES | frozenset(CALLBACK_PARAMETER_COUNTS),
    )
    execution_factors = [
        factor
        for factor in parameters.dataset_query.factors
        if factor != STOCK_POOL_MEMBER
    ]
    execution_factors.extend(factor for factor in DAILY_MESSAGE_FACTORS if factor not in execution_factors)
    if parameters.adj is not None and "adj_factor" not in execution_factors:
        execution_factors.append("adj_factor")
    dataset_query = managed_backtest_dataset_query(parameters).model_copy(
        update={"factors": execution_factors}
    )
    benchmark = parameters.config.get("benchmark")
    synthetic_spread = parameters.config.get("syntheticSpread", 0.0)
    message_exists = has_session_variable(
        session,
        message_ref,
        log_progress=log_progress,
    )

    if not message_exists:
        if parameters.codes_query is not None:
            codes = query_api.execute_codes_query(
                parameters.codes_query,
                session=session,
                source_ref=CODES_SOURCE_REF,
                computed_ref=CODES_COMPUTED_REF,
                filtered_ref=CODES_FILTERED_REF,
                data_ref=CODES_DATA_REF,
                log_progress=log_progress,
            )
            dataset_query = dataset_query.model_copy(update={"codes": codes})

        query_api.build_query_table(
            dataset_query,
            session=session,
            source_ref=source_ref,
            computed_ref=COMPUTED_REF,
            filtered_ref=FILTERED_REF,
            data_ref=DATA_REF,
            log_progress=log_progress,
        )
        if log_progress:
            logger.info("session.run: 统一回测证券代码为 XSHG/XSHE 格式")
        session.run(f"""
            replaceColumn!({source_ref}, `code, symbol(strReplace(strReplace(string({source_ref}.code), ".SZ", ".XSHE"), ".SH", ".XSHG")))
            replaceColumn!({COMPUTED_REF}, `code, symbol(strReplace(strReplace(string({COMPUTED_REF}.code), ".SZ", ".XSHE"), ".SH", ".XSHG")))
            replaceColumn!({FILTERED_REF}, `code, symbol(strReplace(strReplace(string({FILTERED_REF}.code), ".SZ", ".XSHE"), ".SH", ".XSHG")))
            replaceColumn!({DATA_REF}, `code, symbol(strReplace(strReplace(string({DATA_REF}.code), ".SZ", ".XSHE"), ".SH", ".XSHG")))
        """)
        if benchmark is not None:
            benchmark_query = FactorQuery(
                start_date=dataset_query.start_date,
                end_date=dataset_query.end_date,
                lookback="P0D",
                codes=[benchmark],
                factors=list(DAILY_MESSAGE_FACTORS),
                derivatives={},
                filters=[],
            )
            query_api.build_query_table(
                benchmark_query,
                session=session,
                source_ref=BENCHMARK_SOURCE_REF,
                computed_ref=BENCHMARK_COMPUTED_REF,
                filtered_ref=BENCHMARK_FILTERED_REF,
                data_ref=BENCHMARK_DATA_REF,
                log_progress=log_progress,
            )
            if log_progress:
                logger.info("session.run: 统一基准指数代码为 XSHG/XSHE 格式")
            session.run(f"""
                replaceColumn!({BENCHMARK_SOURCE_REF}, `code, symbol(strReplace(strReplace(string({BENCHMARK_SOURCE_REF}.code), ".SZ", ".XSHE"), ".SH", ".XSHG")))
                replaceColumn!({BENCHMARK_COMPUTED_REF}, `code, symbol(strReplace(strReplace(string({BENCHMARK_COMPUTED_REF}.code), ".SZ", ".XSHE"), ".SH", ".XSHG")))
                replaceColumn!({BENCHMARK_FILTERED_REF}, `code, symbol(strReplace(strReplace(string({BENCHMARK_FILTERED_REF}.code), ".SZ", ".XSHE"), ".SH", ".XSHG")))
                replaceColumn!({BENCHMARK_DATA_REF}, `code, symbol(strReplace(strReplace(string({BENCHMARK_DATA_REF}.code), ".SZ", ".XSHE"), ".SH", ".XSHG")))
            """)
    else:
        if log_progress:
            logger.info(f"复用回测数据和消息表 {message_ref}")

    session.upload({
        "coreBacktestCodes": np.asarray(dataset_query.codes, dtype=str),
        "coreBacktestAnnualTradingDays": parameters.annual_trading_days,
        "coreBacktestRiskFreeRate": parameters.risk_free_rate,
        "coreBacktestAdj": parameters.adj or "",
        "coreBacktestSyntheticSpread": synthetic_spread,
        "coreBacktestBenchmark": backtest_symbol(benchmark) if benchmark is not None else "",
        "coreBacktestCodeToIndustry": backtest_industry_mapping(),
    })
    load_backtest_environment(session, log_progress=log_progress)
    if parameters.utils:
        if log_progress:
            logger.info("session.run: 执行 utils 脚本")
        session.run(parameters.utils)
    if log_progress:
        logger.info(f"session.run: 定义回调函数 {list(parameters.callbacks)}")
    session.run("\n".join(parameters.callbacks.values()))

    if not message_exists:
        if log_progress:
            logger.info(f"session.run: 生成回测消息表 {message_ref}")
        if benchmark is None:
            session.run(f"""
                {message_ref} = backtest::build_backtest_message(
                    {DATA_REF},
                    coreBacktestAdj,
                    coreBacktestSyntheticSpread
                )
            """)
        else:
            session.run(f"""
                {message_ref} = backtest::build_backtest_message(
                    {DATA_REF},
                    coreBacktestAdj,
                    coreBacktestSyntheticSpread
                )
                {message_ref} = select *
                from {message_ref}
                where string(symbol) != coreBacktestBenchmark
                if ({message_ref}.rows() == 0) {{
                    throw "排除基准指数后回测行情为空"
                }}
                {BENCHMARK_MESSAGE_REF} = backtest::build_backtest_message(
                    {BENCHMARK_DATA_REF},
                    NULL,
                    0.0
                )
                {message_ref} = unionAll(
                    {message_ref},
                    {BENCHMARK_MESSAGE_REF}
                )
                {message_ref}.sortBy!(`timestamp`symbol)
            """)
    if log_progress:
        logger.info(f"session.run: 缓存回测交易日期 {message_ref}")
    session.run(f"""
        coreBacktestAvailableTradeDates = exec distinct date(timestamp)
        from {message_ref}
        order by date(timestamp)
    """)
    return parameters.model_copy(update={"dataset_query": dataset_query})


def execute_prepared_backtest(
        parameters: BacktestParameters,
        session: Any,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        params: dict[str, Any] | None = None,
        name: str | None = None,
        message_ref: str = MESSAGE_REF,
        log_progress: bool = True,
) -> str:
    """复用当前 session 的数据和消息表运行一个独立 Backtest 引擎。"""
    output_start, output_end = normalize_date_range(
        start_date or parameters.dataset_query.start_date,
        end_date or parameters.dataset_query.end_date,
    )
    query_start, query_end = normalize_date_range(
        parameters.dataset_query.start_date,
        parameters.dataset_query.end_date,
    )
    if output_start < query_start or output_end > query_end:
        raise ValueError("回测区间必须位于已准备的数据区间内")
    engine_name = normalize_str(name, "name") if name is not None else f"coreBacktest_{uuid4().hex}"
    backtest_config = dict(parameters.config)
    backtest_config.pop("syntheticSpread", None)
    if benchmark := backtest_config.get("benchmark"):
        backtest_config["benchmark"] = backtest_symbol(benchmark)
    backtest_config.update({
        "startDate": output_start.to_datetime64().astype("datetime64[D]"),
        "endDate": output_end.to_datetime64().astype("datetime64[D]"),
        "strategyGroup": "stock",
        "dataType": np.int32(1),
        "matchingMode": np.int32(1),
        "frequency": np.int32(0),
        "callbackForSnapshot": np.int32(0),
        "msgAsTable": True,
        "msgAsPiecesOnSnapshot": True,
        "matchingRatio": 0.0,
        "orderBookMatchingRatio": 1.0,
    })
    session.upload({
        "coreBacktestName": engine_name,
        "coreBacktestConfig": backtest_config,
        "coreBacktestStartDate": output_start,
        "coreBacktestEndDate": output_end,
    })
    if log_progress:
        logger.info("session.run: 初始化策略参数字典")
    session.run("coreBacktestParams = dict(STRING, ANY)")
    run_params = parameters.params if params is None else params
    if run_params:
        session.upload({"coreBacktestParams": run_params})
    run_message_ref = message_ref
    message_statement = ""
    if output_start != query_start or output_end != query_end:
        run_message_ref = "coreBacktestRunMessage"
        message_statement = f"""
            coreBacktestRunMessage = select *
            from {message_ref}
            where date(timestamp) >= coreBacktestStartDate,
                  date(timestamp) <= coreBacktestEndDate
        """
    if log_progress:
        logger.info(f"session.run: 创建并运行回测引擎 {engine_name}")
    session.run(f"""
        {message_statement}

        coreBacktestTradeDates = coreBacktestAvailableTradeDates[
            coreBacktestAvailableTradeDates >= date(coreBacktestStartDate) &&
            coreBacktestAvailableTradeDates <= date(coreBacktestEndDate)
        ]

        coreBacktestEngine = backtest::run_backtest(
            coreBacktestName,
            coreBacktestConfig,
            {run_message_ref},
            initialize,
            beforeTrading,
            onBar,
            onSnapshot,
            onOrder,
            onTrade,
            afterTrading,
            finalize
        )
    """)
    return engine_name


def drop_prepared_backtest_engine(
        session: Any,
        *,
        log_progress: bool = False,
) -> None:
    """清理复用会话中的当前回测引擎，异常路径重复调用也是安全的。"""
    if not has_session_variable(
        session,
        "coreBacktestEngine",
        log_progress=log_progress,
    ):
        return
    try:
        session.run("Backtest::dropBacktestEngine(coreBacktestEngine)")
    except RuntimeError as error:
        if log_progress:
            logger.debug(f"回测引擎已由插件清理：{error}")
    finally:
        session.run("undef(`coreBacktestEngine, VAR)")


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
    """使用日线合成的开收盘快照回测，并把结果会话移交给惰性结果。"""
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
    owns_session = session is None
    current_session = (
        create_session(max_time=BACKTEST_SESSION_MAX_TIME)
        if owns_session
        else session
    )
    redirect_session_output(current_session)

    try:
        prepared = prepare_backtest_session(
            parameters,
            current_session,
            source_ref=source_ref,
            message_ref=message_ref,
        )
        engine_name = execute_prepared_backtest(
            prepared,
            current_session,
            name=name,
            message_ref=message_ref,
        )
        backtest_result = BacktestResult(session=current_session)
        logger.success(f"回测完成：name={engine_name}")
        return backtest_result
    except Exception:
        logger.exception(f"回测失败：name={name or '自动生成'}")
        if owns_session:
            current_session.close()
        raise
