"""Real-engine tests: temporary tables/engines only, never publish modules or data."""

import os
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest

from runtime.database import create_session
from runtime.database.compile.backtest.functions import BACKTEST_FUNCTIONS
from runtime.database.compile.backtest.functions.snapshot import (
    GET_MINUTE_HISTORY,
    READ_STOCK_SNAPSHOTS,
    RUN_SNAPSHOT_BACKTEST,
)
from runtime.database.compile.script import collect_functions
from runtime.apps.query.api import build_query_table
from runtime.apps.query.schema import FactorQuery
from runtime.apps.backtest import api as backtest_api
from runtime.apps.backtest.schema import BacktestParameters


@pytest.fixture(scope="module")
def dolphin():
    if os.getenv("ARENA_TEST_DOLPHINDB") != "1":
        pytest.skip("requires explicit opt-in to configured DolphinDB")
    session = create_session(redirect_output=True, max_time=900)
    try:
        session.run('''
            if (!("MatchingEngineSimulator" in (exec plugin from getLoadedPlugins()))) loadPlugin("MatchingEngineSimulator")
            if (!("Backtest" in (exec plugin from getLoadedPlugins()))) loadPlugin("Backtest")
        ''')
        for function in collect_functions(BACKTEST_FUNCTIONS):
            session.run(function.definition)
        session.run('''
            def snapBefore(mutable ctx) {}
            def snapBar(mutable ctx,msg,indicator) { throw "unexpected onBar" }
            def snapOrder(mutable ctx,orders) {}
            def snapAfter(mutable ctx) {}
            def snapFinal(mutable ctx) {}
        ''')
        yield session
    finally:
        session.close()


def upload_quotes(session, times, *, symbols=("600020.SH",), prices=None):
    stamps = pd.DatetimeIndex(times)
    size = len(stamps)
    codes = [symbols[i % len(symbols)] for i in range(size)]
    frame = pd.DataFrame({
        "Market": [s[-2:] for s in codes], "SecurityID": [s[:6] for s in codes],
        "TradeDate": stamps.normalize(), "TradeTime": stamps,
        "LastPrice": np.asarray(prices if prices is not None else [10.] * size, dtype=float),
        "TotalVolume": np.arange(size, dtype=np.int64) * 100,
        "TotalAmount": np.arange(size, dtype=float) * 1000,
    })
    for level in range(1, 6):
        for side, sign in [("Bid", -1), ("Ask", 1)]:
            frame[f"{side}Price{level}"] = 10. + sign * level / 100
            frame[f"{side}Volume{level}"] = np.int64(100 if level == 1 else 0)
    session.upload({"snapRaw": frame})
    session.run('''
        replaceColumn!(snapRaw,`TradeDate,date(snapRaw.TradeDate))
        replaceColumn!(snapRaw,`TradeTime,time(snapRaw.TradeTime))
        replaceColumn!(snapRaw,`Market,symbol(snapRaw.Market))
        replaceColumn!(snapRaw,`SecurityID,symbol(snapRaw.SecurityID))
        snapReference=select distinct timestamp(TradeDate) as time,
            symbol(string(SecurityID)+iif(Market=="SH",".XSHG",".XSHE")) as code,
            10.0 as pre_close,11.0 as up_limit,9.0 as down_limit from snapRaw
    ''')
    return frame


def test_message_mapping_five_levels_and_one_sided_book(dolphin):
    upload_quotes(dolphin, ["2026-06-01 09:30:01"] * 2, symbols=("600020.SH", "000001.SZ"))
    dolphin.run('''
        update snapRaw set AskPrice1=0.0,AskVolume1=0l where Market="SZ"
        update snapRaw set BidVolume2=23l where Market="SH"
    ''')
    result = dolphin.run("build_stock_snapshot_message(snapRaw,snapReference)")
    assert result.symbol.tolist() == ["600020.XSHG", "000001.XSHE"]
    assert result.timestamp.tolist() == [pd.Timestamp("2026-06-01 09:30:01")] * 2
    np.testing.assert_allclose(result.bidPrice.iloc[0], [9.99, 9.98, 0, 0, 0])
    np.testing.assert_allclose(result.bidQty.iloc[0], [100, 23, 0, 0, 0])
    np.testing.assert_array_equal(result.offerQty.iloc[1], np.zeros(5))
    assert not result.totalBidQty.any() and not result.totalOfferQty.any()
    dolphin.run("update snapReference set up_limit=double(NULL) where code=`000001.XSHE")
    with pytest.raises(RuntimeError, match=r"000001.XSHE.*2026.06.01.*up_limit"):
        dolphin.run("build_stock_snapshot_message(snapRaw,snapReference)")


def test_invalid_last_price_and_empty_input(dolphin):
    upload_quotes(dolphin, ["2026-06-01 09:30:01"] * 3, prices=[0, np.nan, 10])
    assert len(dolphin.run("build_stock_snapshot_message(snapRaw,snapReference)")) == 1
    assert dolphin.run("build_stock_snapshot_message(snapRaw[0:0],snapReference)").empty
    assert dolphin.run("build_minute_bars(snapRaw[0:0])").empty


def test_minute_ohlc_cumulative_differences_lunch_and_boundaries(dolphin):
    times = ["2026-06-01 " + t for t in ["09:29:59", "09:30:00", "09:30:20", "09:31:00", "11:30:00", "13:00:00", "13:00:20", "13:01:00", "15:00:00"]]
    frame = upload_quotes(dolphin, times, prices=[9, 10, 12, 11, 13, 14, 15, 14, 16])
    actual = dolphin.run("build_minute_bars(snapRaw)")
    # Independent pandas reference, only the test (not production) materializes rows.
    frame["volume"] = frame.TotalVolume.diff().fillna(0).astype("int64")
    frame["amount"] = frame.TotalAmount.diff().fillna(0)
    frame = frame.iloc[1:].copy()
    frame["end"] = pd.DatetimeIndex(frame.TradeTime).ceil("min")
    opening = frame.TradeTime.dt.strftime("%H:%M").isin(["09:30", "13:00"]) & (frame.TradeTime.dt.second == 0)
    frame["end"] = frame["end"].where(~opening, frame["end"] + pd.Timedelta(minutes=1))
    expected = frame.groupby("end").agg(open=("LastPrice", "first"), high=("LastPrice", "max"), low=("LastPrice", "min"), close=("LastPrice", "last"), volume=("volume", "sum"), amount=("amount", "sum"))
    pd.testing.assert_frame_equal(actual.set_index("time")[list(expected.columns)], expected, check_names=False, check_freq=False)
    assert actual.time.dt.strftime("%H:%M").tolist() == ["09:31", "11:30", "13:01", "15:00"]


def test_minute_history_cutoff_count_and_future_independence(dolphin):
    upload_quotes(dolphin, ["2026-06-01 " + t for t in ["09:29:59", "09:30:01", "09:31:00", "09:31:30", "09:32:00", "09:33:00"]])
    dolphin.run('''
        coreBacktestSnapshotState=dict(STRING,ANY)
        coreBacktestSnapshotState["enabled"]=true
        coreBacktestSnapshotState["source"]=snapRaw
        coreBacktestSnapshotState["codes"]=symbol(["600020.XSHG"])
        coreBacktestSnapshotState["historyDates"]=date([2026.06.01])
        coreBacktestSnapshotState["history"]=dict(STRING,ANY)
        snapMsg=table(2026.06.01T09:32:30.000 as timestamp)
    ''')
    before = dolphin.run('getMinuteHistory(NULL,snapMsg,["600020.XSHG"],1)')
    assert before.time.tolist() == [pd.Timestamp("2026-06-01 09:32")]
    dolphin.run('''
        update snapRaw set LastPrice=900.0,TotalAmount=0.0 where TradeTime>09:32:30.000
        coreBacktestSnapshotState["history"]=dict(STRING,ANY)
    ''')
    pd.testing.assert_frame_equal(before, dolphin.run('getMinuteHistory(NULL,snapMsg,["600020.XSHG"],1)'))
    assert len(dolphin.run('getMinuteHistory(NULL,snapMsg,["600020.XSHG"],100)')) == 2


def test_invalid_price_does_not_erase_cumulative_volume(dolphin):
    upload_quotes(dolphin, ["2026-06-01 " + t for t in [
        "09:29:59", "09:30:00", "09:30:20", "09:31:00",
    ]], prices=[9, 10, np.nan, 11])
    bars = dolphin.run("build_minute_bars(snapRaw)")
    assert bars[["open", "high", "low", "close"]].iloc[0].tolist() == [10, 11, 10, 11]
    assert bars.volume.tolist() == [300]
    assert bars.amount.tolist() == [3000.0]


def run_replay(session, chunk_minutes, *, latency=0):
    session.upload({"snapName": "arena_snapshot_test_" + uuid4().hex, "snapChunk": np.int32(chunk_minutes), "snapLatency": np.int32(latency)})
    session.run('''
        coreBacktestSnapshotState=dict(STRING,ANY)
        def snapInit(mutable ctx) { ctx["times"]=array(TIMESTAMP,0); ctx["bars"]=0 }
        def snapBefore(mutable ctx) {}
        def snapBar(mutable ctx,msg,indicator) { throw "unexpected onBar" }
        def snapCallback(mutable ctx,msg,indicator) {
            ctx["times"].append!(msg.timestamp[0])
            history=getMinuteHistory(ctx,msg,["600020.XSHG"],3)
            ctx["bars"]+=history.rows()
            if (size(ctx["times"])==2) order_target(ctx,msg,"600020.XSHG",300)
        }
        def snapOrder(mutable ctx,orders) {}
        def snapTrade(mutable ctx,trades) {}
        def snapAfter(mutable ctx) {}
        def snapFinal(mutable ctx) {}
        snapDays=sort(distinct(snapRaw.TradeDate))
        snapCodes=symbol(["600020.XSHG","000001.XSHE"])
        snapConfig=dict(STRING,ANY)
        snapConfig["cash"]=100000.0
        snapConfig["commission"]=0.0
        snapConfig["tax"]=0.0
        snapConfig["enableMinimumPerTransactionFee"]=false
        snapConfig["startDate"]=min(snapDays)
        snapConfig["endDate"]=max(snapDays)
        snapConfig["strategyGroup"]="stock"
        snapConfig["msgAsTable"]=true
        snapConfig["latency"]=snapLatency
        snapEmpty=build_stock_snapshot_message(snapRaw[0:0],snapReference)
        snapEngine=run_snapshot_backtest(snapName,snapConfig,snapRaw,snapReference,snapCodes,snapDays,snapEmpty,
            snapInit,snapBefore,snapBar,snapCallback,snapOrder,snapTrade,snapAfter,snapFinal,snapChunk)
    ''')
    try:
        return {"trades": session.run("Backtest::getTradeDetails(snapEngine)"),
                "daily": session.run("Backtest::getDailyTotalPortfolios(snapEngine)"),
                "times": session.run('Backtest::getContextDict(snapEngine)["times"]')}
    finally:
        session.run("Backtest::dropBacktestEngine(snapEngine)")


def test_chunk_replay_and_repeated_session_match_whole_replay(dolphin):
    upload_quotes(dolphin, [f"2026-06-0{day} {t}" for day in (1, 2, 3)
                           for t in ["09:30:01", "09:30:03", "09:31:00", "09:35:00", "15:00:00"]],
                  symbols=("600020.SH", "000001.SZ"))
    # Cumulative volumes reset by date in real data. This synthetic fixture is also monotone within each date.
    whole = run_replay(dolphin, 1440)
    for chunk in [1, 5, 1]:
        actual = run_replay(dolphin, chunk)
        pd.testing.assert_frame_equal(whole["trades"], actual["trades"])
        pd.testing.assert_frame_equal(whole["daily"], actual["daily"])
        np.testing.assert_array_equal(whole["times"], actual["times"])
    assert len(whole["times"]) == 15
    assert len(whole["daily"]) == 3
    fills = whole["trades"].loc[whole["trades"].orderStatus.isin([0, 1])]
    # The engine waits for this symbol's next quote; two remaining books supply
    # 100 shares each. END must not supply the missing 100 shares.
    assert fills.tradeQty.sum() == 200
    assert fills.tradeQty.max() <= 100
    expired = whole["trades"].loc[whole["trades"].orderStatus == -3]
    assert expired.tradeQty.sum() == 100


def test_one_sided_book_rejects_buy_and_latency_does_not_create_liquidity(dolphin):
    times = ["2026-06-01 " + t for t in ["09:30:01", "09:30:03", "09:31:00", "09:35:00", "15:00:00"]]
    upload_quotes(dolphin, times, symbols=("600020.SH", "000001.SZ"))
    delayed = run_replay(dolphin, 5, latency=100000)
    fills = delayed["trades"].loc[delayed["trades"].orderStatus.isin([0, 1])]
    assert fills.tradeQty.sum() == 100
    assert fills.tradeTime.min() >= pd.Timestamp("2026-06-01 09:31:43")
    dolphin.run("update snapRaw set AskVolume1=0l")
    with pytest.raises(RuntimeError, match="卖一没有可成交数量"):
        run_replay(dolphin, 5)


def test_missing_trading_day_is_not_silently_skipped(dolphin):
    upload_quotes(dolphin, ["2026-06-01 09:30:01", "2026-06-01 15:00:00"])
    run_replay(dolphin, 5)
    dolphin.upload({"snapName": "arena_missing_day_" + uuid4().hex})
    with pytest.raises(RuntimeError, match="缺少交易日行情.*2026.06.02"):
        dolphin.run('''
            snapConfig["endDate"]=2026.06.02
            run_snapshot_backtest(snapName,snapConfig,snapRaw,snapReference,snapCodes,2026.06.01 2026.06.02,snapEmpty,
                snapInit,snapBefore,snapBar,snapCallback,snapOrder,snapTrade,snapAfter,snapFinal)
        ''')


@pytest.mark.parametrize("coverage_case", ["absent", "invalid", "other_stock", "empty"])
def test_missing_days_are_reported_together_before_creating_engine(dolphin, coverage_case):
    upload_quotes(dolphin, ["2026-06-01 09:30:01", "2026-06-01 15:00:00"])
    if coverage_case in {"invalid", "other_stock"}:
        dolphin.run('''
            invalidDay=select * from snapRaw
            update invalidDay set TradeDate=2026.06.02
        ''')
        if coverage_case == "invalid":
            dolphin.run('update invalidDay set LastPrice=0.0')
        else:
            dolphin.run('update invalidDay set Market=`SZ,SecurityID=`000001')
        dolphin.run('snapRaw.append!(invalidDay)')
    elif coverage_case == "empty":
        dolphin.run('snapRaw=snapRaw[0:0]')
    dolphin.run('''
        coreBacktestSnapshotState=dict(STRING,ANY)
        def rejectTestEngine(name,mutable config,initialize_callback,before_trading_callback,on_bar_callback,on_snapshot_callback,on_order_callback,on_trade_callback,after_trading_callback,finalize_callback) {
            throw "engine creation must not be reached"
        }
        def preflightNoop(mutable ctx) {}
        def preflightEvent(mutable ctx,event) {}
        def preflightSnapshot(mutable ctx,msg,indicator) {}
        preflightConfig=dict(STRING,ANY)
        preflightEmpty=build_stock_snapshot_message(snapRaw[0:0],snapReference)
    ''')
    # A separate session-local entry proves the factory is never called, even
    # if the plugin postpones initialize until its first quotation arrives.
    dolphin.run(RUN_SNAPSHOT_BACKTEST.definition.replace(
        "def run_snapshot_backtest(", "def test_snapshot_preflight("
    ).replace("engine = create_backtest_engine(", "engine = rejectTestEngine("))
    with pytest.raises(RuntimeError) as caught:
        dolphin.run('''
            test_snapshot_preflight("preflight",preflightConfig,snapRaw,snapReference,symbol(["600020.XSHG"]),
                2026.06.01 2026.06.02 2026.06.03,preflightEmpty,
                preflightNoop,preflightNoop,preflightSnapshot,preflightSnapshot,
                preflightEvent,preflightEvent,preflightNoop,preflightNoop)
        ''')
    message = str(caught.value)
    assert "engine creation must not be reached" not in message
    assert "2026.06.02" in message and "2026.06.03" in message
    assert "缺少交易日行情" in message
    if coverage_case == "invalid":
        assert "缺少有效交易日行情" in message
    if coverage_case == "empty":
        assert "2026.06.01" in message
    assert not dolphin.run('coreBacktestSnapshotState["enabled"]')


def test_minute_history_reuses_each_symbol_and_batches_equal_read_boundaries(dolphin):
    times = ["2026-06-01 " + t for t in [
        "09:29:59", "09:30:00", "09:31:00", "09:32:00", "09:33:00", "09:34:00",
    ] for _ in range(2)]
    upload_quotes(dolphin, times, symbols=("600020.SH", "000001.SZ"),
                  prices=[10 + (i % 2) * 10 + i / 10 for i in range(len(times))])
    dolphin.run('''
        coreBacktestSnapshotState=dict(STRING,ANY)
        coreBacktestSnapshotState["enabled"]=true
        coreBacktestSnapshotState["source"]=snapRaw
        coreBacktestSnapshotState["codes"]=symbol(["600020.XSHG","000001.XSHE"])
        coreBacktestSnapshotState["historyDates"]=date([2026.06.01])
        coreBacktestSnapshotState["history"]=dict(STRING,ANY)
        coreBacktestSnapshotState["readAudit"]=table(1:0,`codes`begin`end,[STRING,TIME,TIME])
    ''')
    dolphin.run(READ_STOCK_SNAPSHOTS.definition.replace(
        "def read_stock_snapshots(", "def audited_read_stock_snapshots("
    ).replace("shCodes =", '''
        if (history) {
            state=objByName("coreBacktestSnapshotState")
            audit=state["readAudit"]
            audit.append!(table(concat(string(codes),",") as codes,begin_time as begin,end_time as end))
            state["readAudit"]=audit
        }
        shCodes =''', 1))
    dolphin.run(GET_MINUTE_HISTORY.definition.replace(
        "def getMinuteHistory(", "def audited_minute_history("
    ).replace("read_stock_snapshots(", "audited_read_stock_snapshots("))
    for instant, codes, count in [
        ("09:31:00", ["600020.XSHG"], 1),
        ("09:31:00", ["000001.XSHE"], 1),
        ("09:32:00", ["600020.XSHG", "000001.XSHE"], 2),
        ("09:33:00", ["600020.XSHG"], 2),
        ("09:34:00", ["600020.XSHG", "000001.XSHE"], 3),
        # Reading an older time must not leak later cached bars; the other
        # security's cache must survive this rollback and the smaller request.
        ("09:32:00", ["600020.XSHG"], 1),
        ("09:34:00", ["000001.XSHE"], 4),
    ]:
        dolphin.upload({"historyCodesForTest": codes, "historyCountForTest": count})
        dolphin.run(f'snapMsg=table(timestamp("2026.06.01T{instant}.000") as timestamp)')
        actual = dolphin.run('audited_minute_history(NULL,snapMsg,historyCodesForTest,historyCountForTest)')
        reference = dolphin.run('''
            expectedHistory=build_minute_bars(select * from snapRaw where TradeTime<=time(snapMsg.timestamp[0]))
            expectedHistory=select * from expectedHistory where code in historyCodesForTest,time<=snapMsg.timestamp[0] order by code,time desc
            update expectedHistory set ordinal=cumcount(time) context by code
            select time,code,open,high,low,close,volume,amount from expectedHistory
                where ordinal<=historyCountForTest order by time,code
        ''')
        pd.testing.assert_frame_equal(actual, reference)
    audit = dolphin.run('coreBacktestSnapshotState["readAudit"]')
    # Both symbols start cold once; subsequent calls extend their individual
    # cursors, with a single batched read when both cursors are equal.
    assert audit.iloc[2]["codes"] == "000001.XSHE,600020.XSHG"
    assert audit.iloc[2]["begin"].time().isoformat() == "09:31:00.001000"
    assert audit.iloc[3]["begin"].time().isoformat() == "09:32:00.001000"
    assert len(audit) == 7  # Includes one intentional rollback read, not a reread of the other symbol.
    assert audit.iloc[-1]["codes"] == "600020.XSHG"


def test_minute_history_prunes_old_days_only_for_requested_symbols(dolphin):
    upload_quotes(dolphin, [stamp for stamp in [
        "2026-06-01 14:58:59", "2026-06-01 14:59:00", "2026-06-01 15:00:00",
        "2026-06-02 09:29:59", "2026-06-02 09:30:01", "2026-06-02 09:31:00",
    ] for _ in range(2)], symbols=("600020.SH", "000001.SZ"))
    dolphin.run('''
        coreBacktestSnapshotState=dict(STRING,ANY)
        coreBacktestSnapshotState["enabled"]=true
        coreBacktestSnapshotState["source"]=snapRaw
        coreBacktestSnapshotState["codes"]=symbol(["600020.XSHG","000001.XSHE"])
        coreBacktestSnapshotState["historyDates"]=2026.06.01 2026.06.02
        coreBacktestSnapshotState["history"]=dict(STRING,ANY)
        snapMsg=table(2026.06.02T09:31:00.000 as timestamp)
    ''')
    before = dolphin.run('getMinuteHistory(NULL,snapMsg,["000001.XSHE"],3)')
    assert len(before) == 3
    dolphin.run('getMinuteHistory(NULL,snapMsg,["600020.XSHG"],3)')
    dolphin.run('getMinuteHistory(NULL,snapMsg,["600020.XSHG"],1)')
    cached_codes = dolphin.run('keys(coreBacktestSnapshotState["history"]["2026.06.01"])')
    assert list(cached_codes) == ["000001.XSHE"]
    pd.testing.assert_frame_equal(before, dolphin.run('getMinuteHistory(NULL,snapMsg,["000001.XSHE"],3)'))
    dolphin.run('getMinuteHistory(NULL,snapMsg,["000001.XSHE"],1)')
    assert list(dolphin.run('keys(coreBacktestSnapshotState["history"])')) == ["2026.06.02"]


def test_order_quote_isolation_and_single_side_rejection(dolphin):
    dolphin.run('''
        coreBacktestSnapshotState=dict(STRING,ANY)
        coreBacktestSnapshotState["enabled"]=true
        coreBacktestSnapshotState["quotes"]=dict(SYMBOL,ANY)
        coreBacktestSnapshotState["codes"]=symbol(["600020.XSHG"])
        coreBacktestSnapshotState["quoteDate"]=date()
        snapMsg=table(2026.06.02T09:30:00.000 as timestamp)
    ''')
    with pytest.raises(RuntimeError, match="尚无可用快照"):
        dolphin.run('backtest_order_quote(snapMsg,"600020.XSHG")')
    dolphin.run('''
        snapQuotes=dict(SYMBOL,ANY)
        snapQuotes[`600020.XSHG]=[2026.06.01T15:00:00.000,10.0,9.99,10.01,100l,100l]
        coreBacktestSnapshotState["quotes"]=snapQuotes
    ''')
    with pytest.raises(RuntimeError, match="当日报价"):
        dolphin.run('backtest_order_quote(snapMsg,"600020.XSHG")')
    dolphin.run('''
        snapQuotes[`600020.XSHG]=[2026.06.02T09:31:00.000,10.0,9.99,10.01,100l,100l]
        coreBacktestSnapshotState["quotes"]=snapQuotes
    ''')
    with pytest.raises(RuntimeError, match="当日报价"):
        dolphin.run('backtest_order_quote(snapMsg,"600020.XSHG")')


def test_minute_history_cross_day_and_lunch_does_not_create_empty_bars(dolphin):
    upload_quotes(dolphin, ["2026-06-01 14:58:59", "2026-06-01 14:59:00", "2026-06-01 15:00:00",
                           "2026-06-02 09:29:59", "2026-06-02 09:30:01", "2026-06-02 09:31:00",
                           "2026-06-02 11:30:00", "2026-06-02 13:00:00", "2026-06-02 13:01:00"])
    dolphin.run('''
        coreBacktestSnapshotState=dict(STRING,ANY)
        coreBacktestSnapshotState["enabled"]=true
        coreBacktestSnapshotState["source"]=snapRaw
        coreBacktestSnapshotState["codes"]=symbol(["600020.XSHG"])
        coreBacktestSnapshotState["historyDates"]=2026.06.01 2026.06.02
        coreBacktestSnapshotState["history"]=dict(STRING,ANY)
        snapMsg=table(2026.06.02T09:31:00.000 as timestamp)
    ''')
    history = dolphin.run('getMinuteHistory(NULL,snapMsg,["600020.XSHG"],3)')
    assert history.time.tolist() == list(pd.to_datetime(["2026-06-01 14:59", "2026-06-01 15:00", "2026-06-02 09:31"]))
    assert history.volume.tolist() == [100, 100, 200]
    dolphin.run('snapMsg=table(2026.06.02T12:30:00.000 as timestamp)')
    history = dolphin.run('getMinuteHistory(NULL,snapMsg,["600020.XSHG"],1)')
    assert history.time.tolist() == [pd.Timestamp("2026-06-02 11:30")]


def test_incremental_history_does_not_cache_unfinished_opening_minutes(dolphin):
    upload_quotes(dolphin, ["2026-06-01 " + t for t in [
        "09:29:59", "09:30:00", "09:30:20", "09:31:00", "11:30:00",
        "13:00:00", "13:00:20", "13:01:00",
    ]], prices=[9, 10, 12, 11, 13, 14, 15, 14])
    dolphin.run('''
        coreBacktestSnapshotState=dict(STRING,ANY)
        coreBacktestSnapshotState["enabled"]=true
        coreBacktestSnapshotState["source"]=snapRaw
        coreBacktestSnapshotState["codes"]=symbol(["600020.XSHG"])
        coreBacktestSnapshotState["historyDates"]=date([2026.06.01])
        coreBacktestSnapshotState["history"]=dict(STRING,ANY)
    ''')
    for instant in ["09:30:00", "09:31:00", "13:00:00", "13:01:00"]:
        dolphin.run(f'snapMsg=table(timestamp("2026.06.01T{instant}.000") as timestamp)')
        actual = dolphin.run('getMinuteHistory(NULL,snapMsg,["600020.XSHG"],100)')
        expected = dolphin.run('''
            complete=build_minute_bars(select * from snapRaw where TradeTime<=time(snapMsg.timestamp[0]))
            select time,code,open,high,low,close,volume,amount from complete where time<=snapMsg.timestamp[0]
        ''')
        pd.testing.assert_frame_equal(actual, expected)
        assert not actual.duplicated(["time", "code"]).any()


def test_python_entry_replays_unfiltered_candidates_and_keeps_daily_history_boundary(dolphin, monkeypatch):
    if os.getenv("ARENA_TEST_SNAPSHOT_DATA") != "1":
        pytest.skip("opt in to real StockSnapshot reads")

    class LocalModuleSession:
        """Resolve only this test's freshly compiled functions in its own session.

        This tests the real Python entry without publishing modules to shared nodes.
        """
        def run(self, script, *args, **kwargs):
            return dolphin.run(script.replace("backtest::", ""), *args, **kwargs)

        def __getattr__(self, name):
            return getattr(dolphin, name)

    monkeypatch.setattr(backtest_api, "load_backtest_environment", lambda *args, **kwargs: None)
    callbacks = {
        "initialize": 'def initialize(mutable ctx) { ctx["ordered"]=false; ctx["seen"]=false }',
        "beforeTrading": "def beforeTrading(mutable ctx) {}",
        "onBar": "def onBar(mutable ctx,msg,indicator) {}",
        "onSnapshot": '''def onSnapshot(mutable ctx,msg,indicator) {
            daily=getHistoryData(ctx,msg,false)
            if (daily.rows()>0 && max(date(daily.time))>=date(msg.timestamp[0])) throw "daily lookahead"
            if (time(msg.timestamp[0])>=09:35:00.000 && !ctx["ordered"]) {
                history=getMinuteHistory(ctx,msg,["600020.XSHG"],3)
                if (history.rows()!=3) throw "minute history missing"
                if (max(history.time)>msg.timestamp[0]) throw "minute lookahead"
                order_target_value(ctx,msg,"600020.XSHG",1000.0)
                ctx["ordered"]=true
            }
            if (any(string(msg.symbol)=="600020.XSHG")) ctx["seen"]=true
        }''',
        "onOrder": "def onOrder(mutable ctx,events) {}",
        "onTrade": "def onTrade(mutable ctx,events) {}",
        "afterTrading": "def afterTrading(mutable ctx) {}",
        "finalize": "def finalize(mutable ctx) {}",
    }
    params = BacktestParameters.model_validate({
        "market_source": "snapshot", "adj": None,
        "config": {"cash": 100000, "commission": 0.0003, "tax": 0.001, "syntheticSpread": 0},
        "callbacks": callbacks,
        # Deliberately exclude every daily selection row. Raw candidate quotes
        # must still be replayed so a previously held stock can be liquidated.
        "dataset_query": {"start_date": "2026-06-01", "end_date": "2026-06-01", "lookback": "P0D",
                          "codes": ["600020.SH"], "factors": ["close"],
                          "derivatives": {"selected": {"type": "DIRECT", "op": "binary.lt",
                                                         "fields": {"left": "close", "right": 0}, "params": {}}},
                          "filters": ["selected"]},
    })
    local = LocalModuleSession()
    prepared = backtest_api.prepare_backtest_session(params, local, log_progress=False)
    assert dolphin.run("coreBacktestFilteredData.rows()") == 0
    backtest_api.execute_prepared_backtest(prepared, local, log_progress=False)
    try:
        assert dolphin.run('Backtest::getContextDict(coreBacktestEngine)["seen"]')
        trades = dolphin.run("Backtest::getTradeDetails(coreBacktestEngine)")
        assert trades.loc[trades.orderStatus.isin([0, 1]), "tradeQty"].sum() > 0
    finally:
        backtest_api.drop_prepared_backtest_engine(local)


def test_three_live_trading_days_minute_decisions_and_four_outputs(dolphin, tmp_path):
    if os.getenv("ARENA_TEST_SNAPSHOT_DATA") != "1":
        pytest.skip("opt in to three days of real StockSnapshot reads")
    build_query_table(FactorQuery(start_date="2026-06-01", end_date="2026-06-03", lookback="P0D",
                                  codes=["600020.SH", "000001.SZ"], factors=["pre_close", "up_limit", "down_limit"]),
                      session=dolphin, source_ref="liveSource", computed_ref="liveComputed", filtered_ref="liveFiltered", data_ref="liveData", log_progress=False)
    dolphin.run('''
        snapRaw=loadTable("dfs://StockSnapshot","snapshot")
        snapReference=select time,symbol(strReplace(strReplace(string(code),".SH",".XSHG"),".SZ",".XSHE")) as code,pre_close,up_limit,down_limit from liveData
        coreBacktestSnapshotState=dict(STRING,ANY)
        def liveInit(mutable ctx) { ctx["minute"]=timestamp(); ctx["decisions"]=0; ctx["bars"]=0; ctx["fills"]=0l; ctx["calls"]=0; ctx["maxHistory"]=0 }
        def liveSnapshot(mutable ctx,msg,indicator) {
            ctx["calls"]+=1
            current=bar(msg.timestamp[0],60000)
            if (!isNull(ctx["minute"]) && ctx["minute"]==current) return
            ctx["minute"]=current
            if (time(current)<09:32:00.000 || time(current)>=14:59:00.000) return
            history=getMinuteHistory(ctx,msg,["600020.XSHG","000001.XSHE"],5)
            ctx["maxHistory"]=max([ctx["maxHistory"],history.rows()])
            if (history.rows()<10) return
            ctx["decisions"]+=1
            ctx["bars"]+=history.rows()
            quotes=objByName("coreBacktestSnapshotState")["quotes"]
            for (targetCode in ["600020.XSHG","000001.XSHE"]) {
                if (!(targetCode in quotes)) continue
                h=select * from history where string(code)=targetCode order by time
                target=iif(last(h.close)>=avg(h.close),100l,0l)
                q=quotes[targetCode]
                if (q[4]>0 && q[5]>0) order_target(ctx,msg,targetCode,target)
            }
        }
        def liveTrade(mutable ctx,trades) { for (event in trades) ctx["fills"]+=event.tradeQty }
        liveConfig=dict(STRING,ANY)
        liveConfig["cash"]=100000.0
        liveConfig["commission"]=0.0003
        liveConfig["tax"]=0.001
        liveConfig["startDate"]=2026.06.01
        liveConfig["endDate"]=2026.06.03
        liveConfig["strategyGroup"]="stock"
        liveConfig["msgAsTable"]=true
        liveConfig["latency"]=0
        liveEmpty=table(1:0,`symbol`symbolSource`timestamp`lastPrice`upLimitPrice`downLimitPrice`totalBidQty`totalOfferQty`bidPrice`bidQty`offerPrice`offerQty`prevClosePrice,[SYMBOL,SYMBOL,TIMESTAMP,DOUBLE,DOUBLE,DOUBLE,LONG,LONG,DOUBLE[],LONG[],DOUBLE[],LONG[],DOUBLE])
    ''')
    dolphin.upload({"liveName": "arena_live_snapshot_" + uuid4().hex})
    dolphin.run('''
        liveEngine=run_snapshot_backtest(liveName,liveConfig,snapRaw,snapReference,symbol(["600020.XSHG","000001.XSHE"]),
            2026.06.01 2026.06.02 2026.06.03,liveEmpty,liveInit,snapBefore,snapBar,liveSnapshot,snapOrder,liveTrade,snapAfter,snapFinal)
    ''')
    try:
        print("Live context:", dolphin.run('Backtest::getContextDict(liveEngine)[`calls`maxHistory`decisions`bars`fills]'), flush=True)
        diagnostics = dolphin.run('coreBacktestSnapshotState["diagnostics"]')
        print("\nLive snapshot diagnostics (DOS object bytes, not process RSS):\n" + diagnostics.to_string(index=False), flush=True)
        for name, function in {"trade_details": "getTradeDetails", "daily_positions": "getDailyPosition", "daily_portfolios": "getDailyTotalPortfolios", "daily_trading_statistics": "getDailyTradingStatistics"}.items():
            frame = dolphin.run(f"Backtest::{function}(liveEngine)")
            assert not frame.empty
            frame.to_parquet(tmp_path / f"{name}.parquet", index=False)
            pd.testing.assert_frame_equal(frame, pd.read_parquet(tmp_path / f"{name}.parquet"))
            if name == "daily_portfolios":
                assert len(frame) == 3
        print("Minute decisions:", dolphin.run('Backtest::getContextDict(liveEngine)["decisions"]'))
        assert dolphin.run('Backtest::getContextDict(liveEngine)["decisions"]') > 500
        assert dolphin.run('Backtest::getContextDict(liveEngine)["fills"]') > 0
    finally:
        dolphin.run("Backtest::dropBacktestEngine(liveEngine)")
