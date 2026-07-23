"""直接执行纯 DolphinDB 策略，验证 Backtest 插件行为。"""

from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest


pytestmark = [pytest.mark.dolphindb, pytest.mark.backtest]

SCRIPT_DIR = Path(__file__).with_name("dolphindb")


def run_strategy(
    session: Any,
    script_name: str,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """运行一个独立 DOS 策略，读取结果后始终销毁测试引擎。"""
    session.upload({"testEngineName": f"test_{uuid4().hex}"})
    try:
        session.run((SCRIPT_DIR / script_name).read_text(encoding="utf-8"))
        context = session.run("Backtest::getContextDict(testEngine)")
        trades = session.run("Backtest::getTradeDetails(testEngine)")
        portfolios = session.run("Backtest::getDailyTotalPortfolios(testEngine)")
        stat = session.run("Backtest::getBacktestEngineStat(testEngine)")
        context.pop("engine", None)
        return context, trades, portfolios, stat
    finally:
        session.run("Backtest::dropBacktestEngine(testEngine)")


def test_daily_lifecycle_and_last_bar(ddb_session: Any) -> None:
    """日频生命周期次数、参数类型和尾部 Bar 行为应与 README 一致。"""
    context, trades, portfolios, stat = run_strategy(
        ddb_session,
        "lifecycle.dos",
    )

    assert context["initializeCount"] == 1
    assert context["beforeTradingCount"] == 4
    assert context["onBarCount"] == 3
    assert context["onSnapshotCount"] == 0
    assert context["onOrderCount"] == 0
    assert context["onTradeCount"] == 0
    assert context["afterTradingCount"] == 4
    assert context["finalizeCount"] == 1
    assert context["msgType"] == "IN-MEMORY TABLE"
    assert context["indicatorType"] == "VOID"
    assert context["firstSymbol"] == "000001.XSHE"
    assert context["firstScore"] == pytest.approx(0.1)
    assert context["barRowCounts"].tolist() == [1, 1, 1]
    assert context["barTimes"].tolist() == [
        np.datetime64("2025-01-02T15:00:00.000"),
        np.datetime64("2025-01-03T15:00:00.000"),
        np.datetime64("2025-01-06T15:00:00.000"),
    ]
    assert context["trace"].tolist() == [
        "initialize",
        "beforeTrading",
        "onBar",
        "afterTrading",
        "beforeTrading",
        "onBar",
        "afterTrading",
        "beforeTrading",
        "onBar",
        "afterTrading",
        "beforeTrading",
        "afterTrading",
        "finalize",
    ]
    assert trades.empty
    assert len(portfolios) == 4
    assert stat.loc[0, "status"] == "END"
    assert stat.loc[0, "lastErrMsg"] == ""


def test_readme_example_matches_documented_results(ddb_session: Any) -> None:
    """README 主示例的输入、回调次数、成交和权益必须原样可复现。"""
    context, trades, portfolios, stat = run_strategy(
        ddb_session,
        "readme_example.dos",
    )

    assert context["initializeCount"] == 1
    assert context["beforeTradingCount"] == 7
    assert context["onBarCount"] == 6
    assert context["onSnapshotCount"] == 0
    assert context["onOrderCount"] == 2
    assert context["onTradeCount"] == 1
    assert context["afterTradingCount"] == 7
    assert context["finalizeCount"] == 1
    assert context["msgType"] == "IN-MEMORY TABLE"
    assert context["indicatorType"] == "VOID"
    assert context["firstSymbol"] == "000001.XSHE"
    assert context["firstTradeTime"] == np.datetime64(
        "2025-01-02T15:00:00.000"
    )
    assert context["firstOpen"] == pytest.approx(11.73)
    assert context["firstClose"] == pytest.approx(11.43)
    assert context["firstPositionTarget"] == 1
    assert context["firstFactorScore"] == pytest.approx(0.82)
    assert context["firstMarketRegime"] == "bull"
    assert context["firstSignal"].tolist() == pytest.approx([0.1, 0.2])
    assert context["signalType"] == "FAST DOUBLE[] VECTOR"

    filled = trades.loc[trades["orderStatus"].eq(1)].iloc[0]
    assert filled["direction"] == 1
    assert filled["orderPrice"] == pytest.approx(11.43)
    assert filled["tradePrice"] == pytest.approx(11.73)
    assert filled["tradeQty"] == 100
    final = portfolios.iloc[-1]
    assert final["cash"] == pytest.approx(1_998_826.6481)
    assert final["totalMarketValue"] == pytest.approx(1_130)
    assert final["totalFee"] == pytest.approx(0.3519)
    assert final["totalEquity"] == pytest.approx(1_999_956.6481)
    assert stat.loc[0, "status"] == "END"


def test_open_matching_callbacks_fees_and_equity(ddb_session: Any) -> None:
    """开盘撮合的成交价、回调次数、费用和权益应逐项可核对。"""
    context, trades, portfolios, stat = run_strategy(
        ddb_session,
        "matching.dos",
    )

    filled = trades.loc[trades["orderStatus"].eq(1)].reset_index(drop=True)
    assert context["onBarCount"] == 3
    assert context["onOrderCount"] == 4
    assert context["onTradeCount"] == 2
    assert context["orderType"] == "ANY VECTOR"
    assert context["tradeType"] == "ANY VECTOR"
    assert context["portfolioType"] == "IN-MEMORY TABLE"
    assert context["initialTotalEquity"] == pytest.approx(100000)
    assert context["trace"].tolist() == [
        "initialize",
        "beforeTrading",
        "onBar",
        "onOrder",
        "onOrder",
        "onTrade",
        "afterTrading",
        "beforeTrading",
        "onBar",
        "onOrder",
        "onOrder",
        "onTrade",
        "afterTrading",
        "beforeTrading",
        "onBar",
        "afterTrading",
        "beforeTrading",
        "afterTrading",
        "finalize",
    ]
    assert filled["direction"].tolist() == [1, 3]
    assert filled["tradeQty"].tolist() == [100, 100]
    assert filled["tradePrice"].tolist() == pytest.approx([10.0, 12.0])
    assert filled["tradeTime"].tolist() == [
        pd.Timestamp("2025-01-02 15:00:00"),
        pd.Timestamp("2025-01-03 15:00:00"),
    ]

    expected_fee = 1000 * 0.001 + 1200 * (0.001 + 0.002)
    expected_equity = 100000 + (1200 - 1000) - expected_fee
    final = portfolios.iloc[-1]
    assert final["totalFee"] == pytest.approx(expected_fee)
    assert final["cash"] == pytest.approx(expected_equity)
    assert final["totalMarketValue"] == pytest.approx(0)
    assert final["totalEquity"] == pytest.approx(expected_equity)
    assert stat.loc[0, "status"] == "END"


def test_same_timestamp_symbols_are_one_table(ddb_session: Any) -> None:
    """同一时间戳的股票应组成完整表，扩展 INT 和 DOUBLE 列应保持值。"""
    context, trades, portfolios, stat = run_strategy(
        ddb_session,
        "batch_message.dos",
    )

    assert context["beforeTradingCount"] == 3
    assert context["onBarCount"] == 2
    assert context["afterTradingCount"] == 3
    assert context["rowCounts"].tolist() == [2, 2]
    assert context["barTimes"].tolist() == [
        np.datetime64("2025-01-02T15:00:00.000"),
        np.datetime64("2025-01-03T15:00:00.000"),
    ]
    assert context["firstSymbols"].tolist() == [
        "000001.XSHE",
        "600000.XSHG",
    ]
    assert context["firstSelections"].tolist() == [1, 0]
    assert context["firstScores"].tolist() == pytest.approx([0.8, 0.2])
    assert context["scoreReference"].tolist() == pytest.approx([0.6, 0.4])
    assert trades.empty
    assert len(portfolios) == 3
    assert stat.loc[0, "status"] == "END"


def test_bool_extension_is_rejected(ddb_session: Any) -> None:
    """插件应拒绝 BOOL 扩展列，项目必须先把 BOOL 派生因子转为 INT。"""
    ddb_session.upload({"testEngineName": f"test_{uuid4().hex}"})
    try:
        with pytest.raises(RuntimeError, match="Not support BOOL in extend columns"):
            ddb_session.run(
                (SCRIPT_DIR / "bool_extension.dos").read_text(encoding="utf-8")
            )
    finally:
        ddb_session.run("Backtest::dropBacktestEngine(testEngine)")
