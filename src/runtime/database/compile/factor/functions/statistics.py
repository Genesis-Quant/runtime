"""定义因子 IC 与分组收益分析函数。"""

from runtime.database.compile import DolphinDBFunction

from .helpers import (
    FACTOR_CHECK_COLUMNS,
    FACTOR_EXTREME_WEIGHTED_RETURN,
    FACTOR_STRING_VECTOR,
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


FACTOR_EXECUTION_STATISTICS = DolphinDBFunction(
    module="factor",
    definition=r"""
    def factorExecutionStatistics(
        sourceTable,
        computedTable,
        filteredTable,
        filterCols,
        startTime,
        endTime,
        timeCol="time",
        codeCol="code") {
        filterColNames = factorStringVector(filterCols)
        requiredColumns = symbol([timeCol, codeCol])
        factorCheckColumns(sourceTable, requiredColumns)
        factorCheckColumns(computedTable, requiredColumns)
        factorCheckColumns(filteredTable, requiredColumns)
        if (size(filterColNames) > 0) {
            factorCheckColumns(computedTable, symbol(filterColNames))
        }

        result =
            <select count(*) as source_count
             from sourceTable
             where
                _$timeCol >= startTime,
                _$timeCol < endTime,
                !isNull(_$codeCol)
             group by _$timeCol>.eval()
        result.rename!(symbol([timeCol])[0], `time)
        result.sortBy!(`time)

        timeSym = symbol([timeCol])[0]
        codeSym = symbol([codeCol])[0]
        computedMask = (
            computedTable[timeSym] >= startTime &&
            computedTable[timeSym] < endTime &&
            !isNull(computedTable[codeSym])
        )
        if (size(filterColNames) > 0) {
            for (index in 0 .. (size(filterColNames) - 1)) {
                filterSym = symbol([string(filterColNames[index])])[0]
                computedMask = computedMask && nullFill(
                    computedTable[filterSym],
                    false
                )
                stageRows = table(
                    computedTable[timeSym][computedMask] as time
                )
                stageCounts = select count(*) as stage_count
                    from stageRows
                    group by time
                stageColumn = symbol([
                    "filter" + string(index) + "_count"
                ])[0]
                stageCounts.rename!(`stage_count, stageColumn)
                result = lj(result, stageCounts, `time)
                result[stageColumn] = long(
                    nullFill(result[stageColumn], 0)
                )
                filterNameColumn = symbol([
                    "filter" + string(index) + "_name"
                ])[0]
                result[filterNameColumn] = take(
                    string(filterColNames[index]),
                    result.rows()
                )
            }
        }

        filteredCounts =
            <select count(*) as filtered_count
             from filteredTable
             where
                _$timeCol >= startTime,
                _$timeCol < endTime,
                !isNull(_$codeCol)
             group by _$timeCol>.eval()
        filteredCounts.rename!(symbol([timeCol])[0], `time)
        result = lj(result, filteredCounts, `time)
        result[`filtered_count] = long(
            nullFill(result[`filtered_count], 0)
        )
        result[`retention_rate] = iif(
            result[`source_count] > 0,
            double(result[`filtered_count]) \
                double(result[`source_count]),
            double(NULL)
        )
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
        FACTOR_WEIGHTED_RETURN,
        FACTOR_EXTREME_WEIGHTED_RETURN,
    ),
)


FACTOR_GROUP_TURNOVER = DolphinDBFunction(
    module="factor",
    definition=r"""
    def factorGroupTurnover(
        processedFactorTable,
        factorCols,
        turnoverPeriods,
        nGroups,
        nSelect,
        timeCol="time",
        codeCol="code") {
        if (nGroups < 2) {
            throw "nGroups must be at least 2"
        }
        if (nSelect < 1) {
            throw "nSelect must be at least 1"
        }
        factorColNames = factorStringVector(factorCols)
        periodValues = sort(distinct(int(turnoverPeriods)))
        if (size(periodValues) == 0 || any(periodValues < 1)) {
            throw "turnoverPeriods must contain positive integers"
        }
        factorCheckColumns(
            processedFactorTable,
            symbol([timeCol, codeCol])
        )
        factorCheckColumns(processedFactorTable, symbol(factorColNames))

        groupColumns = "group" + string(0 .. (nGroups - 1))
        result = table(
            array(TIMESTAMP, 0) as time,
            array(STRING, 0) as factor,
            array(INT, 0) as periods,
            array(DOUBLE, 0) as rank_autocorrelation
        )
        addColumn(result, ["bottom"], take(DOUBLE, 1))
        addColumn(result, groupColumns, take(DOUBLE, nGroups))
        addColumn(result, ["top"], take(DOUBLE, 1))

        for (factorCol in factorColNames) {
            groupCol = string(factorCol) + "_group"
            factorCheckColumns(processedFactorTable, symbol([groupCol]))
            factorMembers = <select
                    timestamp(_$timeCol) as time,
                    string(_$codeCol) as code,
                    double(_$factorCol) as factor_value
                from processedFactorTable
                where !isNull(_$factorCol)>.eval()
            if (factorMembers.rows() > 0) {
                factorMembers = select distinct time, code, factor_value
                    from factorMembers
                factorDates = select distinct time from factorMembers
                factorDates.sortBy!(`time)
                groupMembers = <select
                        timestamp(_$timeCol) as time,
                        string(_$codeCol) as code,
                        int(_$groupCol) as group_id
                    from processedFactorTable
                    where
                        !isNull(_$factorCol),
                        !isNull(_$groupCol)>.eval()
                groupMembers = select distinct time, code, group_id
                    from groupMembers
                ranks = select
                        time,
                        code,
                        rank(
                            factor_value,
                            true,
                            ,
                            true,
                            `average,
                            false
                        ) as factor_rank
                    from factorMembers
                    context by time
                extremeRanks = select
                        time,
                        code,
                        rank(
                            factor_value,
                            true,
                            ,
                            true,
                            `first,
                            false
                        ) as bottom_rank,
                        rank(
                            factor_value,
                            false,
                            ,
                            true,
                            `first,
                            false
                        ) as top_rank
                    from factorMembers
                    context by time
                portfolioMembers = select
                        time,
                        code,
                        int(group_id + 1) as portfolio_id
                    from groupMembers
                bottomMembers = select
                        time,
                        code,
                        int(0) as portfolio_id
                    from extremeRanks
                    where bottom_rank < int(nSelect)
                topMembers = select
                        time,
                        code,
                        int(nGroups + 1) as portfolio_id
                    from extremeRanks
                    where top_rank < int(nSelect)
                portfolioMembers = unionAll(
                    portfolioMembers,
                    bottomMembers
                )
                portfolioMembers = unionAll(
                    portfolioMembers,
                    topMembers
                )
                portfolioDates = select distinct time, portfolio_id
                    from portfolioMembers
                portfolioDates.sortBy!(`portfolio_id`time)

                for (period in periodValues) {
                    rankDateMap = select
                        time,
                        move(time, period) as previous_time
                        from factorDates
                    currentRanks = lj(ranks, rankDateMap, `time)
                    previousRanks = select
                            time as previous_time,
                            code,
                            factor_rank as previous_rank
                        from ranks
                    rankPairs = lj(currentRanks, previousRanks, ["previous_time", "code"])
                    rankRows = select
                            corr(
                                factor_rank,
                                previous_rank
                            ) as rank_autocorrelation
                        from rankPairs
                        where !isNull(previous_rank)
                        group by time

                    portfolioDateMap = table(
                        array(TIMESTAMP, 0) as time,
                        array(INT, 0) as portfolio_id,
                        array(TIMESTAMP, 0) as previous_time
                    )
                    for (portfolioId in 0 .. (nGroups + 1)) {
                        portfolioPeriodDates = select
                                time,
                                portfolio_id
                            from portfolioDates
                            where portfolio_id == int(portfolioId)
                        portfolioPeriodDates.sortBy!(`time)
                        portfolioPeriodDates["previous_time"] = move(
                            portfolioPeriodDates["time"],
                            period
                        )
                        portfolioDateMap = unionAll(
                            portfolioDateMap,
                            portfolioPeriodDates
                        )
                    }
                    currentMembers = lj(portfolioMembers, portfolioDateMap, ["time", "portfolio_id"])
                    previousMembers = select
                            time as previous_time,
                            code,
                            portfolio_id,
                            true as retained
                        from portfolioMembers
                    matchedMembers = lj(currentMembers, previousMembers, ["previous_time", "code", "portfolio_id"])
                    turnoverRows = select
                            1.0 - sum(
                                iif(isNull(retained), 0, 1)
                            ) \ count(*) as turnover
                        from matchedMembers
                        where
                            !isNull(previous_time)
                        group by time, portfolio_id

                    periodResult = select time from factorDates
                    periodResult["factor"] = take(
                        string(factorCol),
                        periodResult.rows()
                    )
                    periodResult["periods"] = take(
                        int(period),
                        periodResult.rows()
                    )
                    periodResult = lj(periodResult, rankRows, `time)
                    for (portfolioId in 0 .. (nGroups + 1)) {
                        portfolioRows = select time, turnover
                            from turnoverRows
                            where portfolio_id == portfolioId
                        if (portfolioId == 0) {
                            portfolioColumn = `bottom
                        } else if (portfolioId == nGroups + 1) {
                            portfolioColumn = `top
                        } else {
                            portfolioColumn = symbol([
                                "group" + string(portfolioId - 1)
                            ])[0]
                        }
                        portfolioRows.rename!(`turnover, portfolioColumn)
                        periodResult = lj(periodResult, portfolioRows, `time)
                    }
                    result = unionAll(result, periodResult)
                }
            }
        }
        result.sortBy!(`factor`periods`time)
        return result
    }
    """,
    dependencies=(
        FACTOR_STRING_VECTOR,
        FACTOR_CHECK_COLUMNS,
    ),
)

