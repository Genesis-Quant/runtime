"""截面算符共用的 DolphinDB 函数。"""

from core.query.dolphindb.function import DolphinDBFunction

BROADCAST_LIKE = DolphinDBFunction(
    """
    def broadcast_like(value, reference) {
        // 将标量 value 广播到与 reference 相同的长度。
        return take(value, size(reference))
    }
    """
)

CROSS_SECTION_RANK = DolphinDBFunction(
    """
    def cross_section_rank(value, ascending, ties_method, percent) {
        // 统一普通、密集和百分位截面排名，并将非百分位名次调整为从 1 开始。
        if (ties_method == "dense") {
            result = denseRank(value, ascending, true, percent)
        } else {
            result = rank(value, ascending, , true, ties_method, percent)
        }
        if (!percent) result = result + 1
        return result
    }
    """
)

CROSS_SECTION_SLOPE = DolphinDBFunction(
    """
    def cross_section_slope(left, right) {
        // 计算 right 关于 left 的截面 OLS 斜率；自变量无方差时返回 NULL。
        valid = isValid(left) && isValid(right)
        paired_left = iif(valid, double(left), double(NULL))
        paired_right = iif(valid, double(right), double(NULL))
        variance = covar(paired_left, paired_left)
        return iif(
            isNull(variance) || variance == 0,
            NULL,
            covar(paired_left, paired_right) / variance
        )
    }
    """
)

__all__ = ["BROADCAST_LIKE", "CROSS_SECTION_RANK", "CROSS_SECTION_SLOPE"]
