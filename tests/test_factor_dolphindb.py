"""Factor calculation regressions; opt in to an isolated, read-only-data session."""

import os

import numpy as np
import pandas as pd
import pytest

from runtime.database import create_session
from runtime.database.compile.factor.scripts import build_script


@pytest.fixture(scope="module")
def dolphin():
    if os.getenv("ARENA_TEST_DOLPHINDB") != "1":
        pytest.skip("requires explicit opt-in to the configured DolphinDB server")
    session = create_session(max_time=300)
    try:
        session.run(build_script().replace("module factor\n", ""))
        yield session
    finally:
        session.close()


def test_saturated_regression_does_not_standardize_roundoff(dolphin):
    result = dolphin.run('''
        t=table(take(timestamp(2025.01.06),3) as time,`A`B`C as code,
            1.0 4 2 as signal,100.0 200 300 as mktmv,1 2 2 as industry)
        factorPreprocess(t,["signal"],2)
    ''')
    assert result.signal.isna().all()
    assert result.signal_group.isna().all()


def test_preprocessing_is_permutation_invariant_and_matches_svd(dolphin):
    raw = pd.DataFrame({
        "time": pd.to_datetime(["2025-01-06"] * 12),
        "code": [f"{index:06d}.SZ" for index in range(12)],
        "signal": [1., 4, 2, 6, 3, 9, 5, 10, 7, 11, 8, 12],
        "mktmv": np.exp(np.arange(12) / 12 + 5),
        "industry": [1, 2, 2, 3] * 3,
    })
    dolphin.upload({"auditFactorInput": raw})
    actual = dolphin.run('factorPreprocess(auditFactorInput,["signal"],3)').set_index("code").sort_index()
    dolphin.upload({"auditFactorInput": raw.iloc[::-1].reset_index(drop=True)})
    permuted = dolphin.run('factorPreprocess(auditFactorInput,["signal"],3)').set_index("code").sort_index()
    pd.testing.assert_frame_equal(actual, permuted)
    values = raw.signal.to_numpy()
    median = np.median(values)
    mad = np.median(abs(values - median))
    values = np.clip(values, median - 3 * mad, median + 3 * mad)
    y = (values - values.mean()) / values.std()
    mv = np.log(raw.mktmv.to_numpy())
    x = np.column_stack([np.ones(len(raw)), (mv - mv.mean()) / mv.std(), raw.industry == 2, raw.industry == 3])
    residual = y - x @ np.linalg.lstsq(x, y, rcond=None)[0]
    expected = (residual - residual.mean()) / residual.std()
    np.testing.assert_allclose(actual.signal, expected, atol=1e-12)


@pytest.mark.parametrize("group", ["99", "0.5", "-1", "double(NULL)"])
@pytest.mark.parametrize("calculation", [
    'factorValidateGroups(t,["signal"],2)',
    'factorGroupReturns(t,["ret"],["signal"],2,1)',
    'factorGroupTurnover(t,["signal"],1 2,2,1)',
])
def test_manual_groups_are_validated_before_any_cast(dolphin, group, calculation):
    dolphin.run(f'''
        t=table(take(timestamp(2025.01.06),2) as time,`A`B as code,
            1.0 2.0 as signal,take({group},2) as signal_group,
            1.0 1.0 as mktmv,0.1 0.2 as ret)
    ''')
    with pytest.raises(RuntimeError, match="signal_group.*整数"):
        dolphin.run(calculation)


def test_turnover_uses_shared_dates_not_nonempty_portfolio_dates(dolphin):
    result = dolphin.run('''
        t=table(timestamp(take(2025.01.06,4) join take(2025.01.07,4) join take(2025.01.08,4)) as time,
            take(`A`B`C`D,12) as code,double(1 2 3 4 1 2 3 4 1 2 3 4) as signal,
            int(0 0 1 1 1 1 1 1 0 0 1 1) as signal_group)
        factorGroupTurnover(t,["signal"],1 2,2,1)
    ''').set_index(["time", "periods"])
    assert result.loc[("2025-01-08", 1), "group0"] == 1
    assert result.loc[("2025-01-08", 2), "group0"] == 0
    assert np.isnan(result.loc[("2025-01-07", 1), "group0"])


def test_whole_cross_section_gap_remains_on_trading_axis(dolphin):
    result = dolphin.run('''
        t=table(timestamp(take(2025.01.06,2) join take(2025.01.08,2)) as time,
            take(`A`B,4) as code,1.0 2 1 2 as signal,0 1 0 1 as signal_group)
        factorGroupTurnover(t,["signal"],1 2,2,1,"time","code",2025.01.06 2025.01.07 2025.01.08)
    ''').set_index(["time", "periods"])
    assert len(result) == 6
    assert result.loc[("2025-01-08", 1), "group0"] == 1
    assert result.loc[("2025-01-08", 2), "group0"] == 0
    assert np.isnan(result.loc[("2025-01-08", 1), "rank_autocorrelation"])


def test_ties_use_code_order_and_opposite_endpoints(dolphin):
    dolphin.run('''
        t=table(take(timestamp(2025.01.06),4) as time,`A`B`C`D as code,
            take(1.0,4) as signal,0 0 1 1 as signal_group,
            take(1.0,4) as mktmv,1.0 2 3 4 as ret)
    ''')
    normal = dolphin.run('factorGroupReturns(t,["ret"],["signal"],2,1)')
    permuted = dolphin.run('factorGroupReturns(t[3 2 1 0],["ret"],["signal"],2,1)')
    pd.testing.assert_frame_equal(normal, permuted)
    assert normal.signal_ret_bottom.iloc[0] == 1
    assert normal.signal_ret_top.iloc[0] == 4
    turnover = dolphin.run('''
        t2=t[3 2 1 0]
        update t2 set time=timestamp(2025.01.07)
        factorGroupTurnover(unionAll(t,t2),["signal"],[1],2,1)
    ''')
    assert turnover.bottom.iloc[1] == 0
    assert turnover.top.iloc[1] == 0


@pytest.mark.parametrize("weights", ["-1.0 2.0", "-1.0 -2.0"])
def test_market_value_weighting_rejects_negative_weights(dolphin, weights):
    with pytest.raises(RuntimeError, match="市值权重"):
        dolphin.run(f"factorWeightedReturn({weights},0.1 0.2)")


def test_weighted_return_keeps_pairwise_null_and_zero_weight_semantics(dolphin):
    assert dolphin.run("factorWeightedReturn([1.0, 2.0, double(NULL), 0.0],[0.1, 0.2, 0.9, 100.0])") == pytest.approx(1 / 6)
    assert dolphin.run("factorWeightedReturn([1.0, 2.0],[double(NULL), 0.2])") == pytest.approx(0.2)
    assert dolphin.run("isNull(factorWeightedReturn(0.0 0.0,0.1 0.2))")


def test_empty_factor_table_preserves_explicit_dates(dolphin):
    actual = dolphin.run('''
        t=table(array(TIMESTAMP,0) as time,array(SYMBOL,0) as code,
            array(DOUBLE,0) as signal,array(INT,0) as signal_group)
        factorGroupTurnover(t,["signal"],1 2,2,1,"time","code",2025.01.06 2025.01.07 2025.01.08)
    ''')
    assert len(actual) == 6
    assert actual[["bottom", "top", "group0", "group1", "rank_autocorrelation"]].isna().all().all()


def test_turnover_matches_independent_sets_on_random_sparse_multi_factor_data(dolphin):
    dates = pd.bdate_range("2025-01-06", periods=8)
    rng = np.random.default_rng(91)
    rows = []
    for day, date in enumerate(dates):
        if day == 3:
            continue
        for code in "ABCDEF":
            if rng.random() < 0.3:
                continue
            rows.append({"time": date, "code": code,
                         "first": float(rng.integers(0, 3)), "first_group": int(rng.integers(0, 3)),
                         "second": float(rng.integers(0, 3)), "second_group": int(rng.integers(0, 3))})
    data = pd.DataFrame(rows)
    dolphin.upload({"auditSparse": data.sample(frac=1, random_state=91).reset_index(drop=True),
                    "auditDates": dates.to_numpy()})
    actual = dolphin.run('factorGroupTurnover(auditSparse,["first","second"],1 2 4,3,2,"time","code",auditDates)')
    actual = actual.set_index(["factor", "periods", "time"])
    for factor in ["first", "second"]:
        portfolios = []
        for date in dates:
            daily = data.loc[data.time == date].sort_values([factor, "code"])
            portfolios.append({
                "bottom": set(daily.head(2).code), "top": set(daily.tail(2).code),
                **{f"group{group}": set(daily.loc[daily[factor+"_group"] == group, "code"]) for group in range(3)},
            })
        for period in [1, 2, 4]:
            for day, date in enumerate(dates):
                for name, current in portfolios[day].items():
                    value = actual.loc[(factor, period, date), name]
                    if day < period or not current:
                        assert np.isnan(value)
                    else:
                        expected = len(current - portfolios[day-period][name]) / len(current)
                        assert value == pytest.approx(expected)
