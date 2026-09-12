"""Real plugin boundary tests with in-memory quotes and temporary engines only."""

import os
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest

from runtime.database import create_session
from runtime.database.compile.backtest.functions.build_backtest_message import BUILD_BACKTEST_MESSAGE
from runtime.database.compile.backtest.functions.run_backtest import RUN_BACKTEST
from runtime.database.compile.backtest.functions.return_summary import STANDARDIZE_RETURN_SUMMARY
from runtime.database.compile.script import collect_functions


@pytest.fixture(scope="module")
def dolphin():
    if os.getenv("ARENA_TEST_DOLPHINDB") != "1":
        pytest.skip("requires explicit opt-in to the configured DolphinDB server")
    session = create_session(max_time=300)
    try:
        session.run('''
            if (!("MatchingEngineSimulator" in (exec plugin from getLoadedPlugins()))) loadPlugin("MatchingEngineSimulator")
            if (!("Backtest" in (exec plugin from getLoadedPlugins()))) loadPlugin("Backtest")
        ''')
        for function in collect_functions([BUILD_BACKTEST_MESSAGE, RUN_BACKTEST, STANDARDIZE_RETURN_SUMMARY]):
            session.run(function.definition)
        session.run('''
            def auditInit(mutable ctx) {
                ctx["events"]=array(STRING,0)
                ctx["statuses"]=array(INT,0)
                ctx["fills"]=array(LONG,0)
                ctx["days"]=0
                ctx["closing"]=objByName("auditClosing")
                ctx["quantity"]=objByName("auditQuantity")
            }
            def auditBefore(mutable ctx) {
                ctx["days"]=ctx["days"]+1
                ctx["events"]=ctx["events"] join ["before"]
            }
            def auditInitial(mutable ctx) {
                auditInit(ctx)
                Backtest::setPosition(ctx.engine,"000001.XSHE",100l,10.0)
            }
            def auditBar(mutable ctx,msg,indicator) { throw "unexpected onBar" }
            def auditSnapshot(mutable ctx,msg,indicator) {
                ctx["events"]=ctx["events"] join [string(msg.timestamp[0])+"/"+string(msg.rows())]
                if (ctx["quantity"]>0 && ctx["days"]==1 &&
                    ((ctx["closing"] && time(msg.timestamp[0])==15:00:00.000) ||
                    (!ctx["closing"] && time(msg.timestamp[0])==09:30:00.000))) {
                    Backtest::submitOrder(ctx.engine,(msg.symbol[0],msg.timestamp[0],5,10.0,ctx["quantity"],1),"audit")
                }
            }
            def auditOrder(mutable ctx,events) {
                for (event in events) ctx["statuses"]=ctx["statuses"] join [int(event.status)]
            }
            def auditTrade(mutable ctx,events) {
                for (event in events) ctx["fills"]=ctx["fills"] join [long(event.tradeQty)]
            }
            def auditAfter(mutable ctx) { ctx["events"]=ctx["events"] join ["after"] }
            def auditFinal(mutable ctx) { ctx["events"]=ctx["events"] join ["final"] }
        ''')
        yield session
    finally:
        session.close()


def run_case(dolphin, days, *, closing=False, latency=0, quantity=100, initial=False):
    name = "arena_feedback91_" + uuid4().hex
    dates = pd.bdate_range("2025-01-02", periods=days)
    daily = pd.DataFrame({
        "time": np.repeat(dates.to_numpy(), 2),
        "code": ["000001.XSHE", "600000.XSHG"] * days,
        "open": 10., "close": 9., "high": 11., "low": 8.,
        "up_limit": 11., "down_limit": 8., "pre_close": 10.,
    })
    dolphin.upload({"auditDaily": daily, "auditName": name, "auditClosing": closing,
                    "auditLatency": np.int32(latency), "auditQuantity": np.int64(quantity),
                    "auditCash": 100000. if initial else 100000000000., "auditCommission": 0.01 if initial else 0.0})
    initialize_callback = "auditInitial" if initial else "auditInit"
    dolphin.run(f'''
        auditMessage=build_backtest_message(auditDaily,NULL)
        auditConfig=dict(STRING,ANY)
        auditConfig["cash"]=auditCash
        auditConfig["commission"]=auditCommission
        auditConfig["tax"]=0.0
        auditConfig["enableMinimumPerTransactionFee"]=false
        auditConfig["startDate"]=min(date(auditDaily.time))
        auditConfig["endDate"]=max(date(auditDaily.time))+1
        auditConfig["strategyGroup"]="stock"
        auditConfig["msgAsTable"]=true
        auditConfig["latency"]=auditLatency
        auditEngine=run_backtest(auditName,auditConfig,auditMessage,{initialize_callback},auditBefore,
            auditBar,auditSnapshot,auditOrder,auditTrade,auditAfter,auditFinal)
    ''')
    try:
        result = {key: dolphin.run(f'Backtest::getContextDict(auditEngine)["{key}"]')
                  for key in ["events", "statuses", "fills"]}
        result["portfolios"] = dolphin.run("Backtest::getDailyTotalPortfolios(auditEngine)")
        result["trades"] = dolphin.run("Backtest::getTradeDetails(auditEngine)")
        result["message_symbols"] = dolphin.run("string(auditMessage.symbol)")
        result["dates"] = dates
        return result
    finally:
        dolphin.run("Backtest::dropBacktestEngine(auditEngine)")


@pytest.mark.parametrize("days", [1, 2, 3])
def test_end_flush_delivers_every_snapshot_once_and_finalizes_once(dolphin, days):
    actual = run_case(dolphin, days)
    expected = []
    for date in actual["dates"]:
        prefix = date.strftime("%Y.%m.%d")
        expected.extend(["before", prefix+"T09:30:00.000/2", prefix+"T15:00:00.000/2", "after"])
    expected.append("final")
    assert list(actual["events"]) == expected
    assert len(actual["portfolios"]) == days
    assert actual["fills"].sum() == 100
    assert len(actual["message_symbols"]) == 4 * days
    assert "END" not in actual["message_symbols"]


def test_end_marker_is_not_an_extra_liquidity_event(dolphin):
    actual = run_case(dolphin, 1, latency=1, quantity=1_500_000_000)
    assert actual["fills"].sum() == 1_000_000_000
    assert actual["trades"].loc[actual["trades"].orderStatus == -3, "tradeQty"].sum() == 500_000_000
    # This plugin records expiry in getTradeDetails, not an onOrder callback.
    assert -3 not in actual["statuses"]


@pytest.mark.parametrize("days", [1, 2])
def test_close_callback_is_delivered_but_new_close_orders_are_rejected(dolphin, days):
    actual = run_case(dolphin, days, closing=True)
    assert -1 in actual["statuses"]
    assert not len(actual["fills"])
    assert actual["trades"].orderStatus.tolist() == [4, -1]


def test_pending_limit_fills_at_order_price_not_new_opposite_quote(dolphin):
    actual = run_case(dolphin, 1, latency=1)
    filled = actual["trades"].loc[actual["trades"].orderStatus == 1]
    assert filled.tradePrice.tolist() == [10.]
    assert filled.tradeTime.iloc[0].hour == 15


def test_two_days_have_undefined_volatility_after_excluding_initial_return(dolphin):
    actual = dolphin.run('''
        summary=table(0.0 as annualReturn,0.0 as annualVolatility,0.0 as sharpeRatio)
        daily=table(2025.01.02 2025.01.03 as tradeDate,1.01 1.0302 as netValue)
        standardize_return_summary(summary,daily,252,0.0)
    ''')
    assert actual.annualVolatility.isna().all()
    assert actual.sharpeRatio.isna().all()


def test_qfq_basis_is_latest_by_date_not_physical_row_order(dolphin):
    daily = pd.DataFrame({
        "time": pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-02", "2025-01-03"]),
        "code": ["000001.XSHE"] * 2 + ["600000.XSHG"] * 2,
        "open": 10., "close": 9., "high": 11., "low": 8.,
        "up_limit": 11., "down_limit": 8., "pre_close": 10.,
        "adj_factor": [1., 2., 2., 4.],
    })
    dolphin.upload({"auditDaily": daily})
    normal = dolphin.run('build_backtest_message(auditDaily,"qfq")')
    dolphin.upload({"auditDaily": daily.iloc[[3, 2, 1, 0]].reset_index(drop=True)})
    before = dolphin.run("auditDaily")
    permuted = dolphin.run('build_backtest_message(auditDaily,"qfq")')
    pd.testing.assert_frame_equal(normal, permuted)
    pd.testing.assert_frame_equal(dolphin.run("auditDaily"), before)
    assert normal.lastPrice.tolist() == [5., 5., 4.5, 4.5, 10., 10., 9., 9.]


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="Backtest 2.00.16.32 setPosition deducts initial commission without totalFee/PnL; remove after upstream fix")
def test_plugin_accounts_for_set_position_fee_in_total_fee_and_pnl(dolphin):
    actual = run_case(dolphin, 3, quantity=0, initial=True)["portfolios"]
    # No trades: initial position value 1,000 plus commission 10 is deducted once.
    np.testing.assert_allclose(actual.cash, 98_990.)
    np.testing.assert_allclose(actual.totalFee, 10.)
    np.testing.assert_allclose(actual.totalEquity, 100_000. + actual.totalPnl)
