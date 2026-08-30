"""定义因子分析模块共用的 DolphinDB 辅助函数。"""

from runtime.database.compile import DolphinDBFunction
from runtime.database.compile.common.functions import IS_FINITE_NUMBER


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


FACTOR_VALIDATE_GROUPS = DolphinDBFunction(
    module="factor",
    definition=r"""
    def factorValidateGroups(
        processedTable,
        factorCols,
        nGroups) {
        if (nGroups < 2) {
            throw "nGroups must be at least 2"
        }
        factorColNames = factorStringVector(factorCols)
        for (factorCol in factorColNames) {
            groupCol = string(factorCol) + "_group"
            factorCheckColumns(processedTable, symbol([groupCol]))
            groupSym = symbol([groupCol])[0]
            values = processedTable[groupSym]
            valueType = type(values)
            if (!(valueType in [CHAR, SHORT, INT, LONG, FLOAT, DOUBLE])) {
                throw groupCol + " must be a numeric group column, actual type: " +
                    typestr(values)
            }
            nonNullValues = values[!isNull(values)]
            if (size(nonNullValues) == 0) {
                continue
            }
            if (sum(!is_finite_number(nonNullValues)) > 0) {
                throw groupCol + " contains non-finite group values"
            }
            numericValues = double(nonNullValues)
            if (sum(numericValues != floor(numericValues)) > 0) {
                throw groupCol + " contains non-integer group values"
            }
            if (sum(numericValues < 0 || numericValues >= nGroups) > 0) {
                throw groupCol + " must contain only group IDs in [0, " +
                    string(nGroups - 1) + "]"
            }
        }
        return true
    }
    """,
    dependencies=(
        FACTOR_STRING_VECTOR,
        FACTOR_CHECK_COLUMNS,
        IS_FINITE_NUMBER,
    ),
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
        valid = !isNull(weight) && !isNull(ret)
        validWeight = weight[valid]
        validReturn = ret[valid]
        totalWeight = sum(validWeight)
        if (!isValid(totalWeight) || totalWeight <= 0) {
            return double(NULL)
        }
        return sum(validWeight * validReturn) \ totalWeight
    }
    """,
)


FACTOR_EXTREME_WEIGHTED_RETURN = DolphinDBFunction(
    module="factor",
    definition=r"""
    def factorExtremeWeightedReturn(
        factorValue,
        weight,
        ret,
        nSelect,
        ascending) {
        selected = !isNull(factorValue) && (
            rank(
                factorValue,
                ascending,
                ,
                true,
                `first,
                false
            ) < int(nSelect)
        )
        return factorWeightedReturn(weight[selected], ret[selected])
    }
    """,
    dependencies=(FACTOR_WEIGHTED_RETURN,),
)

