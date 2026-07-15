"""时序算符共用的 DolphinDB 函数。"""

from core.dolphindb.function import DolphinDBFunction


ROLLING_MIN_PERIODS = DolphinDBFunction(
    """
def rolling_min_periods(window, min_periods) {
    // 规范化滚动窗口的最少观测数；NULL 表示要求完整 window。
    if (isNull(min_periods)) return int(window)
    return int(min_periods)
}
"""
)

MASK_EXPANDING_RESULT = DolphinDBFunction(
    """
def mask_expanding_result(result, value, min_periods) {
    // 在累计有效观测数达到 min_periods 前，将单序列 expanding 结果置为 NULL。
    return iif(cumcount(value) < int(min_periods), NULL, result)
}
"""
)

MASK_PAIR_EXPANDING_RESULT = DolphinDBFunction(
    """
def mask_pair_expanding_result(result, left, right, min_periods) {
    // 仅统计左右两列同时有效的样本，并遮蔽观测不足的双序列 expanding 结果。
    valid = iif(isValid(left) && isValid(right), 1, int(NULL))
    return iif(cumcount(valid) < int(min_periods), NULL, result)
}
"""
)

ROLLING_SLOPE = DolphinDBFunction(
    """
def rolling_slope(left, right, window, min_periods) {
    // 计算 right 关于 left 的滚动 OLS 斜率。
    return mbeta(right, left, int(window), int(min_periods))
}
"""
)

ROLLING_INTERCEPT = DolphinDBFunction(
    """
def rolling_intercept(left, right, window, min_periods) {
    // 根据滚动均值和斜率计算 right 关于 left 的 OLS 截距。
    slope = rolling_slope(left, right, window, min_periods)
    return mavg(right, int(window), int(min_periods)) - slope * mavg(left, int(window), int(min_periods))
}
""",
    dependencies=(ROLLING_SLOPE,),
)

ROLLING_TRUE_COUNT = DolphinDBFunction(
    """
def rolling_true_count(value, window, min_periods) {
    // 将 NULL 按 false 处理，统计每个滚动窗口中的 true 数量。
    return msum(int(nullFill(value, false)), int(window), int(min_periods))
}
"""
)


__all__ = [
    "MASK_EXPANDING_RESULT",
    "MASK_PAIR_EXPANDING_RESULT",
    "ROLLING_INTERCEPT",
    "ROLLING_MIN_PERIODS",
    "ROLLING_SLOPE",
    "ROLLING_TRUE_COUNT",
]
