"""固定策略参数，比较原始 ETF 池与人工优化后的 ETF 池。"""

import math
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd

from core.database import create_session
from research import get_data, run_strategy

FACTOR_NAMES = [
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "adj_factor",
    "vol",
]
START_DATE = "2019-01-01"
END_DATE = "2026-07-26"
HISTORY_BUFFER_DAYS = 120

INITIAL_CASH = 100_000.0
MOMENTUM_WINDOW = 21
SELECT_COUNT = 4
RISK_WINDOW = 20
MAX_HISTORY_ROWS = 90
TARGET_VOLATILITY = 0.09
MAX_INVESTED_RATIO = 0.99

BASELINE_CODE_NAMES = [
    "518880.SH",
    "159980.SZ",
    "159981.SZ",
    "159985.SZ",
    "501018.SH",
    "513400.SH",
    "513100.SH",
    "513500.SH",
    "513180.SH",
    "513120.SH",
    "513070.SH",
    "588000.SH",
    "159967.SZ",
    "512890.SH",
    "159851.SZ",
]

# 相对原始池：
# 1. 删除能源化工，减少与原油、有色的周期暴露重叠。
# 2. 删除恒生科技，减少与纳指、科创和创成长的科技暴露重叠。
# 3. 删除金融科技，降低国内高弹性科技行业的集中度。
# 4. 增加日经 225，引入不同于美国和中国的发达市场周期。
CODE_NAMES = [
    "518880.SH",
    "159980.SZ",
    "159985.SZ",
    "501018.SH",
    "513400.SH",
    "513100.SH",
    "513500.SH",
    "513120.SH",
    "513070.SH",
    "588000.SH",
    "159967.SZ",
    "512890.SH",
    "513880.SH",
]


def calculate_performance(net_value: pd.Series) -> dict[str, Any]:
    """按 test_eft 的年化口径计算净值曲线指标。"""
    daily_returns = net_value.pct_change().dropna()
    years = (
        net_value.index[-1] - net_value.index[0]
    ).days / 365.2425
    annual_return = (
        net_value.iloc[-1] / net_value.iloc[0]
    ) ** (1 / years) - 1
    drawdown = net_value / net_value.cummax() - 1
    max_drawdown = -drawdown.min()
    annual_volatility = daily_returns.std(ddof=0) * math.sqrt(250)
    sharpe = (
        daily_returns.mean() - 0.04 / 250
    ) / daily_returns.std(ddof=0) * math.sqrt(250)

    return {
        "start_date": net_value.index[0],
        "end_date": net_value.index[-1],
        "trading_days": len(net_value),
        "final_net_value": float(net_value.iloc[-1]),
        "annual_return": float(annual_return),
        "max_drawdown": float(max_drawdown),
        "annual_volatility": float(annual_volatility),
        "sharpe": float(sharpe),
        "calmar": float(annual_return / max_drawdown),
    }


def main() -> None:
    """查询一次数据，回测两个 ETF 池并展示比较结果。"""
    session = create_session()
    try:
        data_profile = get_data(
            session,
            FACTOR_NAMES,
            START_DATE,
            END_DATE,
            HISTORY_BUFFER_DAYS,
        )
        baseline_net_value = run_strategy(
            session,
            BASELINE_CODE_NAMES,
            START_DATE,
            END_DATE,
            INITIAL_CASH,
            MOMENTUM_WINDOW,
            SELECT_COUNT,
            RISK_WINDOW,
            MAX_HISTORY_ROWS,
            TARGET_VOLATILITY,
            MAX_INVESTED_RATIO,
        )
        optimized_net_value = run_strategy(
            session,
            CODE_NAMES,
            START_DATE,
            END_DATE,
            INITIAL_CASH,
            MOMENTUM_WINDOW,
            SELECT_COUNT,
            RISK_WINDOW,
            MAX_HISTORY_ROWS,
            TARGET_VOLATILITY,
            MAX_INVESTED_RATIO,
        )
    finally:
        session.close()

    print("data_profile:", data_profile)
    print(
        "baseline:",
        calculate_performance(baseline_net_value),
    )
    print(
        "optimized:",
        calculate_performance(optimized_net_value),
    )

    figure, axis = plt.subplots(figsize=(12, 5))
    axis.plot(
        baseline_net_value.index,
        baseline_net_value.to_numpy(),
        label="Baseline",
    )
    axis.plot(
        optimized_net_value.index,
        optimized_net_value.to_numpy(),
        label="Optimized CODE_NAMES",
    )
    axis.set(
        title="ETF Pool Optimization",
        xlabel="Date",
        ylabel="Net Value",
    )
    axis.grid(alpha=0.3)
    axis.legend()
    figure.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
