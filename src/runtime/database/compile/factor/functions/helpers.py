"""定义因子分析模块共用的 DolphinDB 辅助函数。"""

from runtime.database.compile import DolphinDBFunction


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
        if (any(!isNull(weight) && weight < 0)) {
            throw "市值权重不能为负数"
        }
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


FACTOR_EXTREME_RANKS = DolphinDBFunction(
    module="factor",
    definition=r"""
    def factorExtremeRanks(values, codes, ascending) {
        ranks = take(long(NULL), size(values))
        if (size(values) == 0) return ranks
        ranked = table(
            long(0 .. (size(values) - 1)) as row_id,
            double(values) as factor_value,
            string(codes) as factor_code
        )
        ranked = select * from ranked where !isNull(factor_value)
        ranked.sortBy!(`factor_value`factor_code, [ascending, ascending])
        if (ranked.rows() > 0) {
            ranks[ranked.row_id] = long(0 .. (ranked.rows() - 1))
        }
        return ranks
    }
    """,
)


FACTOR_VALIDATE_GROUPS = DolphinDBFunction(
    module="factor",
    definition=r"""
    def factorValidateGroups(tb, factorCols, nGroups, timeCol="time", codeCol="code") {
        for (factorCol in factorStringVector(factorCols)) {
            groupCol = string(factorCol) + "_group"
            factorCheckColumns(tb, symbol([factorCol, groupCol, timeCol, codeCol]))
            groups = double(tb[groupCol])
            invalid = !isNull(tb[factorCol]) && (
                isNull(groups) || groups < 0 || groups >= nGroups || groups != floor(groups)
            )
            if (any(invalid)) {
                sample = tb[invalid]
                sample = sample[0:min(5, sample.rows())]
                throw groupCol + " 必须是 [0, " + string(nGroups - 1) +
                    "] 内的整数；违规行数=" + string(sum(invalid)) +
                    "，日期=" + string(sample[timeCol]) + ", code=" + string(sample[codeCol])
            }
        }
    }
    """,
    dependencies=(FACTOR_STRING_VECTOR, FACTOR_CHECK_COLUMNS),
)


FACTOR_EXTREME_WEIGHTED_RETURN = DolphinDBFunction(
    module="factor",
    definition=r"""
    def factorExtremeWeightedReturn(
        factorValue,
        weight,
        ret,
        nSelect,
        ascending,
        codes) {
        selected = !isNull(factorValue) && (
            factorExtremeRanks(factorValue, codes, ascending) < int(nSelect)
        )
        return factorWeightedReturn(weight[selected], ret[selected])
    }
    """,
    dependencies=(FACTOR_WEIGHTED_RETURN, FACTOR_EXTREME_RANKS),
)

