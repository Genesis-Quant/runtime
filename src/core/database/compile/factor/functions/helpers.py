"""定义因子分析模块共用的 DolphinDB 辅助函数。"""

from core.database.compile import DolphinDBFunction


FACTOR_CHECK_COLUMNS = DolphinDBFunction(
    module="factor",
    definition=r"""
    def factorCheckColumns(tb, requiredColumns) {
        columns = tb.columnNames()
        for (col in requiredColumns) {
            if (not(col in columns)) {
                throw "required column is missing: " + string(col)
            }
        }
    }
    """,
)

FACTOR_STRING_VECTOR = DolphinDBFunction(
    module="factor",
    definition=r"""
    def factorStringVector(cols) {
        if (typestr(cols) == "STRING") {
            return [string(cols)]
        }
        return string(cols)
    }
    """,
)

FACTOR_Z_SCORE = DolphinDBFunction(
    module="factor",
    definition=r"""
    def factorZScore(values) {
        valueStd = stdp(values)
        if (!isValid(valueStd) || valueStd == 0) {
            return take(double(NULL), size(values))
        }
        return (values - avg(values)) \ valueStd
    }
    """,
)

FACTOR_CLIP_MAD = DolphinDBFunction(
    module="factor",
    definition=r"""
    def factorClipMad(values) {
        valueMedian = median(values)
        mad = median(abs(values - valueMedian))
        if (!isValid(mad) || mad == 0) {
            return values
        }
        return values.clip(
            valueMedian - 3 * mad,
            valueMedian + 3 * mad
        )
    }
    """,
)

FACTOR_WEIGHTED_RETURN = DolphinDBFunction(
    module="factor",
    definition=r"""
    def factorWeightedReturn(weight, ret) {
        totalWeight = sum(weight)
        if (!isValid(totalWeight) || totalWeight <= 0) {
            return double(NULL)
        }
        return sum(weight * ret) \ totalWeight
    }
    """,
)

