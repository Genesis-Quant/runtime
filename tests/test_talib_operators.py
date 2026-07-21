"""使用 Python TA-Lib 独立验证全部 DolphinDB TA 算符。"""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import pytest
import talib

from core.operators import Derivative
from core.operators.base import TimeSeriesOperator
from tests.support.assertions import assert_vector_equal
from tests.support.dsl import TRUE_NODE, compute_factors, direct, time_series


@dataclass(frozen=True)
class TalibContract:
    """保存一个完整 TA DSL 节点及其 Python TA-Lib 参考结果。"""

    definition: dict[str, object]
    expected: np.ndarray


def _ts(
    operation: str,
    fields: dict[str, object],
    params: dict[str, object] | None = None,
) -> dict[str, object]:
    """构造对全部输入行启用的 TA 时序节点。"""
    return time_series(operation, fields, params, on=TRUE_NODE)


def _source(case: int, size: int = 180) -> pd.DataFrame:
    """生成带趋势、周期和随机扰动且价格关系合法的 OHLCV 序列。"""
    rng = np.random.default_rng(20240701 + case)
    position = np.arange(size, dtype=float)
    center = (
        80.0
        + 0.08 * position
        + 2.5 * np.sin(position / (5.0 + case % 4))
        + np.cumsum(rng.normal(0.0, 0.32, size))
    )
    open_ = center + rng.normal(0.0, 0.28, size)
    close = center + rng.normal(0.0, 0.28, size)
    high = np.maximum(open_, close) + rng.uniform(0.15, 1.35, size)
    low = np.minimum(open_, close) - rng.uniform(0.15, 1.25, size)
    volume = rng.integers(50_000, 2_000_000, size).astype(float)
    return pd.DataFrame(
        {
            "time": pd.date_range("2020-01-02", periods=size, freq="B"),
            "code": [f"CASE{case:02d}"] * size,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


def _contracts(source: pd.DataFrame, case: int) -> dict[str, TalibContract]:
    """显式定义全部 TA 算符及对应的 Python TA-Lib 调用。"""
    open_ = source["open"].to_numpy(dtype=float)
    high = source["high"].to_numpy(dtype=float)
    low = source["low"].to_numpy(dtype=float)
    close = source["close"].to_numpy(dtype=float)
    volume = source["volume"].to_numpy(dtype=float)

    unary = {"col": "close"}
    high_low = {"high": "high", "low": "low"}
    ohlc = {"high": "high", "low": "low", "close": "close"}
    full_ohlc = {**ohlc, "open": "open"}
    ohlcv = {**ohlc, "volume": "volume"}
    close_volume = {"close": "close", "volume": "volume"}

    period = 6 + case % 5
    fast = 3 + case % 3
    slow = fast + 5 + case % 2
    signal = 2 + case % 3
    ma_type = (0, 1, 2, 3, 4, 5, 6, 8, 0, 8)[case]
    nbdev = 1.0 + case * 0.1
    vfactor = 0.45 + case * 0.05
    period1 = 4 + case % 3
    period2 = period1 + 4
    period3 = period2 + 7

    aroon_down, aroon_up = talib.AROON(high, low, timeperiod=period)
    bb_upper, bb_middle, bb_lower = talib.BBANDS(
        close,
        timeperiod=period,
        nbdevup=nbdev,
        nbdevdn=nbdev + 0.25,
        matype=ma_type,
    )
    macd, macd_signal, macd_hist = talib.MACD(
        close,
        fastperiod=fast,
        slowperiod=slow,
        signalperiod=signal,
    )

    return {
        "ad": TalibContract(_ts("talib.ad", ohlcv), talib.AD(high, low, close, volume)),
        "adx": TalibContract(_ts("talib.adx", ohlc, {"time_period": period}), talib.ADX(high, low, close, timeperiod=period)),
        "adxr": TalibContract(_ts("talib.adxr", ohlc, {"time_period": period}), talib.ADXR(high, low, close, timeperiod=period)),
        "apo": TalibContract(_ts("talib.apo", unary, {"fast_period": fast, "slow_period": slow, "ma_type": ma_type}), talib.APO(close, fastperiod=fast, slowperiod=slow, matype=ma_type)),
        "aroon_down": TalibContract(_ts("talib.aroon", high_low, {"time_period": period, "output": "down"}), aroon_down),
        "aroon_up": TalibContract(_ts("talib.aroon", high_low, {"time_period": period, "output": "up"}), aroon_up),
        "aroon_osc": TalibContract(_ts("talib.aroonOsc", high_low, {"time_period": period}), talib.AROONOSC(high, low, timeperiod=period)),
        "atr": TalibContract(_ts("talib.atr", ohlc, {"time_period": period}), talib.ATR(high, low, close, timeperiod=period)),
        "avg_price": TalibContract(_ts("talib.avgPrice", full_ohlc), talib.AVGPRICE(open_, high, low, close)),
        "beta": TalibContract(_ts("talib.beta", high_low, {"time_period": period}), talib.BETA(high, low, timeperiod=period)),
        "bop": TalibContract(_ts("talib.bop", full_ohlc), talib.BOP(open_, high, low, close)),
        "bb_upper": TalibContract(_ts("talib.bBands", unary, {"time_period": period, "nbdev_up": nbdev, "nbdev_down": nbdev + 0.25, "ma_type": ma_type, "output": "upper"}), bb_upper),
        "bb_middle": TalibContract(_ts("talib.bBands", unary, {"time_period": period, "nbdev_up": nbdev, "nbdev_down": nbdev + 0.25, "ma_type": ma_type, "output": "middle"}), bb_middle),
        "bb_lower": TalibContract(_ts("talib.bBands", unary, {"time_period": period, "nbdev_up": nbdev, "nbdev_down": nbdev + 0.25, "ma_type": ma_type, "output": "lower"}), bb_lower),
        "cci": TalibContract(_ts("talib.cci", ohlc, {"time_period": period}), talib.CCI(high, low, close, timeperiod=period)),
        "correl": TalibContract(_ts("talib.correl", high_low, {"time_period": period}), talib.CORREL(high, low, timeperiod=period)),
        "dema": TalibContract(_ts("talib.dema", unary, {"time_period": period}), talib.DEMA(close, timeperiod=period)),
        "dx": TalibContract(_ts("talib.dx", ohlc, {"time_period": period}), talib.DX(high, low, close, timeperiod=period)),
        "ema": TalibContract(_ts("talib.ema", unary, {"time_period": period}), talib.EMA(close, timeperiod=period)),
        "kama": TalibContract(_ts("talib.kama", unary, {"time_period": period}), talib.KAMA(close, timeperiod=period)),
        "linearreg": TalibContract(_ts("talib.linearreg", unary, {"time_period": period}), talib.LINEARREG(close, timeperiod=period)),
        "linearreg_angle": TalibContract(_ts("talib.linearreg_angle", unary, {"time_period": period}), talib.LINEARREG_ANGLE(close, timeperiod=period)),
        "linearreg_intercept": TalibContract(_ts("talib.linearreg_intercept", unary, {"time_period": period}), talib.LINEARREG_INTERCEPT(close, timeperiod=period)),
        "linearreg_slope": TalibContract(_ts("talib.linearreg_slope", unary, {"time_period": period}), talib.LINEARREG_SLOPE(close, timeperiod=period)),
        "ma": TalibContract(_ts("talib.ma", unary, {"time_period": period, "ma_type": ma_type}), talib.MA(close, timeperiod=period, matype=ma_type)),
        "macd": TalibContract(_ts("talib.macd", unary, {"fast_period": fast, "slow_period": slow, "signal_period": signal, "output": "macd"}), macd),
        "macd_signal": TalibContract(_ts("talib.macd", unary, {"fast_period": fast, "slow_period": slow, "signal_period": signal, "output": "signal"}), macd_signal),
        "macd_hist": TalibContract(_ts("talib.macd", unary, {"fast_period": fast, "slow_period": slow, "signal_period": signal, "output": "hist"}), macd_hist),
        "med_price": TalibContract(_ts("talib.medPrice", high_low), talib.MEDPRICE(high, low)),
        "mfi": TalibContract(_ts("talib.mfi", ohlcv, {"time_period": period}), talib.MFI(high, low, close, volume, timeperiod=period)),
        "mid_point": TalibContract(_ts("talib.midPoint", unary, {"time_period": period}), talib.MIDPOINT(close, timeperiod=period)),
        "mid_price": TalibContract(_ts("talib.midPrice", high_low, {"time_period": period}), talib.MIDPRICE(high, low, timeperiod=period)),
        "minus_di": TalibContract(_ts("talib.minus_di", ohlc, {"time_period": period}), talib.MINUS_DI(high, low, close, timeperiod=period)),
        "minus_dm": TalibContract(_ts("talib.minus_dm", high_low, {"time_period": period}), talib.MINUS_DM(high, low, timeperiod=period)),
        "mom": TalibContract(_ts("talib.mom", unary, {"time_period": period}), talib.MOM(close, timeperiod=period)),
        "natr": TalibContract(_ts("talib.natr", ohlc, {"time_period": period}), talib.NATR(high, low, close, timeperiod=period)),
        "obv": TalibContract(_ts("talib.obv", close_volume), talib.OBV(close, volume)),
        "plus_di": TalibContract(_ts("talib.plus_di", ohlc, {"time_period": period}), talib.PLUS_DI(high, low, close, timeperiod=period)),
        "plus_dm": TalibContract(_ts("talib.plus_dm", high_low, {"time_period": period}), talib.PLUS_DM(high, low, timeperiod=period)),
        "ppo": TalibContract(_ts("talib.ppo", unary, {"fast_period": fast, "slow_period": slow, "ma_type": ma_type}), talib.PPO(close, fastperiod=fast, slowperiod=slow, matype=ma_type)),
        "roc": TalibContract(_ts("talib.roc", unary, {"time_period": period}), talib.ROC(close, timeperiod=period)),
        "rocp": TalibContract(_ts("talib.rocp", unary, {"time_period": period}), talib.ROCP(close, timeperiod=period)),
        "rocr": TalibContract(_ts("talib.rocr", unary, {"time_period": period}), talib.ROCR(close, timeperiod=period)),
        "rocr100": TalibContract(_ts("talib.rocr100", unary, {"time_period": period}), talib.ROCR100(close, timeperiod=period)),
        "rsi": TalibContract(_ts("talib.rsi", unary, {"time_period": period}), talib.RSI(close, timeperiod=period)),
        "sma": TalibContract(_ts("talib.sma", unary, {"time_period": period}), talib.SMA(close, timeperiod=period)),
        "stddev": TalibContract(_ts("talib.stddev", unary, {"time_period": period, "nbdev": nbdev}), talib.STDDEV(close, timeperiod=period, nbdev=nbdev)),
        "t3": TalibContract(_ts("talib.t3", unary, {"time_period": period, "vfactor": vfactor}), talib.T3(close, timeperiod=period, vfactor=vfactor)),
        "tema": TalibContract(_ts("talib.tema", unary, {"time_period": period}), talib.TEMA(close, timeperiod=period)),
        "trange": TalibContract(_ts("talib.trange", ohlc), talib.TRANGE(high, low, close)),
        "trima": TalibContract(_ts("talib.trima", unary, {"time_period": period}), talib.TRIMA(close, timeperiod=period)),
        "trix": TalibContract(_ts("talib.trix", unary, {"time_period": period}), talib.TRIX(close, timeperiod=period)),
        "tsf": TalibContract(_ts("talib.tsf", unary, {"time_period": period}), talib.TSF(close, timeperiod=period)),
        "typ_price": TalibContract(_ts("talib.typPrice", ohlc), talib.TYPPRICE(high, low, close)),
        "ult_osc": TalibContract(_ts("talib.ultOsc", ohlc, {"period1": period1, "period2": period2, "period3": period3}), talib.ULTOSC(high, low, close, timeperiod1=period1, timeperiod2=period2, timeperiod3=period3)),
        "var": TalibContract(_ts("talib.var", unary, {"time_period": period, "nbdev": nbdev}), talib.VAR(close, timeperiod=period, nbdev=nbdev)),
        "wcl_price": TalibContract(_ts("talib.wclPrice", ohlc), talib.WCLPRICE(high, low, close)),
        "willr": TalibContract(_ts("talib.willr", ohlc, {"time_period": period}), talib.WILLR(high, low, close, timeperiod=period)),
        "wma": TalibContract(_ts("talib.wma", unary, {"time_period": period}), talib.WMA(close, timeperiod=period)),
    }


def test_talib_inventory_is_explicit_and_complete() -> None:
    """要求测试清单与登记的 54 个 TA 算符精确一致。"""
    contracts = _contracts(_source(0), 0)
    tested = {contract.definition["op"] for contract in contracts.values()}
    registered = {
        operation
        for operation, model in Derivative.operators.items()
        if operation.startswith("talib.") and issubclass(model, TimeSeriesOperator)
    }
    assert len(registered) == 54
    assert tested == registered


@pytest.mark.parametrize("case", range(10))
def test_all_talib_operators_match_python_talib(ddb_session: Any, case: int) -> None:
    """用十组价格路径和参数逐值比较全部 TA 算符及多输出分量。"""
    source = _source(case)
    contracts = _contracts(source, case)
    result = compute_factors(
        ddb_session,
        source,
        {name: contract.definition for name, contract in contracts.items()},
    )
    for name, contract in contracts.items():
        assert_vector_equal(
            result[name],
            contract.expected,
            atol=1e-7,
            rtol=1e-9,
        )


@pytest.mark.parametrize("pattern", ["leading", "interior", "scattered", "trailing"])
def test_all_talib_operators_match_when_on_excludes_null_rows(
    ddb_session: Any,
    pattern: str,
) -> None:
    """用 on 排除缺失行后，全部 TA 算符与压缩序列的 TA-Lib 结果一致。"""
    source = _source(3)
    price_columns = ["open", "high", "low", "close"]
    if pattern == "leading":
        source.loc[:2, [*price_columns, "volume"]] = np.nan
    elif pattern == "interior":
        source.loc[80, [*price_columns, "volume"]] = np.nan
    elif pattern == "scattered":
        source.loc[[55, 73, 91, 109], [*price_columns, "volume"]] = np.nan
    else:
        source.loc[len(source) - 1, [*price_columns, "volume"]] = np.nan

    selected = source.loc[source["close"].notna()].reset_index(drop=True)
    contracts = _contracts(selected, 3)
    definitions: dict[str, dict[str, object]] = {}
    expected: dict[str, np.ndarray] = {}
    mask = source["close"].notna().to_numpy()
    on = direct("unary.not_null", {"col": "close"})
    for name, contract in contracts.items():
        definition = deepcopy(contract.definition)
        definition["on"] = on
        definitions[name] = definition
        restored = np.full(len(source), np.nan)
        restored[mask] = contract.expected
        expected[name] = restored
    result = compute_factors(
        ddb_session,
        source,
        definitions,
    )
    for name, values in expected.items():
        assert_vector_equal(
            result[name],
            values,
            atol=1e-7,
            rtol=1e-9,
        )


@pytest.mark.parametrize("position", [0, 1, 20, 75, 178, 179])
def test_pointwise_talib_operators_preserve_current_null(
    ddb_session: Any,
    position: int,
) -> None:
    """逐行价格算符在任一当前输入缺失时返回 NULL，而不是零或旧值。"""
    source = _source(5)
    source.loc[position, ["open", "high", "low", "close"]] = np.nan
    contracts = _contracts(source, 5)
    names = ["avg_price", "bop", "med_price", "typ_price", "wcl_price"]
    result = compute_factors(
        ddb_session,
        source,
        {name: contracts[name].definition for name in names},
    )
    for name in names:
        assert_vector_equal(result[name], contracts[name].expected)
