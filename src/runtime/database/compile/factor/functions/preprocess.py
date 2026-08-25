"""定义因子去极值、标准化、中性化和分组函数。"""

from runtime.database.compile import DolphinDBFunction

from .helpers import (
    FACTOR_CHECK_COLUMNS,
    FACTOR_CLIP_MAD,
    FACTOR_STRING_VECTOR,
    FACTOR_Z_SCORE,
)


FACTOR_PREPROCESS = DolphinDBFunction(
    module="factor",
    definition=r"""
    def factorPreprocess(
        rawFactorTable,
        factorCols,
        nGroups,
        timeCol="time",
        codeCol="code",
        mktmvCol="mktmv",
        industryCol="industry") {
        if (nGroups < 2) {
            throw "nGroups must be at least 2"
        }
        factorColNames = factorStringVector(factorCols)
        factorCheckColumns(
            rawFactorTable,
            symbol([timeCol, codeCol, mktmvCol, industryCol])
        )
        factorCheckColumns(rawFactorTable, symbol(factorColNames))
        if (size(rawFactorTable) == 0) {
            throw "factorPreprocess 输入表为空；请检查 dataset_query.filters 和股票池条件"
        }
        for (factorCol in factorColNames) {
            groupColName = string(factorCol) + "_group"
            if (groupColName in rawFactorTable.columnNames()) {
                throw groupColName + " column already exists"
            }
        }

        workingTable = rawFactorTable.copy()
        addColumn(workingTable, `factor_preprocess_row_id, LONG)
        update workingTable
            set factor_preprocess_row_id =
                long(0 .. (size(workingTable) - 1))
        dateTable =
            <select distinct(_$timeCol) as date_col
             from workingTable>.eval()
        dates = dateTable.sortBy!(`date_col)[`date_col]

        for (factorCol in factorColNames) {
            factorProcessedCol =
                symbol([string(factorCol) + "_processed"])[0]
            addColumn(workingTable, factorProcessedCol, DOUBLE)
            groupCol = symbol([string(factorCol) + "_group"])[0]
            addColumn(workingTable, groupCol, INT)
        }

        mktmvColSym = symbol([mktmvCol])[0]
        industryColSym = symbol([industryCol])[0]
        for (currentDate in dates) {
            crossSection =
                <select *
                 from workingTable
                 where _$timeCol = currentDate>.eval()
            if (size(crossSection) == 0) {
                continue
            }

            for (factorCol in factorColNames) {
                factorColSym = symbol([string(factorCol)])[0]
                rawFactor = double(crossSection[factorColSym])
                rawMarketValue = double(crossSection[mktmvColSym])
                rawIndustry = string(crossSection[industryColSym])
                validMask = isValid(rawFactor) &&
                    isValid(rawMarketValue) &&
                    isValid(rawIndustry)
                if (sum(validMask) == 0) {
                    continue
                }
                rowIds = crossSection[`factor_preprocess_row_id][validMask]
                marketValue = rawMarketValue[validMask]
                marketValue = iif(marketValue < 1, 1.0, marketValue)
                mv = factorZScore(log(marketValue))
                industryValues = rawIndustry[validMask]
                y = factorZScore(
                    factorClipMad(rawFactor[validMask])
                )
                regressionMask = isValid(y) && isValid(mv)
                if (sum(regressionMask) == 0) {
                    continue
                }
                rowIds = rowIds[regressionMask]
                y = y[regressionMask]
                mv = mv[regressionMask]
                industryValues = industryValues[regressionMask]
                industries = sort(distinct(industryValues))
                x = matrix(mv)
                if (size(industries) > 1) {
                    for (i in 1 .. (size(industries) - 1)) {
                        x = x join
                            matrix(double(industryValues == industries[i]))
                    }
                }
                if (size(y) <= cols(x)) {
                    continue
                }
                beta = ols(y, x, true, 0)
                fitted = beta[0] + beta[1] * mv
                if (size(industries) > 1) {
                    for (i in 1 .. (size(industries) - 1)) {
                        fitted += beta[i + 1] * flatten(x[, i])
                    }
                }

                factorProcessedCol =
                    symbol([string(factorCol) + "_processed"])[0]
                processedValues = workingTable[factorProcessedCol]
                residual = factorZScore(y - fitted)
                processedValues[rowIds] = residual
                workingTable[factorProcessedCol] = processedValues

                validRows = table(
                    rowIds as factor_preprocess_row_id,
                    residual as factor_value
                )
                validRows =
                    select factor_preprocess_row_id, factor_value
                    from validRows
                    where isValid(factor_value)
                    order by factor_value
                if (size(validRows) > 0) {
                    rankIndex = 0 .. (size(validRows) - 1)
                    groups = int(
                        floor(
                            rankIndex * nGroups \
                            double(size(validRows))
                        )
                    )
                    groupCol =
                        symbol([string(factorCol) + "_group"])[0]
                    groupValues = workingTable[groupCol]
                    groupValues[validRows[`factor_preprocess_row_id]] = iif(
                        groups >= nGroups,
                        nGroups - 1,
                        groups
                    )
                    workingTable[groupCol] = groupValues
                }
            }
        }

        for (factorCol in factorColNames) {
            factorColSym = symbol([string(factorCol)])[0]
            factorProcessedCol =
                symbol([string(factorCol) + "_processed"])[0]
            workingTable.dropColumns!([factorColSym])
            workingTable.rename!(factorProcessedCol, factorColSym)
        }
        workingTable.dropColumns!([`factor_preprocess_row_id])
        return workingTable
    }
    """,
    dependencies=(
        FACTOR_STRING_VECTOR,
        FACTOR_CHECK_COLUMNS,
        FACTOR_Z_SCORE,
        FACTOR_CLIP_MAD,
    ),
)

