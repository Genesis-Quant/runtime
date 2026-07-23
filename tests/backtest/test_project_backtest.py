"""使用真实历史行情验证项目 run_backtest 的时序和清理逻辑。"""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest

from core.backtest import run_backtest


pytestmark = [pytest.mark.dolphindb, pytest.mark.backtest]

BASE_QUERY = {
    "start_date": "2025-01-02",
    "end_date": "2025-01-13",
    "lookback": "0D",
    "codes": ["000001.SZ"],
    "factors": ["open", "low", "high", "close", "amount"],
    "derivatives": {
        "volume": {
            "type": "DIRECT",
            "op": "unary.cast",
            "fields": {
                "col": {
                    "type": "DIRECT",
                    "op": "binary.mul",
                    "fields": {"left": "vol", "right": 100},
                    "params": {},
                }
            },
            "params": {"dtype": "long"},
        },
        "upLimitPrice": {
            "type": "DIRECT",
            "op": "unary.cast",
            "fields": {"col": "up_limit"},
            "params": {"dtype": "double"},
        },
        "downLimitPrice": {
            "type": "DIRECT",
            "op": "unary.cast",
            "fields": {"col": "down_limit"},
            "params": {"dtype": "double"},
        },
        "prevClosePrice": {
            "type": "DIRECT",
            "op": "unary.cast",
            "fields": {"col": "pre_close"},
            "params": {"dtype": "double"},
        },
        "tradable": {
            "type": "DIRECT",
            "op": "unary.not_null",
            "fields": {"col": "close"},
            "params": {},
        },
        "eligible": {
            "type": "DIRECT",
            "op": "binary.gt",
            "fields": {"left": "close", "right": 11.4},
            "params": {},
        },
        "rawSignal": {
            "type": "CS",
            "op": "unary.top_n",
            "fields": {"col": "close"},
            "params": {"n": 1},
            "on": "eligible",
        },
    },
    "filters": ["tradable"],
}

TRADING_CALLBACKS = {
    "initialize": """
        def projectInitialize(mutable context) {
            if (!("signalTimes" in context)) {
                context["signalTimes"] = array(TIMESTAMP, 0)
                context["executionTimes"] = array(TIMESTAMP, 0)
                context["callbackCount"] = 0
            }
        }
    """,
    "onBar": """
        def projectOnBar(mutable context, msg, indicator) {
            if (msg.rows() == 0) return
            context["callbackCount"] += 1
            context["signalTimes"].append!(take(msg.tradeTime[0], 1))
            context["executionTimes"].append!(take(context.tradeTime, 1))
            if (context["callbackCount"] == 1) {
                context["signalType"] = typestr(msg.rawSignal)
            }

            symbol = msg.symbol[0]
            position = Backtest::getPosition(context.engine, symbol)
            longPosition = position.longPosition.sum()
            selected = nullFill(msg.rawSignal[0], false)
            if (selected && longPosition < 1) {
                Backtest::submitOrder(
                    context.engine,
                    (symbol, context.tradeTime, 0, msg.close[0], long(100), 1),
                    "project-buy"
                )
            } else if (!selected && longPosition > 0) {
                Backtest::submitOrder(
                    context.engine,
                    (
                        symbol,
                        context.tradeTime,
                        0,
                        msg.close[0],
                        longPosition,
                        3
                    ),
                    "project-sell"
                )
            }
        }
    """,
}

TRACE_CALLBACKS = {
    "initialize": """
        def traceInitialize(mutable context) {
            if (!("signalTimes" in context)) {
                context["signalTimes"] = array(TIMESTAMP, 0)
                context["executionTimes"] = array(TIMESTAMP, 0)
            }
        }
    """,
    "onBar": """
        def traceOnBar(mutable context, msg, indicator) {
            context["signalTimes"].append!(take(msg.tradeTime[0], 1))
            context["executionTimes"].append!(take(context.tradeTime, 1))
        }
    """,
}


def load_playground_defaults() -> dict[str, Any]:
    """用 Node.js 读取 Playground 实际使用的 JavaScript 默认对象。"""
    html = (
        Path(__file__).parents[2] / "core" / "playground" / "backtest.html"
    ).read_text(encoding="utf-8")
    module = html.split('<script type="module">', 1)[1].split(
        "const state =",
        1,
    )[0]
    node_source = f"""
const vm = require("node:vm");
const source = {json.dumps(module)};
const sandbox = {{}};
vm.runInNewContext(
    source + `
globalThis.result = JSON.stringify({{
    codesQuery: CODES_QUERY_TEMPLATE,
    query: QUERY_TEMPLATE,
    utils: UTILS_TEMPLATES,
    callbacks: STRATEGY_TEMPLATES
}});`,
    sandbox
);
process.stdout.write(sandbox.result);
"""
    completed = subprocess.run(
        ["node", "-e", node_source],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


def assert_engine_dropped(session: Any, engine_name: str) -> None:
    """确认项目在成功或失败后都没有留下命名回测引擎。"""
    session.upload({"projectTestEngineName": engine_name})
    exists = session.run(
        "projectTestEngineName in Backtest::getBacktestEngineList()"
    )
    assert not bool(exists)


def test_previous_signal_executes_at_current_open_and_accounts_exactly(
    ddb_session: Any,
) -> None:
    """上一交易日信号应在当前开盘执行，全部资金结果应可手工复算。"""
    engine_name = f"project_timing_{uuid4().hex}"
    result = run_backtest(
        deepcopy(BASE_QUERY),
        TRADING_CALLBACKS,
        name=engine_name,
        config={
            "cash": 1_000_000,
            "commission": 0.001,
            "tax": 0.002,
            "matchingMode": 2,
            "outputOrderInfo": True,
        },
        session=ddb_session,
    )

    assert result.message_rows == 8
    assert result.context["callbackCount"] == 6
    assert result.context["signalType"] == "FAST INT VECTOR"
    assert result.context["signalTimes"].tolist() == [
        np.datetime64("2025-01-02T15:00:00.000"),
        np.datetime64("2025-01-03T15:00:00.000"),
        np.datetime64("2025-01-06T15:00:00.000"),
        np.datetime64("2025-01-07T15:00:00.000"),
        np.datetime64("2025-01-08T15:00:00.000"),
        np.datetime64("2025-01-09T15:00:00.000"),
    ]
    assert result.context["executionTimes"].tolist() == [
        np.datetime64("2025-01-03T15:00:00.000"),
        np.datetime64("2025-01-06T15:00:00.000"),
        np.datetime64("2025-01-07T15:00:00.000"),
        np.datetime64("2025-01-08T15:00:00.000"),
        np.datetime64("2025-01-09T15:00:00.000"),
        np.datetime64("2025-01-10T15:00:00.000"),
    ]

    filled = result.trade_details.loc[
        result.trade_details["orderStatus"].eq(1)
    ].reset_index(drop=True)
    assert filled["direction"].tolist() == [1, 3, 1, 3]
    assert filled["tradeQty"].tolist() == [100, 100, 100, 100]
    assert filled["tradePrice"].tolist() == pytest.approx(
        [11.44, 11.38, 11.42, 11.40]
    )
    assert filled["tradeTime"].tolist() == [
        pd.Timestamp("2025-01-03 15:00:00"),
        pd.Timestamp("2025-01-06 15:00:00"),
        pd.Timestamp("2025-01-07 15:00:00"),
        pd.Timestamp("2025-01-10 15:00:00"),
    ]

    first_round = (11.38 - 11.44) * 100
    first_fees = 11.44 * 100 * 0.001 + 11.38 * 100 * 0.003
    second_round = (11.40 - 11.42) * 100
    second_fees = 11.42 * 100 * 0.001 + 11.40 * 100 * 0.003
    expected_pnl = first_round + second_round - first_fees - second_fees
    final = result.daily_portfolios.iloc[-1]
    assert expected_pnl == pytest.approx(-17.12)
    assert final["totalFee"] == pytest.approx(9.12)
    assert final["totalPnl"] == pytest.approx(expected_pnl)
    assert final["cash"] == pytest.approx(1_000_000 + expected_pnl)
    assert final["totalMarketValue"] == pytest.approx(0)
    assert final["totalEquity"] == pytest.approx(1_000_000 + expected_pnl)
    assert result.engine_stat.loc[0, "status"] == "END"
    assert_engine_dropped(ddb_session, engine_name)


def test_playground_risk_parity_default_runs_end_to_end(
    ddb_session: Any,
) -> None:
    """Playground 默认多因子风险平价策略应完成真实数据回测。"""
    defaults = load_playground_defaults()
    scope = {
        "start_date": "2025-01-01",
        "end_date": "2025-03-31",
        "lookback": "180D",
        "codes": [],
    }
    codes_query = {**scope, **defaults["codesQuery"]}
    query = {**scope, **defaults["query"]}
    engine_name = f"project_risk_parity_{uuid4().hex}"

    result = run_backtest(
        query,
        defaults["callbacks"],
        utils=defaults["utils"],
        codes_query=codes_query,
        name=engine_name,
        config={
            "cash": 1_000_000,
            "commission": 0.00015,
            "tax": 0.001,
            "matchingMode": 2,
            "outputOrderInfo": True,
        },
        session=ddb_session,
    )

    assert set(defaults["utils"]) == {
        "equalRiskContributionWeights",
        "getBacktestHistory",
        "riskParityCovariance",
    }
    assert all(
        definition.count("def ") == 1
        for definition in defaults["utils"].values()
    )
    assert all(
        definition.count("def ") == 1
        for definition in defaults["callbacks"].values()
    )
    assert result.message_rows > 0
    assert result.context["rebalanceCount"] > 0
    assert result.context["lastSelectedCount"] == 20
    assert result.context["lastWeightSum"] == pytest.approx(1)
    assert result.context["lastCovarianceObservations"] == 60
    assert pd.Timestamp(result.context["lastHistoryDate"]).date() == pd.Timestamp(
        result.context["lastMessageDate"]
    ).date()
    assert pd.Timestamp(result.context["lastHistoryDate"]).date() == pd.Timestamp(
        result.context["coreBacktestSignalTime"]
    ).date()
    risk_contribution_min = result.context["lastRiskContributionMin"]
    risk_contribution_max = result.context["lastRiskContributionMax"]
    assert risk_contribution_min == pytest.approx(
        risk_contribution_max,
        rel=1e-8,
        abs=1e-12,
    )
    assert result.context["lastInverseVolatilityDistance"] > 1e-6
    assert not result.trade_details.empty
    assert set(result.trade_details["direction"]) == {1, 3}
    assert np.isfinite(result.daily_portfolios["totalEquity"]).all()
    assert result.engine_stat.loc[0, "status"] == "END"
    assert_engine_dropped(ddb_session, engine_name)


@pytest.mark.parametrize(
    ("utils", "callbacks", "message"),
    [
        (
            {"declaredName": "def actualName() { return 1 }"},
            TRACE_CALLBACKS,
            "键名必须与函数名一致",
        ),
        (
            {},
            {
                **TRACE_CALLBACKS,
                "onBar": (
                    TRACE_CALLBACKS["onBar"]
                    + "\ndef misplacedUtility() { return 1 }"
                ),
            },
            "工具函数请放入 utils",
        ),
    ],
)
def test_backtest_validates_independent_utility_definitions(
    ddb_session: Any,
    utils: dict[str, str],
    callbacks: dict[str, str],
    message: str,
) -> None:
    """工具函数必须逐个放入 utils，不能附加在回调定义中。"""
    with pytest.raises(ValueError, match=message):
        run_backtest(
            deepcopy(BASE_QUERY),
            callbacks,
            utils=utils,
            session=ddb_session,
        )


def test_filters_only_pass_selected_previous_rows(ddb_session: Any) -> None:
    """filters 应先标记消息，用户回调只收到上一日通过筛选的完整行。"""
    query = deepcopy(BASE_QUERY)
    query["filters"] = ["eligible"]
    engine_name = f"project_filter_{uuid4().hex}"
    result = run_backtest(
        query,
        TRACE_CALLBACKS,
        name=engine_name,
        config={"matchingMode": 2},
        session=ddb_session,
    )

    assert result.message_rows == 8
    assert result.context["signalTimes"].tolist() == [
        np.datetime64("2025-01-02T15:00:00.000"),
        np.datetime64("2025-01-06T15:00:00.000"),
        np.datetime64("2025-01-07T15:00:00.000"),
        np.datetime64("2025-01-08T15:00:00.000"),
    ]
    assert result.context["executionTimes"].tolist() == [
        np.datetime64("2025-01-03T15:00:00.000"),
        np.datetime64("2025-01-07T15:00:00.000"),
        np.datetime64("2025-01-08T15:00:00.000"),
        np.datetime64("2025-01-09T15:00:00.000"),
    ]
    assert result.trade_details.empty
    assert_engine_dropped(ddb_session, engine_name)


def test_callback_failure_drops_engine(ddb_session: Any) -> None:
    """用户回调抛错时 run_backtest 应继续执行 finally 并销毁引擎。"""
    query = deepcopy(BASE_QUERY)
    query["end_date"] = "2025-01-06"
    engine_name = f"project_failure_{uuid4().hex}"
    callbacks = {
        "onBar": """
            def failingOnBar(mutable context, msg, indicator) {
                throw "project callback failure"
            }
        """
    }

    with pytest.raises(RuntimeError, match="project callback failure"):
        run_backtest(
            query,
            callbacks,
            name=engine_name,
            config={"matchingMode": 2},
            session=ddb_session,
        )
    assert_engine_dropped(ddb_session, engine_name)
