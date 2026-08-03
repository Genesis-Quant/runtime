"""定义因子 IC 与分组收益分析函数。"""

from runtime.database.compile import DolphinDBFunction

from .helpers import (
    FACTOR_CHECK_COLUMNS,
    FACTOR_STRING_VECTOR,
    FACTOR_WEIGHTED_RETURN,
)


FACTOR_INFORMATION_COEFFICIENT = DolphinDBFunction(
    module="factor",
    definition=r"""
    def factorInformationCoefficient(
        processedTable,
        returnCols,
        factorCol,
        timeCol="time") {
        returnColNames = factorStringVector(returnCols)
        factorCheckColumns(
            processedTable,
            symbol([timeCol, factorCol])
        )
        factorCheckColumns(
            processedTable,
            symbol(returnColNames)
        )

        result =
            <select distinct(_$timeCol) as time
             from processedTable>.eval()
        result = result.sortBy!(`time)

        timeSym = symbol([timeCol])[0]
        factorSym = symbol([factorCol])[0]
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
                symbol([string(retCol) + "_ic"])[0]
            )
            result.rename!(
                `rank_ic,
                symbol([string(retCol) + "_rank_ic"])[0]
            )
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
        factorCol,
        nGroups,
        timeCol="time",
        codeCol="code",
        mktmvCol="mktmv") {
        if (nGroups < 2) {
            throw "nGroups must be at least 2"
        }
        returnColNames = factorStringVector(returnCols)
        groupCol = string(factorCol) + "_group"
        factorCheckColumns(
            processedFactorTable,
            symbol([
                timeCol,
                codeCol,
                factorCol,
                mktmvCol,
                groupCol
            ])
        )
        factorCheckColumns(
            processedFactorTable,
            symbol(returnColNames)
        )

        result =
            <select distinct(_$timeCol) as time
             from processedFactorTable>.eval()
        result = result.sortBy!(`time)

        timeSym = symbol([timeCol])[0]
        groupSym = symbol([groupCol])[0]
        mktmvSym = symbol([mktmvCol])[0]
        for (retCol in returnColNames) {
            retSym = symbol([string(retCol)])[0]
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
                        string(retCol) + "_group" + string(groupId)
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
        FACTOR_WEIGHTED_RETURN,
    ),
)

