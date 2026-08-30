"""定义因子 IC 与分组收益分析函数。"""

from runtime.database.compile import DolphinDBFunction
from runtime.database.compile.common.functions import IS_FINITE_NUMBER

from .helpers import (
    FACTOR_CHECK_COLUMNS,
    FACTOR_EXTREME_WEIGHTED_RETURN,
    FACTOR_STRING_VECTOR,
    FACTOR_VALIDATE_GROUPS,
    FACTOR_WEIGHTED_RETURN,
)

FACTOR_INFORMATION_COEFFICIENT = DolphinDBFunction(
    module="factor",
    definition=r"""
    def factorInformationCoefficient(
        processedTable,
        returnCols,
        factorCols,
        timeCol="time") {
        returnColNames = factorStringVector(returnCols)
        factorColNames = factorStringVector(factorCols)
        factorCheckColumns(
            processedTable,
            symbol([timeCol])
        )
        factorCheckColumns(processedTable, symbol(factorColNames))
        factorCheckColumns(
            processedTable,
            symbol(returnColNames)
        )

        result =
            <select distinct(_$timeCol) as time
             from processedTable>.eval()
        result = result.sortBy!(`time)

        timeSym = symbol([timeCol])[0]
        for (factorCol in factorColNames) {
            factorSym = symbol([string(factorCol)])[0]
            for (retCol in returnColNames) {
                retSym = symbol([string(retCol)])[0]
                corrTable = sql(
                    [
                        sqlCol(timeSym, , `time),
                        sqlColAlias(
                            makeCall(
                                corr,
                                sqlCol(factorSym),
                                sqlCol(retSym)
                            ),
                            `ic
                        ),
                        sqlColAlias(
                            makeCall(
                                spearmanr,
                                sqlCol(factorSym),
                                sqlCol(retSym)
                            ),
                            `rank_ic
                        )
                    ],
                    processedTable,
                    ,
                    [sqlCol(timeSym)]
                ).eval()
                result = lj(result, corrTable, `time)
                result.rename!(
                    `ic,
                    symbol([
                        string(factorCol) + "_" +
                        string(retCol) + "_ic"
                    ])[0]
                )
                result.rename!(
                    `rank_ic,
                    symbol([
                        string(factorCol) + "_" +
                        string(retCol) + "_rank_ic"
                    ])[0]
                )
            }
        }
        return result
    }
    """,
    dependencies=(
        FACTOR_STRING_VECTOR,
        FACTOR_CHECK_COLUMNS,
    ),
)

FACTOR_GROUP_RETURNS = DolphinDBFunction(
    module="factor",
    definition=r"""
    def factorGroupReturns(
        processedFactorTable,
        returnCols,
        factorCols,
        nGroups,
        nSelect,
        timeCol="time",
        codeCol="code",
        mktmvCol="mktmv") {
        if (nGroups < 2) {
            throw "nGroups must be at least 2"
        }
        if (nSelect < 1) {
            throw "nSelect must be at least 1"
        }
        returnColNames = factorStringVector(returnCols)
        factorColNames = factorStringVector(factorCols)
        factorValidateGroups(
            processedFactorTable,
            factorColNames,
            nGroups
        )
        factorCheckColumns(
            processedFactorTable,
            symbol([timeCol, codeCol, mktmvCol])
        )
        factorCheckColumns(processedFactorTable, symbol(factorColNames))
        factorCheckColumns(
            processedFactorTable,
            symbol(returnColNames)
        )

        result =
            <select distinct(_$timeCol) as time
             from processedFactorTable>.eval()
        result = result.sortBy!(`time)

        timeSym = symbol([timeCol])[0]
        mktmvSym = symbol([mktmvCol])[0]
        for (factorCol in factorColNames) {
            factorSym = symbol([string(factorCol)])[0]
            groupCol = string(factorCol) + "_group"
            factorCheckColumns(
                processedFactorTable,
                symbol([groupCol])
            )
            groupSym = symbol([groupCol])[0]
            for (retCol in returnColNames) {
                retSym = symbol([string(retCol)])[0]
                extremes = sql(
                    [
                        sqlCol(timeSym, , `time),
                        sqlColAlias(
                            makeCall(
                                factorExtremeWeightedReturn,
                                sqlCol(factorSym),
                                sqlCol(mktmvSym),
                                sqlCol(retSym),
                                nSelect,
                                true
                            ),
                            `bottom_ret
                        ),
                        sqlColAlias(
                            makeCall(
                                factorExtremeWeightedReturn,
                                sqlCol(factorSym),
                                sqlCol(mktmvSym),
                                sqlCol(retSym),
                                nSelect,
                                false
                            ),
                            `top_ret
                        )
                    ],
                    processedFactorTable,
                    ,
                    [sqlCol(timeSym)]
                ).eval()
                bottomRows =
                    <select time, bottom_ret as ret from extremes>.eval()
                result = lj(result, bottomRows, `time)
                result.rename!(
                    `ret,
                    symbol([
                        string(factorCol) + "_" +
                        string(retCol) + "_bottom"
                    ])[0]
                )
                for (groupId in 0 .. (nGroups - 1)) {
                    weighted = sql(
                        [
                            sqlCol(timeSym, , `time),
                            sqlColAlias(
                                makeCall(
                                    factorWeightedReturn,
                                    sqlCol(mktmvSym),
                                    sqlCol(retSym)
                                ),
                                `ret
                            )
                        ],
                        processedFactorTable,
                        expr(sqlCol(groupSym), ==, groupId),
                        [sqlCol(timeSym)]
                    ).eval()
                    result = lj(result, weighted, `time)
                    result.rename!(
                        `ret,
                        symbol([
                            string(factorCol) + "_" +
                            string(retCol) + "_group" +
                            string(groupId)
                        ])[0]
                    )
                }
                topRows =
                    <select time, top_ret as ret from extremes>.eval()
                result = lj(result, topRows, `time)
                result.rename!(
                    `ret,
                    symbol([
                        string(factorCol) + "_" +
                        string(retCol) + "_top"
                    ])[0]
                )
            }
        }
        return result
    }
    """,
    dependencies=(
        FACTOR_STRING_VECTOR,
        FACTOR_CHECK_COLUMNS,
        FACTOR_VALIDATE_GROUPS,
        FACTOR_WEIGHTED_RETURN,
        FACTOR_EXTREME_WEIGHTED_RETURN,
    ),
)


FACTOR_DIAGNOSTICS = DolphinDBFunction(
    module="factor",
    definition=r"""
    def factorDiagnostics(
        processedFactorTable,
        returnCols,
        factorCols,
        nGroups,
        timeCol="time",
        codeCol="code",
        mktmvCol="mktmv") {
        if (nGroups < 2) {
            throw "nGroups must be at least 2"
        }
        returnColNames = factorStringVector(returnCols)
        factorColNames = factorStringVector(factorCols)
        factorCheckColumns(
            processedFactorTable,
            symbol([timeCol, codeCol, mktmvCol])
        )
        factorCheckColumns(processedFactorTable, symbol(factorColNames))
        factorCheckColumns(processedFactorTable, symbol(returnColNames))
        factorValidateGroups(
            processedFactorTable,
            factorColNames,
            nGroups
        )

        timeSym = symbol([timeCol])[0]
        codeSym = symbol([codeCol])[0]
        mktmvSym = symbol([mktmvCol])[0]
        result = table(
            array(type(processedFactorTable[timeSym]), 0) as time,
            array(STRING, 0) as factor,
            array(STRING, 0) as return_column,
            array(LONG, 0) as universe_count,
            array(LONG, 0) as factor_valid_count,
            array(LONG, 0) as return_valid_count,
            array(LONG, 0) as paired_valid_count,
            array(LONG, 0) as group_valid_count,
            array(LONG, 0) as group_min,
            array(LONG, 0) as group_max,
            array(LONG, 0) as occupied_group_count,
            array(LONG, 0) as min_group_size,
            array(LONG, 0) as max_group_size
        )
        dateTable =
            <select distinct(_$timeCol) as date_col
             from processedFactorTable>.eval()
        dates = dateTable.sortBy!(`date_col)[`date_col]

        for (currentDate in dates) {
            crossSection =
                <select *
                 from processedFactorTable
                 where _$timeCol = currentDate>.eval()
            codeValues = crossSection[codeSym]
            weightValues = crossSection[mktmvSym]
            weightValid = !isNull(weightValues)
            universeCount = long(
                size(distinct(codeValues[!isNull(codeValues)]))
            )
            for (factorCol in factorColNames) {
                factorSym = symbol([string(factorCol)])[0]
                factorValues = crossSection[factorSym]
                factorValid = is_finite_number(factorValues)
                factorValidCount = long(sum(factorValid))

                groupCol = string(factorCol) + "_group"
                groupSym = symbol([groupCol])[0]
                groupValues = crossSection[groupSym]
                groupValid = !isNull(groupValues)

                for (retCol in returnColNames) {
                    retSym = symbol([string(retCol)])[0]
                    returnValues = crossSection[retSym]
                    returnValid = is_finite_number(returnValues)
                    returnValidCount = long(sum(returnValid))
                    pairedValidCount = long(sum(factorValid && returnValid))
                    eligibleGroup = groupValid && returnValid && weightValid
                    groupValidCount = long(sum(eligibleGroup))
                    groupMin = long(NULL)
                    groupMax = long(NULL)
                    occupiedGroupCount = long(0)
                    minGroupSize = long(NULL)
                    maxGroupSize = long(NULL)
                    if (groupValidCount > 0) {
                        validGroups = long(groupValues[eligibleGroup])
                        occupiedGroups = sort(distinct(validGroups))
                        occupiedGroupCount = long(size(occupiedGroups))
                        groupMin = long(first(occupiedGroups))
                        groupMax = long(last(occupiedGroups))
                        for (groupId in occupiedGroups) {
                            groupSize = long(sum(validGroups == groupId))
                            if (!isValid(minGroupSize) || groupSize < minGroupSize) {
                                minGroupSize = groupSize
                            }
                            if (!isValid(maxGroupSize) || groupSize > maxGroupSize) {
                                maxGroupSize = groupSize
                            }
                        }
                    }
                    result.append!(table(
                        take(currentDate, 1) as time,
                        take(string(factorCol), 1) as factor,
                        take(string(retCol), 1) as return_column,
                        take(universeCount, 1) as universe_count,
                        take(factorValidCount, 1) as factor_valid_count,
                        take(returnValidCount, 1) as return_valid_count,
                        take(pairedValidCount, 1) as paired_valid_count,
                        take(groupValidCount, 1) as group_valid_count,
                        take(groupMin, 1) as group_min,
                        take(groupMax, 1) as group_max,
                        take(occupiedGroupCount, 1) as occupied_group_count,
                        take(minGroupSize, 1) as min_group_size,
                        take(maxGroupSize, 1) as max_group_size
                    ))
                }
            }
        }
        return result
    }
    """,
    dependencies=(
        FACTOR_STRING_VECTOR,
        FACTOR_CHECK_COLUMNS,
        FACTOR_VALIDATE_GROUPS,
        IS_FINITE_NUMBER,
    ),
)

