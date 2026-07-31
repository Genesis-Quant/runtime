"""编译因子预处理、IC 和分组收益 DolphinDB 模块。"""

from pathlib import Path

from core.database.compile import (
    DolphinDBFunction,
    build_script as compile_script,
    write_script as write_compiled_script,
)
from core.database.compile.query.scripts import (
    write_script as write_query_script,
)
from core.utils import logger

MODULE = "factor"
DEFAULT_OUTPUT_DIR = Path("output")

FACTOR_CHECK_COLUMNS = DolphinDBFunction(
    module=MODULE,
    definition=r"""
    def factorCheckColumns(tb, requiredColumns) {
        columns = tb.columnNames()
        for (col in requiredColumns) {
            if (not(col in columns)) {
                throw "required column is missing: " + string(col)
            }
        }
    }
    """
)

FACTOR_STRING_VECTOR = DolphinDBFunction(
    module=MODULE,
    definition=r"""
    def factorStringVector(cols) {
        if (typestr(cols) == "STRING") {
            return [string(cols)]
        }
        return string(cols)
    }
    """
)

FACTOR_Z_SCORE = DolphinDBFunction(
    module=MODULE,
    definition=r"""
    def factorZScore(values) {
        valueStd = stdp(values)
        if (!isValid(valueStd) || valueStd == 0) {
            return take(double(NULL), size(values))
        }
        return (values - avg(values)) \ valueStd
    }
    """
)

FACTOR_CLIP_MAD = DolphinDBFunction(
    module=MODULE,
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
    """
)

FACTOR_WEIGHTED_RETURN = DolphinDBFunction(
    module=MODULE,
    definition=r"""
    def factorWeightedReturn(weight, ret) {
        totalWeight = sum(weight)
        if (!isValid(totalWeight) || totalWeight <= 0) {
            return double(NULL)
        }
        return sum(weight * ret) \ totalWeight
    }
    """
)

FACTOR_PREPROCESS = DolphinDBFunction(
    module=MODULE,
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

            rowIds = crossSection[`factor_preprocess_row_id]
            marketValue = double(crossSection[mktmvColSym])
            marketValue = iif(marketValue < 1, 1.0, marketValue)
            mv = factorZScore(log(marketValue))
            industryValues = string(crossSection[industryColSym])
            industries = sort(distinct(industryValues))

            x = matrix(mv)
            if (size(industries) > 1) {
                for (i in 1 .. (size(industries) - 1)) {
                    x = x join
                        matrix(double(industryValues == industries[i]))
                }
            }

            for (factorCol in factorColNames) {
                factorColSym = symbol([string(factorCol)])[0]
                y = factorZScore(
                    factorClipMad(double(crossSection[factorColSym]))
                )
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

FACTOR_INFORMATION_COEFFICIENT = DolphinDBFunction(
    module=MODULE,
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
    module=MODULE,
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

FACTOR_FUNCTIONS = (
    FACTOR_PREPROCESS,
    FACTOR_INFORMATION_COEFFICIENT,
    FACTOR_GROUP_RETURNS,
)


def build_script() -> str:
    """生成 factor.dos 模块。"""
    return compile_script(MODULE, FACTOR_FUNCTIONS)


def write_script(*, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    """按依赖顺序生成 query 依赖和 factor 模块。"""
    write_query_script(output_dir=output_dir)
    path = write_compiled_script(
        MODULE,
        build_script(),
        output_dir=output_dir,
    )
    logger.success(f"DolphinDB factor 模块已生成：{path}")
    return path


__all__ = [
    "FACTOR_FUNCTIONS",
    "MODULE",
    "build_script",
    "write_script",
]


if __name__ == "__main__":
    print(write_script())
